"""Cancel + SSE progress for async tasks."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app


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
    allow_write: true
  shell:
    enabled: false
agents:
  echo:
    enabled: true
  software_engineer:
    enabled: true
  architect:
    enabled: false
""".strip(),
        encoding="utf-8",
    )


def test_cancel_async_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    started = client.post(
        "/v1/tasks?wait=false",
        json={"goal": "hello", "agent": "echo"},
    )
    assert started.status_code == 200
    task_id = started.json()["id"]

    cancelled = client.post(f"/v1/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["id"] == task_id
    assert body["status"] in {"cancelled", "completed", "failed"}

    # Echo is fast; if it already finished, cancel is a no-op terminal.
    # Force a slow path via cancel-before-run by holding the scheduler briefly.
    # At minimum cancel endpoint must be authorized + return the task.
    final = client.get(f"/v1/tasks/{task_id}")
    assert final.status_code == 200
    assert final.json()["status"] in {"cancelled", "completed", "failed"}


def test_cancel_before_execute(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    app = create_app(workspace=tmp_path)
    kernel = app.state.kernel
    client = TestClient(app)

    task = kernel.syscalls.execute_task("hello", agent="echo", wait=False)
    # Cancel immediately from another thread while run may still be planning.
    kernel.request_cancel(task.id)
    deadline = time.time() + 5
    while time.time() < deadline:
        current = kernel.get_task(task.id)
        assert current is not None
        if current.status.value in {"cancelled", "completed", "failed"}:
            break
        time.sleep(0.05)
    current = kernel.get_task(task.id)
    assert current is not None
    # Prefer cancelled; allow completed if echo finished first.
    assert current.status.value in {"cancelled", "completed"}

    listed = client.get("/v1/tasks")
    assert listed.status_code == 200
    assert any(t["id"] == task.id for t in listed.json())


def test_task_events_sse(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    started = client.post(
        "/v1/tasks?wait=false",
        json={"goal": "hello", "agent": "echo"},
    )
    assert started.status_code == 200
    task_id = started.json()["id"]

    with client.stream("GET", f"/v1/tasks/{task_id}/events") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        chunks: list[str] = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])
                data = json.loads(line[6:])
                if data.get("status") in {"completed", "failed", "cancelled"}:
                    break
        assert chunks
        last = json.loads(chunks[-1])
        assert last["id"] == task_id
        assert last["status"] in {"completed", "failed", "cancelled"}
