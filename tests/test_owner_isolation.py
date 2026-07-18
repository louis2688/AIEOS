"""Per-user isolation for tasks, models, pipelines, and knowledge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.api.auth import resolve_owner_id
from aeios.config import Settings
from aeios.knowledge.search import KnowledgeSearch
from aeios.persistence.pipelines import PipelineStep, PipelineStore
from aeios.persistence.projects import ProjectStore
from aeios.planning.planner import Planner


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: echo
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
    allow_write: false
agents:
  echo:
    enabled: true
  software_engineer:
    enabled: false
  architect:
    enabled: false
""".strip(),
        encoding="utf-8",
    )


def test_tasks_scoped_by_owner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    app = create_app(workspace=tmp_path)
    kernel = app.state.kernel

    a = kernel.syscalls.execute_task("hello a", agent="echo", owner_id="user-a")
    b = kernel.syscalls.execute_task("hello b", agent="echo", owner_id="user-b")

    assert kernel.get_task(a.id, owner_id="user-a") is not None
    assert kernel.get_task(a.id, owner_id="user-b") is None
    assert kernel.get_task(b.id, owner_id="user-b") is not None

    listed_a = kernel.list_tasks(owner_id="user-a")
    assert {t.id for t in listed_a} == {a.id}


def test_models_scoped_by_owner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    # Avoid seeding env keys into both owners
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(workspace=tmp_path)
    models = app.state.models

    m_a = models.create(
        name="A model",
        provider="openai",
        model_id="gpt-4o-mini",
        owner_id="user-a",
        is_default=True,
    )
    m_b = models.create(
        name="B model",
        provider="openai",
        model_id="gpt-4o-mini",
        owner_id="user-b",
        is_default=True,
    )

    assert models.get(m_a.id, owner_id="user-a") is not None
    assert models.get(m_a.id, owner_id="user-b") is None
    assert models.get_default(owner_id="user-a").id == m_a.id
    assert models.get_default(owner_id="user-b").id == m_b.id
    assert models.delete(m_a.id, owner_id="user-b") is False
    assert models.delete(m_a.id, owner_id="user-a") is True


def test_api_tasks_use_resolve_owner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    # Auth disabled → owner "local"
    created = client.post("/v1/tasks", json={"goal": "hello", "agent": "echo"})
    assert created.status_code == 200
    assert created.json().get("owner_id", "local") == "local"
    listed = client.get("/v1/tasks")
    assert listed.status_code == 200
    assert all(t.get("owner_id", "local") == "local" for t in listed.json())


def test_resolve_owner_id_local_default() -> None:
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    assert resolve_owner_id(request) == "local"


def test_pipelines_and_runs_scoped_by_owner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    app = create_app(workspace=tmp_path)
    pipelines: PipelineStore = app.state.pipelines

    pipe_a = pipelines.create(
        name="A pipe",
        description="alpha secret pipeline",
        steps=[PipelineStep(goal="hello", agent="echo")],
        owner_id="user-a",
    )
    pipe_b = pipelines.create(
        name="B pipe",
        description="beta secret pipeline",
        steps=[PipelineStep(goal="hello", agent="echo")],
        owner_id="user-b",
    )
    run_a = pipelines.create_run(pipe_a.id, "alpha goal neon")
    run_a.status = "completed"
    run_a.result = "alpha result"
    pipelines.save_run(run_a)

    assert pipelines.get(pipe_a.id, owner_id="user-a") is not None
    assert pipelines.get(pipe_a.id, owner_id="user-b") is None
    assert pipelines.get_run(run_a.id, owner_id="user-a") is not None
    assert pipelines.get_run(run_a.id, owner_id="user-b") is None
    assert {p.id for p in pipelines.list(owner_id="user-a")} == {pipe_a.id}
    assert {p.id for p in pipelines.list(owner_id="user-b")} == {pipe_b.id}


def test_knowledge_search_owner_isolation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    app = create_app(workspace=tmp_path)
    kernel = app.state.kernel
    pipelines: PipelineStore = app.state.pipelines
    projects: ProjectStore = app.state.projects
    knowledge = KnowledgeSearch(kernel, pipelines, projects)

    # Shared memory must not leak across signed-in tenants.
    kernel.memory.set("shared_secret_key", "unique-memory-token-xyz")

    pipe_a = pipelines.create(
        name="Alice neon pipe",
        description="alice-only neon billing",
        steps=[PipelineStep(goal="hello", agent="echo")],
        owner_id="user-a",
    )
    pipelines.create(
        name="Bob other pipe",
        description="bob-only widget factory",
        steps=[PipelineStep(goal="hello", agent="echo")],
        owner_id="user-b",
    )
    kernel.artifacts.upsert(
        task_id="task-a1",
        path="ALICE_SECRET.md",
        content="alice artifact neon content",
        owner_id="user-a",
    )
    kernel.artifacts.upsert(
        task_id="task-b1",
        path="BOB_SECRET.md",
        content="bob artifact widget content",
        owner_id="user-b",
    )

    hits_a = knowledge.search("neon", owner_id="user-a")
    kinds_a = {h.kind for h in hits_a}
    ids_a = {h.id for h in hits_a}
    assert pipe_a.id in ids_a or any(h.kind == "pipeline" for h in hits_a)
    assert "memory" not in kinds_a
    assert all(
        h.meta.get("task_id") != "task-b1" for h in hits_a if h.kind == "artifact"
    )
    assert any(h.kind == "artifact" and "ALICE" in h.title for h in hits_a)

    hits_b = knowledge.search("widget", owner_id="user-b")
    assert all(h.kind != "pipeline" or "Alice" not in h.title for h in hits_b)
    assert any(h.kind == "artifact" and "BOB" in h.title for h in hits_b)
    assert "memory" not in {h.kind for h in hits_b}

    # Local / auth-off may still see shared memory.
    local_hits = knowledge.search("unique-memory-token-xyz", owner_id="local")
    assert any(h.kind == "memory" for h in local_hits)


def test_planner_no_env_fallback_for_signed_in_owner(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    settings = Settings(openai_api_key="sk-should-not-be-used")
    store = MagicMock()
    store.get_default.return_value = None
    planner = Planner(settings=settings, model_store=store)
    planner.client = MagicMock()

    plan = planner.plan(
        "implement feature X",
        agent_role="software_engineer",
        owner_id="user-alice",
    )
    # Deterministic plan — no silent env-key LLM call for signed-in owners.
    planner.client.complete.assert_not_called()
    assert plan == planner.deterministic_plan(
        "implement feature X", agent_role="software_engineer"
    )

    # Local / auth-off still allowed to use env key.
    planner.client.complete.return_value = '["Env step one", "Env step two"]'
    local_plan = planner.plan(
        "implement feature Y",
        agent_role="software_engineer",
        owner_id="local",
    )
    planner.client.complete.assert_called_once()
    assert local_plan == ["Env step one", "Env step two"]
