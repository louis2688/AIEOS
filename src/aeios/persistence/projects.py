from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from aeios.persistence.db import SqlDb, coerce_db


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str


class ProjectStore:
    """Projects persistence (SQLite default, Postgres when configured)."""

    def __init__(self, db: SqlDb | Path) -> None:
        self._db = coerce_db(db)
        self.db_path = self._db.path or Path(self._db.display)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._db.lock():
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._db.commit()

    def create(self, name: str, description: str = "") -> Project:
        project = Project(
            id=uuid4().hex[:12],
            name=name.strip(),
            description=description.strip(),
            created_at=utcnow_iso(),
            updated_at=utcnow_iso(),
        )
        with self._db.lock():
            self._db.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.description,
                    project.created_at,
                    project.updated_at,
                ),
            )
            self._db.commit()
        return project

    def list(self, limit: int = 50) -> list[Project]:
        with self._db.lock():
            rows = self._db.execute(
                "SELECT * FROM projects ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, project_id: str) -> Project | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._row(row) if row else None

    def delete(self, project_id: str) -> bool:
        with self._db.lock():
            cur = self._db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self._db.commit()
            return cur.rowcount > 0

    @staticmethod
    def _row(row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
