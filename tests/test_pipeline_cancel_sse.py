"""Cancel + SSE progress for async pipeline runs."""

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
    allow_write: false
  shell:
    enabled: false
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


def _create_pipeline(client: TestClient) -> str:
    created = client.post(
        "/v1/pipelines",
        json={
            "name": "Echo chain",
            "steps": [
                {"goal": "hello step1", "agent": "echo"},
                {"goal": "hello step2", "agent": "echo"},
            ],
        },
    )
    assert created.status_code == 200
    return created.json()["id"]


def test_cancel_pipeline_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    pipeline_id = _create_pipeline(client)

    started = client.post(
        f"/v1/pipelines/{pipeline_id}/runs?wait=false",
        json={"input_goal": "hello"},
    )
    assert started.status_code == 200
    run_id = started.json()["id"]

    cancelled = client.post(f"/v1/pipeline-runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["id"] == run_id
    assert body["status"] in {"cancelled", "completed", "failed"}

    deadline = time.time() + 5
    while time.time() < deadline:
        final = client.get(f"/v1/pipeline-runs/{run_id}").json()
        if final["status"] in {"cancelled", "completed", "failed"}:
            break
        time.sleep(0.05)
    final = client.get(f"/v1/pipeline-runs/{run_id}").json()
    assert final["status"] in {"cancelled", "completed", "failed"}


def test_cancel_between_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    app = create_app(workspace=tmp_path)
    client = TestClient(app)
    from aeios.core.pipeline_runner import PipelineRunner
    from aeios.persistence.pipelines import PipelineStep

    pipelines = app.state.pipelines
    runner = PipelineRunner(app.state.kernel, pipelines)
    pipe = pipelines.create(
        name="Slow-ish",
        description="",
        steps=[
            PipelineStep(goal="hello a", agent="echo"),
            PipelineStep(goal="hello b", agent="echo"),
        ],
        owner_id="local",
    )
    started = runner.start(pipe, "hello")
    cancelled = runner.request_cancel(started.id)
    assert cancelled is not None
    deadline = time.time() + 5
    while time.time() < deadline:
        current = pipelines.get_run(started.id)
        assert current is not None
        if current.status in {"cancelled", "completed", "failed"}:
            break
        time.sleep(0.05)
    current = pipelines.get_run(started.id)
    assert current is not None
    assert current.status in {"cancelled", "completed"}
    listed = client.get("/v1/pipeline-runs")
    assert listed.status_code == 200
    assert any(r["id"] == started.id for r in listed.json())


def test_pipeline_run_events_sse(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    pipeline_id = _create_pipeline(client)

    started = client.post(
        f"/v1/pipelines/{pipeline_id}/runs?wait=false",
        json={"input_goal": "hello"},
    )
    assert started.status_code == 200
    run_id = started.json()["id"]

    with client.stream("GET", f"/v1/pipeline-runs/{run_id}/events") as resp:
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
        assert last["id"] == run_id
        assert last["status"] in {"completed", "failed", "cancelled"}


def test_cancel_unknown_run_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    assert client.post("/v1/pipeline-runs/doesnotexist/cancel").status_code == 404
    assert client.get("/v1/pipeline-runs/doesnotexist/events").status_code == 404
