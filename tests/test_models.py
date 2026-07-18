from pathlib import Path

import pytest
import sqlite3

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.persistence.models import ModelStore
from aeios.secrets import is_sealed


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text("{}", encoding="utf-8")


def test_model_library_crud_and_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AEIOS_SECRETS_KEY", "test-secrets-key-for-pytest")
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    created = client.post(
        "/v1/models",
        json={
            "name": "Local Llama",
            "provider": "ollama",
            "model_id": "llama3.2",
            "is_default": True,
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["provider"] == "ollama"
    assert body["is_default"] is True
    assert body["api_key_set"] is False
    assert "api_key" not in body
    assert body["base_url"] == "http://127.0.0.1:11434/v1"
    model_id = body["id"]

    second = client.post(
        "/v1/models",
        json={
            "name": "OpenAI mini",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": "sk-test-secret-key-123456",
            "is_default": True,
        },
    )
    assert second.status_code == 200
    assert second.json()["is_default"] is True
    assert second.json()["api_key_set"] is True
    assert second.json()["api_key_masked"] is not None
    assert "sk-test-secret-key-123456" not in second.text

    listed = client.get("/v1/models")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    defaults = [m for m in listed.json() if m["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == second.json()["id"]

    reset = client.post(f"/v1/models/{model_id}/default")
    assert reset.status_code == 200
    assert reset.json()["is_default"] is True

    status = client.get("/v1/status")
    assert status.status_code == 200
    assert status.json()["default_model"]["id"] == model_id
    assert status.json()["models_count"] == 2

    deleted = client.delete(f"/v1/models/{model_id}")
    assert deleted.status_code == 200
    assert client.get(f"/v1/models/{model_id}").status_code == 404


def test_model_rejects_unknown_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AEIOS_SECRETS_KEY", raising=False)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    resp = client.post(
        "/v1/models",
        json={"name": "X", "provider": "gemini", "model_id": "x"},
    )
    assert resp.status_code == 400


def test_model_rejects_plaintext_store_without_secrets_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AEIOS_SECRETS_KEY", raising=False)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    resp = client.post(
        "/v1/models",
        json={
            "name": "OpenAI mini",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": "sk-should-not-persist",
        },
    )
    assert resp.status_code == 400
    assert "AEIOS_SECRETS_KEY" in resp.json()["detail"]


def test_stored_key_is_sealed_in_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEIOS_SECRETS_KEY", "unit-test-seal-key")
    store = ModelStore(tmp_path / "models.db", secrets_key="unit-test-seal-key")
    rec = store.create(
        name="Sealed",
        provider="openai",
        model_id="gpt-4o-mini",
        api_key="sk-plaintext-in-memory-only",
    )
    assert rec.api_key == "sk-plaintext-in-memory-only"

    conn = sqlite3.connect(str(tmp_path / "models.db"))
    raw = conn.execute("SELECT api_key FROM models WHERE id = ?", (rec.id,)).fetchone()[0]
    conn.close()
    assert is_sealed(raw)
    assert "sk-plaintext" not in raw

    loaded = store.get(rec.id)
    assert loaded is not None
    assert loaded.api_key == "sk-plaintext-in-memory-only"


def test_seed_from_env_does_not_persist_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AEIOS_SECRETS_KEY", raising=False)
    store = ModelStore(tmp_path / "models.db", secrets_key=None)
    created = store.seed_from_env(
        openai_api_key="sk-env-only",
        anthropic_api_key=None,
    )
    assert len(created) == 1
    assert created[0].api_key is None

    conn = sqlite3.connect(str(tmp_path / "models.db"))
    raw = conn.execute("SELECT api_key FROM models").fetchone()[0]
    conn.close()
    assert raw is None

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-only")
    from aeios.config import Settings
    from aeios.persistence.models import resolve_api_key

    settings = Settings(openai_api_key="sk-env-only")
    assert resolve_api_key(created[0], settings) == "sk-env-only"
    pub = created[0].public_dict()
    assert pub["api_key_set"] is True
    assert pub["api_key_masked"] == "env:OPENAI_API_KEY"
