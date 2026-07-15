from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text("{}", encoding="utf-8")


def test_model_library_crud_and_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))
    resp = client.post(
        "/v1/models",
        json={"name": "X", "provider": "gemini", "model_id": "x"},
    )
    assert resp.status_code == 400
