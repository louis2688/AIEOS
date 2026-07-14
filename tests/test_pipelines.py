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


def test_pipeline_create_and_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    created = client.post(
        "/v1/pipelines",
        json={
            "name": "Design then inspect",
            "description": "Architect outline then engineer hello",
            "steps": [
                {
                    "agent": "architect",
                    "goal": "Outline architecture for: {input}",
                },
                {
                    "agent": "software_engineer",
                    "goal": "hello",
                },
            ],
        },
    )
    assert created.status_code == 200
    pipeline = created.json()
    assert pipeline["name"] == "Design then inspect"
    assert len(pipeline["steps"]) == 2
    pipeline_id = pipeline["id"]

    run = client.post(
        f"/v1/pipelines/{pipeline_id}/runs",
        json={"input_goal": "booking module"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "completed"
    assert len(body["step_results"]) == 2
    assert body["step_results"][0]["status"] == "completed"
    assert body["step_results"][1]["status"] == "completed"
    assert "booking module" in body["step_results"][0]["goal"]

    listed = client.get(f"/v1/pipelines/{pipeline_id}/runs")
    assert listed.status_code == 200
    assert any(r["id"] == body["id"] for r in listed.json())

    got = client.get(f"/v1/pipeline-runs/{body['id']}")
    assert got.status_code == 200
    assert got.json()["pipeline_id"] == pipeline_id


def test_pipeline_requires_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    resp = client.post(
        "/v1/pipelines",
        json={"name": "Empty", "steps": []},
    )
    assert resp.status_code == 422
