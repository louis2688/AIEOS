from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aeios.core.kernel import Kernel
from aeios.core.pipeline_runner import PipelineRunner
from aeios.knowledge.search import KnowledgeSearch
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


def create_app(workspace: Path | None = None) -> FastAPI:
    root = workspace or Path.cwd()
    kernel = Kernel(workspace=root)
    db_path = kernel.data_dir / "aeios.db"
    projects = ProjectStore(db_path)
    pipelines = PipelineStore(db_path)
    runner = PipelineRunner(kernel, pipelines)
    knowledge = KnowledgeSearch(kernel, pipelines, projects)

    app = FastAPI(title="AEIOS API", version="0.6.0")
    app.state.kernel = kernel
    app.state.projects = projects
    app.state.pipelines = pipelines
    app.state.knowledge = knowledge

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "aeios"}

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

    return app
