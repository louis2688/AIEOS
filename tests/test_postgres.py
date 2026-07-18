"""Postgres integration — skipped unless psycopg is installed and DB is reachable."""

from __future__ import annotations

import os

import pytest

from aeios.core.types import Task, TaskStatus
from aeios.persistence.db import PostgresDb, is_postgres_url, open_db
from aeios.persistence.models import ModelStore
from aeios.persistence.pipelines import PipelineStep, PipelineStore
from aeios.persistence.projects import ProjectStore
from aeios.persistence.sqlite_store import SqliteTaskStore

psycopg = pytest.importorskip("psycopg")

PG_URL = os.environ.get(
    "AEIOS_TEST_DATABASE_URL",
    "postgresql://aeios:aeios@localhost:5432/aeios",
)


def _pg_reachable() -> bool:
    if not is_postgres_url(PG_URL):
        return False
    try:
        with psycopg.connect(PG_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _pg_reachable(),
    reason="Postgres not reachable (start docker compose postgres or set AEIOS_TEST_DATABASE_URL)",
)


def test_postgres_task_project_pipeline_roundtrip(tmp_path) -> None:
    db = open_db(PG_URL, workspace=tmp_path, data_dir=tmp_path / "data")
    assert isinstance(db, PostgresDb)
    assert db.healthy()

    tasks = SqliteTaskStore(db)
    task = Task(goal="pg goal", status=TaskStatus.COMPLETED, result="ok")
    tasks.save_task(task)
    assert tasks.get_task(task.id) is not None
    tasks.audit("test_event", task_id=task.id, detail={"k": 1})
    assert any(a["event"] == "test_event" for a in tasks.list_audit(task_id=task.id))

    projects = ProjectStore(db)
    p = projects.create("PG Project", "from test")
    assert projects.get(p.id) is not None

    pipelines = PipelineStore(db)
    pipe = pipelines.create(
        "PG Pipe",
        [PipelineStep(goal="hello", agent="echo")],
        description="d",
        project_id=p.id,
    )
    run = pipelines.create_run(pipe.id, "input")
    run.status = "completed"
    run.result = "done"
    pipelines.save_run(run)
    assert pipelines.get_run(run.id) is not None

    models = ModelStore(db, secrets_key="pg-test-seal-key-32chars!!!!!!!!")
    rec = models.create(
        name="Ollama local",
        provider="ollama",
        model_id="llama3.2",
        api_key=None,
        is_default=True,
    )
    assert models.get(rec.id) is not None
    db.close()
