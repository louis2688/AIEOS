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
  default_agent: software_engineer
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
  shell:
    enabled: false
agents:
  software_engineer:
    enabled: true
  architect:
    enabled: true
  echo:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_knowledge_search_finds_task_and_pipeline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    task = client.post("/v1/tasks", json={"goal": "design neon billing module"})
    assert task.status_code == 200

    pipeline = client.post(
        "/v1/pipelines",
        json={
            "name": "Billing flow",
            "description": "Neon billing research pipeline",
            "steps": [
                {"agent": "architect", "goal": "Outline: {input}"},
                {"agent": "software_engineer", "goal": "hello"},
            ],
        },
    )
    assert pipeline.status_code == 200
    pipeline_id = pipeline.json()["id"]

    run = client.post(
        f"/v1/pipelines/{pipeline_id}/runs",
        json={"input_goal": "neon billing"},
    )
    assert run.status_code == 200

    project = client.post(
        "/v1/projects",
        json={"name": "Neon", "description": "Billing workspace"},
    )
    assert project.status_code == 200

    resp = client.get("/v1/knowledge/search", params={"q": "neon billing", "limit": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "neon billing"
    assert body["count"] >= 1
    kinds = {r["kind"] for r in body["results"]}
    assert "task" in kinds or "pipeline" in kinds or "pipeline_run" in kinds

    empty = client.get("/v1/knowledge/search", params={"q": ""})
    assert empty.status_code == 400
