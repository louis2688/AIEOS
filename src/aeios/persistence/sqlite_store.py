from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from aeios.core.types import Task, TaskStatus


class SqliteTaskStore:
    """SQLite persistence for tasks and audit events."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False: FastAPI may run handlers in worker threads
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                event TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
            """
        )
        self._conn.commit()

    def save_task(self, task: Task) -> None:
        with self._lock:
            self._conn.execute(
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
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def audit(self, event: str, task_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log (task_id, event, detail) VALUES (?, ?, ?)",
                (task_id, event, json.dumps(detail or {})),
            )
            self._conn.commit()

    def list_audit(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            if task_id:
                rows = self._conn.execute(
                    "SELECT * FROM audit_log WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def healthy(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
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
