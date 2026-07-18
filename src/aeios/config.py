from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aeios_env: str = "development"
    aeios_log_level: str = "INFO"
    # sqlite:///… (default) or postgresql://user:pass@host:5432/aeios
    database_url: str = "sqlite:///./data/aeios.db"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "aeios_knowledge"
    # When True, knowledge search tries Qdrant if the client is installed
    # and the service is reachable; lexical search always remains the fallback.
    qdrant_enabled: bool = True
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Local master key for encrypting provider API keys at rest in SQLite.
    # When unset, model records should omit stored keys and rely on env vars.
    aeios_secrets_key: str | None = None
    config_path: Path = Field(default=Path("configs/default.yaml"))
    # Bounded tool retries after first failure (reflection/re-plan loop).
    max_tool_retries: int = 2

    # API auth (Clerk JWT). When disabled, or when no JWKS/issuer is set,
    # FastAPI skips Bearer validation (local CLI / pytest escape hatch).
    aeios_auth_disabled: bool = False
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None

    def load_yaml(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config must be a mapping: {self.config_path}")
        return data


def get_settings() -> Settings:
    return Settings()
