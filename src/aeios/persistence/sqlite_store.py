from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aeios.core.types import Task, TaskStatus
from aeios.persistence.db import SqlDb, coerce_db


class SqliteTaskStore:
    """Task + audit persistence (SQLite by default, Postgres when DATABASE_URL is postgres)."""

    def __init__(self, db: SqlDb | Path) -> None:
        self._db = coerce_db(db)
        self.db_path = self._db.path or Path(self._db.display)
        self._init_schema()

    @property
    def backend(self) -> str:
        return self._db.backend

    def _init_schema(self) -> None:
        serial = self._db.serial_pk("id")
        now = self._db.now_default()
        with self._db.lock():
            self._db.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agent TEXT,
                    plan TEXT NOT NULL DEFAULT '[]',
                    steps TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    {serial},
                    task_id TEXT,
                    event TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '{{}}',
                    created_at TEXT NOT NULL {now}
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
                """
            )
            self._db.commit()

    def save_task(self, task: Task) -> None:
        with self._db.lock():
            self._db.execute(
                """
                INSERT INTO tasks (
                    id, goal, status, agent, plan, steps, result, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal=excluded.goal,
                    status=excluded.status,
                    agent=excluded.agent,
                    plan=excluded.plan,
                    steps=excluded.steps,
                    result=excluded.result,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    task.id,
                    task.goal,
                    task.status.value,
                    task.agent,
                    json.dumps(task.plan),
                    json.dumps(task.steps),
                    task.result,
                    task.error,
                    task.created_at.isoformat()
                    if hasattr(task.created_at, "isoformat")
                    else str(task.created_at),
                    task.updated_at.isoformat()
                    if hasattr(task.updated_at, "isoformat")
                    else str(task.updated_at),
                ),
            )
            self._db.commit()

    def get_task(self, task_id: str) -> Task | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        with self._db.lock():
            rows = self._db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def audit(
        self, event: str, task_id: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        with self._db.lock():
            self._db.execute(
                "INSERT INTO audit_log (task_id, event, detail) VALUES (?, ?, ?)",
                (task_id, event, json.dumps(detail or {})),
            )
            self._db.commit()

    def list_audit(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._db.lock():
            if task_id:
                rows = self._db.execute(
                    "SELECT * FROM audit_log WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def healthy(self) -> bool:
        return self._db.healthy()

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _row_to_task(row: Any) -> Task:
        return Task(
            id=row["id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            agent=row["agent"],
            plan=json.loads(row["plan"] or "[]"),
            steps=json.loads(row["steps"] or "[]"),
            result=row["result"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
