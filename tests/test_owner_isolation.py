"""Per-user isolation for tasks and models."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.api.auth import resolve_owner_id


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
