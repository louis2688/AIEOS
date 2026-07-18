"""Async task / pipeline run start + poll."""

from __future__ import annotations

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
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_create_task_wait_false_then_completes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    created = client.post("/v1/tasks?wait=false", json={"goal": "hello", "agent": "echo"})
    assert created.status_code == 200
    body = created.json()
    task_id = body["id"]
    assert body["status"] in {"pending", "planning", "running", "completed"}

    deadline = time.time() + 10
    status = body["status"]
    while status not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.05)
        status = client.get(f"/v1/tasks/{task_id}").json()["status"]

    final = client.get(f"/v1/tasks/{task_id}").json()
    assert final["status"] == "completed"


def test_pipeline_run_wait_false(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    pipe = client.post(
        "/v1/pipelines",
        json={"name": "p", "steps": [{"goal": "hello", "agent": "echo"}]},
    ).json()
    started = client.post(
        f"/v1/pipelines/{pipe['id']}/runs?wait=false",
        json={"input_goal": "hi"},
    )
    assert started.status_code == 200
    run = started.json()
    assert run["status"] in {"running", "completed", "failed"}
    run_id = run["id"]

    deadline = time.time() + 15
    status = run["status"]
    while status not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.05)
        status = client.get(f"/v1/pipeline-runs/{run_id}").json()["status"]

    final = client.get(f"/v1/pipeline-runs/{run_id}").json()
    assert final["status"] == "completed"
