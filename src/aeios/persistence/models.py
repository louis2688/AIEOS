from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from aeios.config import Settings, get_settings
from aeios.persistence.db import SqlDb, coerce_db
from aeios.secrets import is_sealed, seal, unseal

PROVIDERS = frozenset({"openai", "anthropic", "ollama"})

# Env var names used when a model row has no stored key.
PROVIDER_ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}…{value[-4:]}"


def env_api_key_for_provider(provider: str, settings: Settings | None = None) -> str | None:
    """Return the process env key for a provider, if configured."""
    s = settings or get_settings()
    if provider == "openai":
        return (s.openai_api_key or "").strip() or None
    if provider == "anthropic":
        return (s.anthropic_api_key or "").strip() or None
    return None


def resolve_api_key(record: ModelRecord, settings: Settings | None = None) -> str | None:
    """Prefer a stored (decrypted) key; otherwise fall back to provider env vars."""
    if record.api_key:
        return record.api_key
    return env_api_key_for_provider(record.provider, settings)


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
        stored = bool(self.api_key)
        env_key = None if stored else env_api_key_for_provider(self.provider)
        key_set = stored or bool(env_key)
        if stored:
            masked = mask_secret(self.api_key)
        elif env_key:
            env_name = PROVIDER_ENV_KEYS.get(self.provider, "ENV")
            masked = f"env:{env_name}"
        else:
            masked = None
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "api_key_set": key_set,
            "api_key_masked": masked,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ModelStore:
    """SQLite registry for LLM providers / models.

    Provider API keys are never returned in API payloads (see ``public_dict``).
    When ``AEIOS_SECRETS_KEY`` is set, keys are sealed before INSERT/UPDATE.
    When unset, keys cannot be persisted — use ``OPENAI_API_KEY`` /
    ``ANTHROPIC_API_KEY`` env overrides instead (``seed_from_env`` never copies
    raw keys into SQLite).
    """

    def __init__(
        self,
        db: SqlDb | Path,
        *,
        secrets_key: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._db = coerce_db(db)
        self.db_path = self._db.path or Path(self._db.display)
        self._settings = settings
        if secrets_key is not None:
            self._secrets_key = (secrets_key or "").strip() or None
        else:
            s = settings or get_settings()
            self._secrets_key = (s.aeios_secrets_key or "").strip() or None
        self._init_schema()

    def _settings_obj(self) -> Settings:
        return self._settings or get_settings()

    def _init_schema(self) -> None:
        with self._db.lock():
            self._db.executescript(
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
            self._db.commit()

    def _prepare_stored_key(self, api_key: str | None) -> str | None:
        """Normalize and optionally seal a key for at-rest storage."""
        raw = (api_key or "").strip() or None
        if not raw:
            return None
        if not self._secrets_key:
            raise ValueError(
                "Cannot store API keys without AEIOS_SECRETS_KEY. "
                "Set AEIOS_SECRETS_KEY to encrypt keys at rest, or omit api_key "
                "and use OPENAI_API_KEY / ANTHROPIC_API_KEY env vars."
            )
        if is_sealed(raw):
            return raw
        return seal(raw, self._secrets_key)

    def _decode_stored_key(self, stored: str | None) -> str | None:
        if not stored:
            return None
        if is_sealed(stored):
            if not self._secrets_key:
                return None
            try:
                return unseal(stored, self._secrets_key)
            except ValueError:
                return None
        # Legacy plaintext row (pre-hardening); still readable.
        return stored

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

        plaintext = (api_key or "").strip() or None
        stored_key = self._prepare_stored_key(plaintext)

        now = utcnow_iso()
        record = ModelRecord(
            id=uuid4().hex[:12],
            name=name.strip(),
            provider=provider,
            model_id=model_id.strip(),
            base_url=(base_url or "").strip() or None,
            api_key=plaintext,
            is_default=is_default,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        with self._db.lock():
            if record.is_default:
                self._db.execute("UPDATE models SET is_default = 0")
            self._db.execute(
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
                    stored_key,
                    1 if record.is_default else 0,
                    1 if record.enabled else 0,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._db.commit()
        return record

    def list(self, limit: int = 100) -> list[ModelRecord]:
        with self._db.lock():
            rows = self._db.execute(
                "SELECT * FROM models ORDER BY is_default DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, model_id: str) -> ModelRecord | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return self._row(row) if row else None

    def get_default(self) -> ModelRecord | None:
        with self._db.lock():
            row = self._db.execute(
                """
                SELECT * FROM models
                WHERE is_default = 1 AND enabled = 1
                LIMIT 1
                """
            ).fetchone()
            if row:
                return self._row(row)
            row = self._db.execute(
                """
                SELECT * FROM models WHERE enabled = 1
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return self._row(row) if row else None

    def set_default(self, model_id: str) -> ModelRecord | None:
        with self._db.lock():
            row = self._db.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
            if not row:
                return None
            self._db.execute("UPDATE models SET is_default = 0")
            self._db.execute(
                """
                UPDATE models SET is_default = 1, updated_at = ?
                WHERE id = ?
                """,
                (utcnow_iso(), model_id),
            )
            self._db.commit()
            row = self._db.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return self._row(row) if row else None

    def delete(self, model_id: str) -> bool:
        with self._db.lock():
            cur = self._db.execute("DELETE FROM models WHERE id = ?", (model_id,))
            self._db.commit()
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
        next_plaintext = current.api_key
        rewrite_key = False
        if api_key is not None and api_key.strip():
            next_plaintext = api_key.strip()
            rewrite_key = True
        next_enabled = current.enabled if enabled is None else enabled

        # Re-read raw stored value when leaving key unchanged so we do not
        # re-seal plaintext or drop a sealed blob we cannot re-derive.
        with self._db.lock():
            raw_row = self._db.execute(
                "SELECT api_key FROM models WHERE id = ?", (model_pk,)
            ).fetchone()
            if rewrite_key:
                stored_key = self._prepare_stored_key(next_plaintext)
            else:
                stored_key = raw_row["api_key"] if raw_row else None

            self._db.execute(
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
                    stored_key,
                    1 if next_enabled else 0,
                    utcnow_iso(),
                    model_pk,
                ),
            )
            self._db.commit()
        return self.get(model_pk)

    def seed_from_env(
        self,
        *,
        openai_api_key: str | None,
        anthropic_api_key: str | None,
    ) -> list[ModelRecord]:
        """Create default entries from env if library is empty.

        Keys are **not** copied into the DB — runtime resolution uses
        ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` via ``resolve_api_key``.
        """
        if self.list(limit=1):
            return []
        created: list[ModelRecord] = []
        if openai_api_key:
            created.append(
                self.create(
                    name="OpenAI GPT-4o mini",
                    provider="openai",
                    model_id="gpt-4o-mini",
                    api_key=None,
                    is_default=True,
                )
            )
        if anthropic_api_key:
            created.append(
                self.create(
                    name="Anthropic Claude Sonnet",
                    provider="anthropic",
                    model_id="claude-sonnet-4-20250514",
                    api_key=None,
                    is_default=not bool(openai_api_key),
                )
            )
        return created

    def _row(self, row) -> ModelRecord:
        return ModelRecord(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            model_id=row["model_id"],
            base_url=row["base_url"],
            api_key=self._decode_stored_key(row["api_key"]),
            is_default=bool(row["is_default"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
