from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aeios.api.auth import ClerkAuthMiddleware, ClerkJWTVerifier
from aeios.config import Settings, get_settings
from aeios.core.kernel import Kernel
from aeios.core.pipeline_runner import PipelineRunner
from aeios.knowledge.search import KnowledgeSearch
from aeios.models.client import ModelClient
from aeios.observability.metrics import get_metrics
from aeios.observability.request_id import RequestIdMiddleware
from aeios.persistence.pipelines import PipelineStep, PipelineStore
from aeios.persistence.projects import ProjectStore


class TaskCreate(BaseModel):
    goal: str = Field(..., min_length=1)
    agent: str | None = None


class TaskOut(BaseModel):
    id: str
    goal: str
    status: str
    agent: str | None
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
    created_at: str
    updated_at: str


def _pipeline_out(p: Any) -> PipelineOut:
    return PipelineOut(
        id=p.id,
        name=p.name,
        description=p.description,
        project_id=p.project_id,
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
    def create_task(body: TaskCreate) -> TaskOut:
        task = kernel.syscalls.execute_task(body.goal, agent=body.agent)
        return TaskOut(**task.model_dump(mode="json"))

    @app.get("/v1/tasks", response_model=list[TaskOut])
    def list_tasks(limit: int = 50) -> list[TaskOut]:
        tasks = kernel.syscalls.list_tasks(limit=limit)
        return [TaskOut(**t.model_dump(mode="json")) for t in tasks]

    @app.get("/v1/tasks/{task_id}", response_model=TaskOut)
    def get_task(task_id: str) -> TaskOut:
        task = kernel.syscalls.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskOut(**task.model_dump(mode="json"))

    @app.get("/v1/projects", response_model=list[ProjectOut])
    def list_projects(limit: int = 50) -> list[ProjectOut]:
        return [ProjectOut(**p.__dict__) for p in projects.list(limit=limit)]

    @app.post("/v1/projects", response_model=ProjectOut)
    def create_project(body: ProjectCreate) -> ProjectOut:
        project = projects.create(body.name, body.description)
        return ProjectOut(**project.__dict__)

    @app.get("/v1/projects/{project_id}", response_model=ProjectOut)
    def get_project(project_id: str) -> ProjectOut:
        project = projects.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectOut(**project.__dict__)

    @app.delete("/v1/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, bool]:
        if not projects.delete(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return {"ok": True}

    @app.get("/v1/pipelines", response_model=list[PipelineOut])
    def list_pipelines(limit: int = 50) -> list[PipelineOut]:
        return [_pipeline_out(p) for p in pipelines.list(limit=limit)]

    @app.post("/v1/pipelines", response_model=PipelineOut)
    def create_pipeline(body: PipelineCreate) -> PipelineOut:
        if body.project_id and not projects.get(body.project_id):
            raise HTTPException(status_code=400, detail="Unknown project_id")
        try:
            pipeline = pipelines.create(
                name=body.name,
                description=body.description,
                project_id=body.project_id,
                steps=[
                    PipelineStep(goal=s.goal, agent=s.agent) for s in body.steps
                ],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _pipeline_out(pipeline)

    @app.get("/v1/pipelines/{pipeline_id}", response_model=PipelineOut)
    def get_pipeline(pipeline_id: str) -> PipelineOut:
        pipeline = pipelines.get(pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return _pipeline_out(pipeline)

    @app.delete("/v1/pipelines/{pipeline_id}")
    def delete_pipeline(pipeline_id: str) -> dict[str, bool]:
        if not pipelines.delete(pipeline_id):
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"ok": True}

    @app.post("/v1/pipelines/{pipeline_id}/runs", response_model=PipelineRunOut)
    def run_pipeline(pipeline_id: str, body: PipelineRunCreate) -> PipelineRunOut:
        pipeline = pipelines.get(pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        run = runner.run(pipeline, body.input_goal)
        return _run_out(run)

    @app.get("/v1/pipelines/{pipeline_id}/runs", response_model=list[PipelineRunOut])
    def list_pipeline_runs(pipeline_id: str, limit: int = 50) -> list[PipelineRunOut]:
        if not pipelines.get(pipeline_id):
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return [_run_out(r) for r in pipelines.list_runs(pipeline_id=pipeline_id, limit=limit)]

    @app.get("/v1/pipeline-runs/{run_id}", response_model=PipelineRunOut)
    def get_pipeline_run(run_id: str) -> PipelineRunOut:
        run = pipelines.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return _run_out(run)

    @app.get("/v1/pipeline-runs", response_model=list[PipelineRunOut])
    def list_all_pipeline_runs(limit: int = 50) -> list[PipelineRunOut]:
        return [_run_out(r) for r in pipelines.list_runs(limit=limit)]

    @app.get("/v1/knowledge/search", response_model=KnowledgeSearchOut)
    def knowledge_search(
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
        results = knowledge.search(query, limit=max(1, min(limit, 100)), kinds=kind_set)
        return KnowledgeSearchOut(
            query=query,
            count=len(results),
            results=[KnowledgeHitOut(**hit.to_dict()) for hit in results],
        )

    @app.get("/v1/models", response_model=list[ModelOut])
    def list_models(limit: int = 100) -> list[ModelOut]:
        return [ModelOut(**m.public_dict()) for m in models.list(limit=limit)]

    @app.post("/v1/models", response_model=ModelOut)
    def create_model(body: ModelCreate) -> ModelOut:
        try:
            record = models.create(
                name=body.name,
                provider=body.provider,
                model_id=body.model_id,
                base_url=body.base_url,
                api_key=body.api_key,
                is_default=body.is_default,
                enabled=body.enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ModelOut(**record.public_dict())

    @app.get("/v1/models/{model_pk}", response_model=ModelOut)
    def get_model(model_pk: str) -> ModelOut:
        record = models.get(model_pk)
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.patch("/v1/models/{model_pk}", response_model=ModelOut)
    def update_model(model_pk: str, body: ModelUpdate) -> ModelOut:
        record = models.update(
            model_pk,
            name=body.name,
            model_id=body.model_id,
            base_url=body.base_url,
            api_key=body.api_key,
            enabled=body.enabled,
        )
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.post("/v1/models/{model_pk}/default", response_model=ModelOut)
    def set_default_model(model_pk: str) -> ModelOut:
        record = models.set_default(model_pk)
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")
        return ModelOut(**record.public_dict())

    @app.delete("/v1/models/{model_pk}")
    def delete_model(model_pk: str) -> dict[str, bool]:
        if not models.delete(model_pk):
            raise HTTPException(status_code=404, detail="Model not found")
        return {"ok": True}

    @app.post("/v1/models/{model_pk}/test")
    def test_model(model_pk: str) -> dict[str, Any]:
        record = models.get(model_pk)
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
