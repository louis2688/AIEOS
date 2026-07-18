from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aeios.api.auth import ClerkAuthMiddleware, ClerkJWTVerifier, resolve_owner_id
from aeios.config import Settings, get_settings
from aeios.core.kernel import Kernel
from aeios.core.pipeline_runner import PipelineRunner
from aeios.knowledge.artifacts import collect_task_artifacts
from aeios.knowledge.search import KnowledgeSearch
from aeios.models.client import ModelClient
from aeios.observability.metrics import get_metrics
from aeios.observability.request_id import RequestIdMiddleware
from aeios.persistence.pipelines import PipelineStep, PipelineStore
from aeios.persistence.projects import ProjectStore

_TASK_TERMINAL = frozenset({"completed", "failed", "cancelled"})


class TaskCreate(BaseModel):
    goal: str = Field(..., min_length=1)
    agent: str | None = None


class TaskOut(BaseModel):
    id: str
    goal: str
    status: str
    agent: str | None
    owner_id: str = "local"
    plan: list[str]
    steps: list[dict[str, Any]]
    result: str | None
    error: str | None


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    created_at: str
    updated_at: str


class PipelineStepIn(BaseModel):
    goal: str = Field(..., min_length=1)
    agent: str = "software_engineer"


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    project_id: str | None = None
    steps: list[PipelineStepIn] = Field(..., min_length=1)


class PipelineOut(BaseModel):
    id: str
    name: str
    description: str
    project_id: str | None
    owner_id: str
    steps: list[PipelineStepIn]
    created_at: str
    updated_at: str


class PipelineRunCreate(BaseModel):
    input_goal: str = Field(..., min_length=1)


class PipelineRunOut(BaseModel):
    id: str
    pipeline_id: str
    status: str
    input_goal: str
    step_results: list[dict[str, Any]]
    result: str | None
    error: str | None
    created_at: str
    updated_at: str


class KnowledgeHitOut(BaseModel):
    kind: str
    id: str
    title: str
    snippet: str
    score: float
    href: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchOut(BaseModel):
    query: str
    count: int
    results: list[KnowledgeHitOut]


class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    provider: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1, max_length=120)
    base_url: str | None = None
    api_key: str | None = None
    is_default: bool = False
    enabled: bool = True


class ModelUpdate(BaseModel):
    name: str | None = None
    model_id: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


class ModelOut(BaseModel):
    id: str
    name: str
    provider: str
    model_id: str
    base_url: str | None
    api_key_set: bool
    api_key_masked: str | None
    is_default: bool
    enabled: bool
    owner_id: str = "local"
    created_at: str
    updated_at: str


def _task_out(task: Any) -> TaskOut:
    return TaskOut(**task.model_dump(mode="json"))


