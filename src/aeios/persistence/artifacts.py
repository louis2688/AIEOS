from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from aeios.persistence.db import SqlDb, coerce_db


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactStore:
    """Durable file artifacts keyed by task (survives ephemeral disk)."""

    def __init__(self, db: SqlDb | Path) -> None:
        self._db = coerce_db(db)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._db.lock():
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL DEFAULT 'local',
                    path TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_task_path
                    ON artifacts(task_id, path);
                """
            )
            self._db.commit()

    def upsert(
        self,
        *,
        task_id: str,
        path: str,
        content: str,
        owner_id: str = "local",
    ) -> dict[str, Any]:
        rel = path.replace("\\", "/").lstrip("./")
        data = content if isinstance(content, str) else str(content)
        # Cap stored content at 512 KiB
        encoded = data.encode("utf-8")
        if len(encoded) > 512 * 1024:
            data = encoded[: 512 * 1024].decode("utf-8", errors="replace")
            encoded = data.encode("utf-8")
        now = utcnow_iso()
        art_id = uuid4().hex[:12]
        with self._db.lock():
            existing = self._db.execute(
                "SELECT id FROM artifacts WHERE task_id = ? AND path = ?",
                (task_id, rel),
            ).fetchone()
            if existing:
                art_id = existing["id"]
                self._db.execute(
                    """
                    UPDATE artifacts
                    SET content = ?, bytes = ?, owner_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (data, len(encoded), owner_id, now, art_id),
                )
            else:
                self._db.execute(
                    """
                    INSERT INTO artifacts
                        (id, task_id, owner_id, path, content, bytes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (art_id, task_id, owner_id, rel, data, len(encoded), now, now),
                )
            self._db.commit()
        return {
            "id": art_id,
            "task_id": task_id,
            "owner_id": owner_id,
            "path": rel,
            "bytes": len(encoded),
            "content": data,
            "exists": True,
            "source": "db",
            "ephemeral_note": None,
        }

    def list_for_task(
        self, task_id: str, *, owner_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._db.lock():
            if owner_id is not None:
                rows = self._db.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE task_id = ? AND owner_id = ?
                    ORDER BY path
                    """,
                    (task_id, owner_id),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM artifacts WHERE task_id = ? ORDER BY path",
                    (task_id,),
                ).fetchall()
        return [self._row_dict(r) for r in rows]

    def list(
        self, *, limit: int = 500, owner_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List recent artifacts, optionally scoped to an owner."""
        lim = max(1, min(int(limit), 2000))
        with self._db.lock():
            if owner_id is not None:
                rows = self._db.execute(
                    """
                    SELECT * FROM artifacts
                    WHERE owner_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (owner_id, lim),
                ).fetchall()
            else:
                rows = self._db.execute(
                    """
                    SELECT * FROM artifacts
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        return [self._row_dict(r) for r in rows]

    @staticmethod
    def _row_dict(r: Any) -> dict[str, Any]:
        return {
            "id": r["id"],
            "task_id": r["task_id"],
            "owner_id": r["owner_id"],
            "path": r["path"],
            "bytes": r["bytes"],
            "content": r["content"],
            "exists": True,
            "source": "db",
            "ephemeral_note": None,
        }
