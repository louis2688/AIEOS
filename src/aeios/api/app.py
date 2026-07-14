from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from aeios.core.kernel import Kernel


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


def create_app(workspace: Path | None = None) -> FastAPI:
    kernel = Kernel(workspace=workspace or Path.cwd())
    app = FastAPI(title="AEIOS API", version="0.2.0")
    app.state.kernel = kernel

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

    return app
