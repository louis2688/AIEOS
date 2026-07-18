"""Tests for request IDs and in-process metrics counters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.models.client import ModelClient
from aeios.observability.metrics import get_metrics
from aeios.persistence.models import ModelRecord


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: echo
tools:
  filesystem:
    enabled: false
  shell:
    enabled: false
agents:
  echo:
    enabled: true
  software_engineer:
    enabled: false
  architect:
    enabled: false
""".strip(),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    get_metrics().reset()
    yield
    get_metrics().reset()


def test_request_id_generated_and_echoed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    resp = client.get("/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid
    assert len(rid) >= 8

    echoed = client.get("/v1/status", headers={"X-Request-ID": "client-corr-42"})
    assert echoed.status_code == 200
    assert echoed.headers.get("X-Request-ID") == "client-corr-42"


def test_metrics_endpoint_and_http_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    before = client.get("/v1/metrics")
    assert before.status_code == 200
    body = before.json()
    assert "llm_calls" in body
    assert "tool_calls" in body
    assert "http_requests" in body
    http_after_metrics = body["http_requests"]

    client.get("/health")
    after = client.get("/v1/metrics").json()
    assert after["http_requests"] > http_after_metrics


def test_task_and_tool_metrics_increment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    client = TestClient(create_app(workspace=tmp_path))

    created = client.post("/v1/tasks", json={"goal": "say hello", "agent": "echo"})
    assert created.status_code == 200

    metrics = client.get("/v1/metrics").json()
    assert metrics["tasks_started"] >= 1
    assert metrics["tasks_completed"] + metrics["tasks_failed"] >= 1
    assert metrics["tool_calls"] >= 1


def test_llm_metrics_from_model_client() -> None:
    record = ModelRecord(
        id="m1",
        name="test",
        provider="openai",
        model_id="gpt-4o-mini",
        base_url="https://example.test/v1",
        api_key="sk-test",
        is_default=False,
        enabled=True,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    fake_json = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_json

    with patch("aeios.models.client.httpx.Client") as client_cls:
        ctx = client_cls.return_value.__enter__.return_value
        ctx.post.return_value = mock_resp
        text = ModelClient().complete(record, system="sys", user="hi")

    assert text == "ok"
    snap = get_metrics().snapshot()
    assert snap.llm_calls == 1
    assert snap.llm_prompt_tokens == 10
    assert snap.llm_completion_tokens == 5
    assert snap.llm_total_tokens == 15
    assert snap.by_provider.get("openai") == 1
    assert snap.llm_estimated_cost_usd > 0


def test_llm_failure_increments_failures() -> None:
    record = ModelRecord(
        id="m2",
        name="test",
        provider="openai",
        model_id="gpt-4o-mini",
        base_url="https://example.test/v1",
        api_key="sk-test",
        is_default=False,
        enabled=True,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("boom")

    with patch("aeios.models.client.httpx.Client") as client_cls:
        ctx = client_cls.return_value.__enter__.return_value
        ctx.post.return_value = mock_resp
        with pytest.raises(Exception, match="boom"):
            ModelClient().complete(record, system="sys", user="hi")

    snap = get_metrics().snapshot()
    assert snap.llm_failures == 1
    assert snap.llm_calls == 0


def test_metrics_respects_auth_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AEIOS_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.test.example")
    _write_config(tmp_path)

    from aeios.config import Settings

    settings = Settings(
        aeios_auth_disabled=False,
        clerk_issuer="https://clerk.test.example",
        clerk_jwks_url="https://clerk.test.example/.well-known/jwks.json",
    )
    client = TestClient(create_app(workspace=tmp_path, auth_settings=settings))

    # /health stays public; /v1/metrics requires auth when enabled
    assert client.get("/health").status_code == 200
    denied = client.get("/v1/metrics")
    assert denied.status_code == 401
    assert denied.headers.get("X-Request-ID")
