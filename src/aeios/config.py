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
    database_url: str = "sqlite:///./data/aeios.db"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    config_path: Path = Field(default=Path("configs/default.yaml"))

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
