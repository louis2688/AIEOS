from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.persistence.db import SqliteDb
from aeios.persistence.projects import LOCAL_OWNER_ID, ProjectStore


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
    assert body["owner_id"] == LOCAL_OWNER_ID
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


def test_project_store_owner_isolation(tmp_path: Path) -> None:
    db = SqliteDb(tmp_path / "owners.db")
    store = ProjectStore(db)

    a = store.create("Alice Proj", owner_id="user_a")
    b = store.create("Bob Proj", owner_id="user_b")

    assert [p.id for p in store.list(owner_id="user_a")] == [a.id]
    assert [p.id for p in store.list(owner_id="user_b")] == [b.id]
    assert store.get(a.id, owner_id="user_b") is None
    assert store.get(a.id, owner_id="user_a") is not None
    assert store.delete(a.id, owner_id="user_b") is False
    assert store.delete(a.id, owner_id="user_a") is True
    db.close()


def test_project_store_migrates_owner_column(tmp_path: Path) -> None:
    """Existing projects table without owner_id gets ALTER + default."""
    db = SqliteDb(tmp_path / "legacy.db")
    with db.lock():
        db.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        db.execute(
            """
            INSERT INTO projects (id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("legacy1", "Old", "", "t0", "t0"),
        )
        db.commit()

    store = ProjectStore(db)
    row = store.get("legacy1")
    assert row is not None
    assert row.owner_id == LOCAL_OWNER_ID
    created = store.create("New", owner_id="user_x")
    assert created.owner_id == "user_x"
    db.close()
