from pathlib import Path

from aeios.core.types import Task, TaskStatus
from aeios.persistence.db import (
    SqliteDb,
    is_postgres_url,
    is_sqlite_url,
    normalize_postgres_url,
    open_db,
    resolve_sqlite_path,
)
from aeios.persistence.projects import ProjectStore
from aeios.persistence.sqlite_store import SqliteTaskStore


def test_url_helpers() -> None:
    assert is_sqlite_url("sqlite:///./data/aeios.db")
    assert is_postgres_url("postgresql://aeios:aeios@localhost:5432/aeios")
    assert is_postgres_url("postgres://aeios:aeios@localhost:5432/aeios")
    assert is_postgres_url("postgresql+psycopg://aeios:x@localhost/aeios")
    assert not is_postgres_url("sqlite:///./data/aeios.db")
    assert (
        normalize_postgres_url("postgresql+psycopg://u:p@h/db")
        == "postgresql://u:p@h/db"
    )


def test_resolve_sqlite_path(tmp_path: Path) -> None:
    p = resolve_sqlite_path("sqlite:///./data/aeios.db", tmp_path / "data", tmp_path)
    assert p == tmp_path / "data" / "aeios.db"
    fallback = resolve_sqlite_path("postgresql://x", tmp_path / "data", tmp_path)
    assert fallback == tmp_path / "data" / "aeios.db"


def test_open_db_sqlite_default(tmp_path: Path) -> None:
    db = open_db(
        "sqlite:///./data/aeios.db",
        workspace=tmp_path,
        data_dir=tmp_path / "data",
    )
    assert db.backend == "sqlite"
    assert db.healthy()
    store = SqliteTaskStore(db)
    task = Task(goal="persist me", status=TaskStatus.COMPLETED)
    store.save_task(task)
    loaded = store.get_task(task.id)
    assert loaded is not None
    assert loaded.goal == "persist me"
    projects = ProjectStore(db)
    proj = projects.create("Demo", "desc")
    assert projects.get(proj.id) is not None
    db.close()


def test_sqlite_db_placeholder_roundtrip(tmp_path: Path) -> None:
    db = SqliteDb(tmp_path / "t.db")
    with db.lock():
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, n INTEGER);
            """
        )
        db.commit()
        db.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        db.commit()
        row = db.execute("SELECT * FROM t WHERE id = ?", ("a",)).fetchone()
    assert row is not None
    assert row["n"] == 1
    db.close()


def test_postgres_import_skipped_without_extra() -> None:
    """Factory raises a clear error only when opening a postgres URL without psycopg."""
    import importlib.util

    if importlib.util.find_spec("psycopg") is not None:
        return  # installed — covered by test_postgres.py instead
    from aeios.persistence.db import PostgresDb
    import pytest

    with pytest.raises(ImportError, match="aeios\\[postgres\\]"):
        PostgresDb("postgresql://aeios:aeios@localhost:5432/aeios")
