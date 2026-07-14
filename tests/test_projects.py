from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text("{}", encoding="utf-8")


def test_projects_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    created = client.post(
        "/v1/projects",
        json={"name": "Demo", "description": "Phase 2 project"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "Demo"
    project_id = body["id"]

    listed = client.get("/v1/projects")
    assert listed.status_code == 200
    assert any(p["id"] == project_id for p in listed.json())

    got = client.get(f"/v1/projects/{project_id}")
    assert got.status_code == 200
    assert got.json()["description"] == "Phase 2 project"

    deleted = client.delete(f"/v1/projects/{project_id}")
    assert deleted.status_code == 200
    assert client.get(f"/v1/projects/{project_id}").status_code == 404