def _pipeline_out(p: Any) -> PipelineOut:
    return PipelineOut(
        id=p.id,
        name=p.name,
        description=p.description,
        project_id=p.project_id,
        owner_id=p.owner_id,
        steps=[PipelineStepIn(goal=s.goal, agent=s.agent) for s in p.steps],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _run_out(r: Any) -> PipelineRunOut:
    return PipelineRunOut(**r.__dict__)


def create_app(
    workspace: Path | None = None,
    *,
    auth_settings: Settings | None = None,
    auth_verifier: ClerkJWTVerifier | None = None,
) -> FastAPI:
    root = workspace or Path.cwd()
    kernel = Kernel(workspace=root)
    # Share the kernel DB (sqlite path or postgres) with API stores.
    projects = ProjectStore(kernel.db)
    pipelines = PipelineStore(kernel.db)
    runner = PipelineRunner(kernel, pipelines)
    knowledge = KnowledgeSearch(
        kernel, pipelines, projects, vector_index=kernel.vector_index
    )
    models = kernel.models
    model_client = ModelClient()

    app = FastAPI(title="AEIOS API", version="0.7.0")
    app.state.kernel = kernel
    app.state.projects = projects
    app.state.pipelines = pipelines
    app.state.knowledge = knowledge
    app.state.models = models

    # Innermost → outermost: auth, request-id, CORS (401s still get CORS headers).
    app.add_middleware(
        ClerkAuthMiddleware,
        settings=auth_settings or get_settings(),
        verifier=auth_verifier,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://aeios-five.vercel.app",
        ],
        # Preview deployments (aeios-*.vercel.app) and other Vercel hosts.
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "aeios"}

    @app.get("/v1/metrics")
    def metrics() -> dict[str, Any]:
        """In-process counters (LLM tokens/cost placeholders, tools, tasks, HTTP)."""
        return get_metrics().snapshot().to_dict()

    @app.get("/v1/status")
    def status() -> dict[str, Any]:
        return kernel.status()

    @app.get("/v1/agents")
    def agents() -> dict[str, list[str]]:
        return {"agents": kernel.syscalls.list_agents()}

    @app.get("/v1/tools")
    def tools() -> dict[str, list[str]]:
        return {"tools": kernel.syscalls.list_tools()}

    @app.post("/v1/tasks", response_model=TaskOut)
    def create_task(
        request: Request, body: TaskCreate, wait: bool = True
    ) -> TaskOut:
        """Create a task. wait=true (default) blocks until done; wait=false returns immediately."""
        owner = resolve_owner_id(request)
        task = kernel.syscalls.execute_task(
            body.goal, agent=body.agent, wait=wait, owner_id=owner
        )
        return _task_out(task)

    @app.get("/v1/tasks", response_model=list[TaskOut])
    def list_tasks(request: Request, limit: int = 50) -> list[TaskOut]:
        owner = resolve_owner_id(request)
        tasks = kernel.syscalls.list_tasks(limit=limit, owner_id=owner)
        return [_task_out(t) for t in tasks]

    @app.get("/v1/tasks/{task_id}", response_model=TaskOut)
    def get_task(request: Request, task_id: str) -> TaskOut:
        owner = resolve_owner_id(request)
        task = kernel.syscalls.get_task(task_id, owner_id=owner)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_out(task)

    @app.post("/v1/tasks/{task_id}/cancel", response_model=TaskOut)
    def cancel_task(request: Request, task_id: str) -> TaskOut:
        owner = resolve_owner_id(request)
        task = kernel.syscalls.cancel_task(task_id, owner_id=owner)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_out(task)

    @app.get("/v1/tasks/{task_id}/events")
    def task_events(request: Request, task_id: str) -> StreamingResponse:
        """SSE stream of task snapshots until terminal status."""
        owner = resolve_owner_id(request)
        task = kernel.syscalls.get_task(task_id, owner_id=owner)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        def event_stream():
            last: str | None = None
            for _ in range(300):
                current = kernel.syscalls.get_task(task_id, owner_id=owner)
                if not current:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Task not found'})}\n\n"
                    break
                payload = _task_out(current).model_dump()
                blob = json.dumps(payload)
                if blob != last:
                    yield f"data: {blob}\n\n"
                    last = blob
                if current.status.value in _TASK_TERMINAL:
                    break
                time.sleep(1.0)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/v1/tasks/{task_id}/artifacts")
    def get_task_artifacts(request: Request, task_id: str) -> dict[str, Any]:
        """Files written during a task (durable DB + disk when present)."""
        owner = resolve_owner_id(request)
        task = kernel.syscalls.get_task(task_id, owner_id=owner)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        durable = kernel.artifacts.list_for_task(task_id, owner_id=owner)
        artifacts = collect_task_artifacts(
            task, kernel.workspace, durable=durable
        )
        return {
            "task_id": task_id,
            "workspace": str(kernel.workspace),
            "count": len(artifacts),
            "artifacts": artifacts,
        }

    @app.get("/v1/projects", response_model=list[ProjectOut])
    def list_projects(request: Request, limit: int = 50) -> list[ProjectOut]:
        owner = resolve_owner_id(request)
        return [
            ProjectOut(**p.__dict__)
            for p in projects.list(limit=limit, owner_id=owner)
        ]

    @app.post("/v1/projects", response_model=ProjectOut)
    def create_project(request: Request, body: ProjectCreate) -> ProjectOut:
        owner = resolve_owner_id(request)
        project = projects.create(body.name, body.description, owner_id=owner)
        return ProjectOut(**project.__dict__)

    @app.get("/v1/projects/{project_id}", response_model=ProjectOut)
    def get_project(request: Request, project_id: str) -> ProjectOut:
        owner = resolve_owner_id(request)
        project = projects.get(project_id, owner_id=owner)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectOut(**project.__dict__)

    @app.delete("/v1/projects/{project_id}")
    def delete_project(request: Request, project_id: str) -> dict[str, bool]:
        owner = resolve_owner_id(request)
        if not projects.delete(project_id, owner_id=owner):
            raise HTTPException(status_code=404, detail="Project not found")
        return {"ok": True}

    @app.get("/v1/pipelines", response_model=list[PipelineOut])
    def list_pipelines(request: Request, limit: int = 50) -> list[PipelineOut]:
        owner = resolve_owner_id(request)
        return [_pipeline_out(p) for p in pipelines.list(limit=limit, owner_id=owner)]

    @app.post("/v1/pipelines", response_model=PipelineOut)
    def create_pipeline(request: Request, body: PipelineCreate) -> PipelineOut:
        owner = resolve_owner_id(request)
        if body.project_id and not projects.get(body.project_id, owner_id=owner):
            raise HTTPException(status_code=400, detail="Unknown project_id")
        try:
            pipeline = pipelines.create(
                name=body.name,
                description=body.description,
                project_id=body.project_id,
                steps=[
                    PipelineStep(goal=s.goal, agent=s.agent) for s in body.steps
                ],
                owner_id=owner,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _pipeline_out(pipeline)

    @app.get("/v1/pipelines/{pipeline_id}", response_model=PipelineOut)
    def get_pipeline(request: Request, pipeline_id: str) -> PipelineOut:
        owner = resolve_owner_id(request)
        pipeline = pipelines.get(pipeline_id, owner_id=owner)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return _pipeline_out(pipeline)

    @app.delete("/v1/pipelines/{pipeline_id}")
    def delete_pipeline(request: Request, pipeline_id: str) -> dict[str, bool]:
        owner = resolve_owner_id(request)
        if not pipelines.delete(pipeline_id, owner_id=owner):
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"ok": True}

    @app.post("/v1/pipelines/{pipeline_id}/runs", response_model=PipelineRunOut)
    def run_pipeline(
        request: Request,
        pipeline_id: str,
        body: PipelineRunCreate,
        wait: bool = True,
    ) -> PipelineRunOut:
        """Start a pipeline run. wait=true blocks until done; wait=false returns running run."""
        owner = resolve_owner_id(request)
        pipeline = pipelines.get(pipeline_id, owner_id=owner)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        run = (
            runner.run(pipeline, body.input_goal)
            if wait
            else runner.start(pipeline, body.input_goal)
        )
        return _run_out(run)

    @app.get("/v1/pipelines/{pipeline_id}/runs", response_model=list[PipelineRunOut])
    def list_pipeline_runs(
        request: Request, pipeline_id: str, limit: int = 50
    ) -> list[PipelineRunOut]:
        owner = resolve_owner_id(request)
        if not pipelines.get(pipeline_id, owner_id=owner):
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return [
            _run_out(r)
            for r in pipelines.list_runs(
                pipeline_id=pipeline_id, limit=limit, owner_id=owner
            )
        ]

    @app.get("/v1/pipeline-runs/{run_id}", response_model=PipelineRunOut)
    def get_pipeline_run(request: Request, run_id: str) -> PipelineRunOut:
        owner = resolve_owner_id(request)
        run = pipelines.get_run(run_id, owner_id=owner)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return _run_out(run)

    @app.get("/v1/pipeline-runs", response_model=list[PipelineRunOut])
    def list_all_pipeline_runs(
        request: Request, limit: int = 50
    ) -> list[PipelineRunOut]:
        owner = resolve_owner_id(request)
        return [
            _run_out(r) for r in pipelines.list_runs(limit=limit, owner_id=owner)
        ]

    @app.get("/v1/knowledge/search", response_model=KnowledgeSearchOut)
    def knowledge_search(
        request: Request,
        q: str = "",
        limit: int = 30,
        kinds: str | None = None,
    ) -> KnowledgeSearchOut:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query parameter q is required")
        kind_set = None
        if kinds:
            kind_set = {k.strip() for k in kinds.split(",") if k.strip()}
        owner = resolve_owner_id(request)
        results = knowledge.search(
            query,
            limit=max(1, min(limit, 100)),
            kinds=kind_set,
            owner_id=owner,
        )
        return KnowledgeSearchOut(
            query=query,
            count=len(results),
            results=[KnowledgeHitOut(**hit.to_dict()) for hit in results],
        )

    @app.get("/v1/models", response_model=list[ModelOut])
    def list_models(request: Request, limit: int = 100) -> list[ModelOut]:
        owner = resolve_owner_id(request)
        return [
            ModelOut(**m.public_dict())
            for m in models.list(limit=limit, owner_id=owner)
        ]

    @app.post("/v1/models", response_model=ModelOut)
    def create_model(request: Request, body: ModelCreate) -> ModelOut:
        owner = resolve_owner_id(request)
        try:
            record = models.create(
                name=body.name,
                provider=body.provider,
                model_id=body.model_id,
                base_url=body.base_url,
                api_key=body.api_key,
                is_default=body.is_default,
                enabled=body.enabled,
                owner_id=owner,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ModelOut(**record.public_dict())

    @app.get("/v1/models/{model_pk}", response_model=ModelOut)
    def get_model(request: Request, model_pk: str) -> ModelOut:
        owner = resolve_owner_id(request)
        record = models.get(model_pk, owner_id=owner)
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.patch("/v1/models/{model_pk}", response_model=ModelOut)
    def update_model(
        request: Request, model_pk: str, body: ModelUpdate
    ) -> ModelOut:
        owner = resolve_owner_id(request)
        record = models.update(
            model_pk,
            name=body.name,
            model_id=body.model_id,
            base_url=body.base_url,
            api_key=body.api_key,
            enabled=body.enabled,
            owner_id=owner,
        )
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.post("/v1/models/{model_pk}/default", response_model=ModelOut)
    def set_default_model(request: Request, model_pk: str) -> ModelOut:
        owner = resolve_owner_id(request)
        record = models.set_default(model_pk, owner_id=owner)
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.delete("/v1/models/{model_pk}")
    def delete_model(request: Request, model_pk: str) -> dict[str, bool]:
        owner = resolve_owner_id(request)
        if not models.delete(model_pk, owner_id=owner):
            raise HTTPException(status_code=404, detail="Model not found")
        return {"ok": True}

    @app.post("/v1/models/{model_pk}/test")
    def test_model(request: Request, model_pk: str) -> dict[str, Any]:
        owner = resolve_owner_id(request)
        record = models.get(model_pk, owner_id=owner)
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        try:
            reply = model_client.complete(
                record,
                system="Reply with exactly: ok",
                user="ping",
                temperature=0,
                timeout=25.0,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": True, "reply": reply[:500]}

    return app
