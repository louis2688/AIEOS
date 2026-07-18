from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from aeios.persistence.db import SqlDb, coerce_db


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineStep:
    goal: str
    agent: str = "software_engineer"


@dataclass
class Pipeline:
    id: str
    name: str
    description: str
    project_id: str | None
    steps: list[PipelineStep]
    created_at: str
    updated_at: str


@dataclass
class PipelineRun:
    id: str
    pipeline_id: str
    status: str
    input_goal: str
    step_results: list[dict[str, Any]] = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""


class PipelineStore:
    """Pipelines + runs persistence (SQLite default, Postgres when configured)."""

    def __init__(self, db: SqlDb | Path) -> None:
        self._db = coerce_db(db)
        self.db_path = self._db.path or Path(self._db.display)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._db.lock():
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipelines (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    steps TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id TEXT PRIMARY KEY,
                    pipeline_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_goal TEXT NOT NULL,
                    step_results TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline
                    ON pipeline_runs(pipeline_id);
                """
            )
            self._db.commit()

    def create(
        self,
        name: str,
        steps: list[PipelineStep],
        description: str = "",
        project_id: str | None = None,
    ) -> Pipeline:
        if not steps:
            raise ValueError("Pipeline requires at least one step")
        now = utcnow_iso()
        pipeline = Pipeline(
            id=uuid4().hex[:12],
            name=name.strip(),
            description=description.strip(),
            project_id=project_id,
            steps=steps,
            created_at=now,
            updated_at=now,
        )
        with self._db.lock():
            self._db.execute(
                """
                INSERT INTO pipelines
                    (id, name, description, project_id, steps, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pipeline.id,
                    pipeline.name,
                    pipeline.description,
                    pipeline.project_id,
                    json.dumps([s.__dict__ for s in pipeline.steps]),
                    pipeline.created_at,
                    pipeline.updated_at,
                ),
            )
            self._db.commit()
        return pipeline

    def list(self, limit: int = 50) -> list[Pipeline]:
        with self._db.lock():
            rows = self._db.execute(
                "SELECT * FROM pipelines ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._pipeline_row(r) for r in rows]

    def get(self, pipeline_id: str) -> Pipeline | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)
            ).fetchone()
        return self._pipeline_row(row) if row else None

    def delete(self, pipeline_id: str) -> bool:
        with self._db.lock():
            cur = self._db.execute(
                "DELETE FROM pipelines WHERE id = ?", (pipeline_id,)
            )
            self._db.execute(
                "DELETE FROM pipeline_runs WHERE pipeline_id = ?", (pipeline_id,)
            )
            self._db.commit()
            return cur.rowcount > 0

    def create_run(self, pipeline_id: str, input_goal: str) -> PipelineRun:
        now = utcnow_iso()
        run = PipelineRun(
            id=uuid4().hex[:12],
            pipeline_id=pipeline_id,
            status="pending",
            input_goal=input_goal.strip(),
            step_results=[],
            created_at=now,
            updated_at=now,
        )
        with self._db.lock():
            self._db.execute(
                """
                INSERT INTO pipeline_runs
                    (id, pipeline_id, status, input_goal, step_results, result, error,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.pipeline_id,
                    run.status,
                    run.input_goal,
                    json.dumps(run.step_results),
                    run.result,
                    run.error,
                    run.created_at,
                    run.updated_at,
                ),
            )
            self._db.commit()
        return run

    def save_run(self, run: PipelineRun) -> None:
        run.updated_at = utcnow_iso()
        with self._db.lock():
            self._db.execute(
                """
                UPDATE pipeline_runs SET
                    status = ?,
                    step_results = ?,
                    result = ?,
                    error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    run.status,
                    json.dumps(run.step_results),
                    run.result,
                    run.error,
                    run.updated_at,
                    run.id,
                ),
            )
            self._db.commit()

    def get_run(self, run_id: str) -> PipelineRun | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_row(row) if row else None

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50) -> list[PipelineRun]:
        with self._db.lock():
            if pipeline_id:
                rows = self._db.execute(
                    """
                    SELECT * FROM pipeline_runs
                    WHERE pipeline_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (pipeline_id, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._run_row(r) for r in rows]

    @staticmethod
    def _pipeline_row(row) -> Pipeline:
        raw_steps = json.loads(row["steps"] or "[]")
        steps = [
            PipelineStep(
                goal=str(s.get("goal", "")),
                agent=str(s.get("agent") or "software_engineer"),
            )
            for s in raw_steps
        ]
        return Pipeline(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            project_id=row["project_id"],
            steps=steps,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _run_row(row) -> PipelineRun:
        return PipelineRun(
            id=row["id"],
            pipeline_id=row["pipeline_id"],
            status=row["status"],
            input_goal=row["input_goal"],
            step_results=json.loads(row["step_results"] or "[]"),
            result=row["result"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
