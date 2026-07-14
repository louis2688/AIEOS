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
  echo:
    enabled: true
  architect:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_api_task_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    health = client.get("/health")
    assert health.status_code == 200

    created = client.post("/v1/tasks", json={"goal": "hello"})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "completed"
    task_id = body["id"]

    listed = client.get("/v1/tasks")
    assert listed.status_code == 200
    assert any(t["id"] == task_id for t in listed.json())

    got = client.get(f"/v1/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["goal"] == "hello"
