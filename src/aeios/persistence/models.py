from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROVIDERS = frozenset({"openai", "anthropic", "ollama"})


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}…{value[-4:]}"


@dataclass
class ModelRecord:
    id: str
    name: str
    provider: str
    model_id: str
    base_url: str | None
    api_key: str | None
    is_default: bool
    enabled: bool
    created_at: str
    updated_at: str

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "api_key_set": bool(self.api_key),
            "api_key_masked": mask_secret(self.api_key),
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ModelStore:
    """SQLite registry for LLM providers / models."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                base_url TEXT,
                api_key TEXT,
                is_default INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_models_default ON models(is_default);
            """
        )
        self._conn.commit()

    def create(
        self,
        *,
        name: str,
        provider: str,
        model_id: str,
        base_url: str | None = None,
        api_key: str | None = None,
        is_default: bool = False,
        enabled: bool = True,
    ) -> ModelRecord:
        provider = provider.strip().lower()
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Use {sorted(PROVIDERS)}")
        if provider == "ollama" and not (base_url or "").strip():
            base_url = "http://127.0.0.1:11434/v1"
        if provider == "openai" and not (base_url or "").strip():
            base_url = "https://api.openai.com/v1"
        if provider == "anthropic" and not (base_url or "").strip():
            base_url = "https://api.anthropic.com"

        now = utcnow_iso()
        record = ModelRecord(
            id=uuid4().hex[:12],
            name=name.strip(),
            provider=provider,
            model_id=model_id.strip(),
            base_url=(base_url or "").strip() or None,
            api_key=(api_key or "").strip() or None,
            is_default=is_default,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            if record.is_default:
                self._conn.execute("UPDATE models SET is_default = 0")
            self._conn.execute(
                """
                INSERT INTO models
                    (id, name, provider, model_id, base_url, api_key,
                     is_default, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.name,
                    record.provider,
                    record.model_id,
                    record.base_url,
                    record.api_key,
                    1 if record.is_default else 0,
                    1 if record.enabled else 0,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._conn.commit()
        return record

    def list(self, limit: int = 100) -> list[ModelRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM models ORDER BY is_default DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, model_id: str) -> ModelRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return self._row(row) if row else None

    def get_default(self) -> ModelRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM models
                WHERE is_default = 1 AND enabled = 1
                LIMIT 1
                """
            ).fetchone()
            if row:
                return self._row(row)
            row = self._conn.execute(
                """
                SELECT * FROM models WHERE enabled = 1
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return self._row(row) if row else None

    def set_default(self, model_id: str) -> ModelRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
            if not row:
                return None
            self._conn.execute("UPDATE models SET is_default = 0")
            self._conn.execute(
                """
                UPDATE models SET is_default = 1, updated_at = ?
                WHERE id = ?
                """,
                (utcnow_iso(), model_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return self._row(row) if row else None

    def delete(self, model_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def update(
        self,
        model_pk: str,
        *,
        name: str | None = None,
        model_id: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
    ) -> ModelRecord | None:
        current = self.get(model_pk)
        if not current:
            return None
        next_name = name.strip() if name is not None else current.name
        next_model = model_id.strip() if model_id is not None else current.model_id
        next_base = base_url.strip() if base_url is not None else current.base_url
        # Empty string api_key means "leave unchanged"; None from optional field handled by caller
        next_key = current.api_key
        if api_key is not None and api_key.strip():
            next_key = api_key.strip()
        next_enabled = current.enabled if enabled is None else enabled
        with self._lock:
            self._conn.execute(
                """
                UPDATE models SET
                    name = ?, model_id = ?, base_url = ?, api_key = ?,
                    enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_name,
                    next_model,
                    next_base,
                    next_key,
                    1 if next_enabled else 0,
                    utcnow_iso(),
                    model_pk,
                ),
            )
            self._conn.commit()
        return self.get(model_pk)

    def seed_from_env(
        self,
        *,
        openai_api_key: str | None,
        anthropic_api_key: str | None,
    ) -> list[ModelRecord]:
        """Create default entries from env keys if library is empty."""
        if self.list(limit=1):
            return []
        created: list[ModelRecord] = []
        if openai_api_key:
            created.append(
                self.create(
                    name="OpenAI GPT-4o mini",
                    provider="openai",
                    model_id="gpt-4o-mini",
                    api_key=openai_api_key,
                    is_default=True,
                )
            )
        if anthropic_api_key:
            created.append(
                self.create(
                    name="Anthropic Claude Sonnet",
                    provider="anthropic",
                    model_id="claude-sonnet-4-20250514",
                    api_key=anthropic_api_key,
                    is_default=not bool(openai_api_key),
                )
            )
        return created

    @staticmethod
    def _row(row: sqlite3.Row) -> ModelRecord:
        return ModelRecord(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            model_id=row["model_id"],
            base_url=row["base_url"],
            api_key=row["api_key"],
            is_default=bool(row["is_default"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
