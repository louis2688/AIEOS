"""Tests for FastAPI Clerk JWT middleware."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jwt")

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.api.auth import ClerkJWTVerifier, auth_is_enabled, resolve_jwks_url
from aeios.config import Settings


ISSUER = "https://clerk.test.example"
KID = "test-key-1"


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: software_engineer
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
  shell:
    enabled: false
agents:
  software_engineer:
    enabled: true
  echo:
    enabled: true
  architect:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


@pytest.fixture
def rsa_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()

    def _int_to_b64(value: int) -> str:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return jwt.utils.base64url_encode(raw).decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_b64(public_numbers.n),
        "e": _int_to_b64(public_numbers.e),
    }
    return private_key, {"keys": [jwk]}


def _make_token(
    private_key,
    *,
    expires_in: int = 300,
    kid: str = KID,
    sub: str = "user_test_123",
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "iss": ISSUER,
            "iat": now,
            "nbf": now,
            "exp": now + expires_in,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _enabled_settings() -> Settings:
    return Settings(
        aeios_auth_disabled=False,
        clerk_issuer=ISSUER,
        clerk_jwks_url=f"{ISSUER}/.well-known/jwks.json",
    )


def _verifier(jwks: dict) -> ClerkJWTVerifier:
    verifier = ClerkJWTVerifier(
        f"{ISSUER}/.well-known/jwks.json",
        issuer=ISSUER,
        cache_ttl_seconds=3600,
    )
    verifier._jwks = jwks
    verifier._jwks_fetched_at = time.monotonic()
    return verifier


def test_auth_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEIOS_AUTH_DISABLED", "1")
    monkeypatch.setenv("CLERK_ISSUER", ISSUER)
    assert auth_is_enabled(Settings()) is False


def test_auth_disabled_without_clerk_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEIOS_AUTH_DISABLED", "0")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    assert auth_is_enabled(Settings()) is False


def test_resolve_jwks_url_from_issuer() -> None:
    settings = Settings(clerk_issuer=ISSUER, clerk_jwks_url=None)
    assert resolve_jwks_url(settings) == f"{ISSUER}/.well-known/jwks.json"


def test_auth_disabled_allows_unauthenticated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setenv("AEIOS_AUTH_DISABLED", "1")
    client = TestClient(create_app(workspace=tmp_path, auth_settings=Settings(aeios_auth_disabled=True)))

    assert client.get("/health").status_code == 200
    assert client.get("/v1/status").status_code == 200


def test_auth_enabled_rejects_missing_token(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    _, jwks = rsa_pair
    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )

    assert client.get("/health").status_code == 200
    res = client.get("/v1/status")
    assert res.status_code == 401
    assert "Bearer" in res.headers.get("www-authenticate", "")


def test_auth_enabled_rejects_invalid_token(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    _, jwks = rsa_pair
    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )

    res = client.get("/v1/status", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_auth_enabled_rejects_wrong_signature(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    _, jwks = rsa_pair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_token = _make_token(other_key)

    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )
    res = client.get("/v1/status", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401


def test_auth_enabled_accepts_valid_token(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    private_key, jwks = rsa_pair
    token = _make_token(private_key)

    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )
    res = client.get("/v1/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert "ok" in res.json() or "agents" in res.json() or isinstance(res.json(), dict)


def test_verifier_rejects_expired_token(rsa_pair) -> None:
    private_key, jwks = rsa_pair
    token = _make_token(private_key, expires_in=-10)
    verifier = _verifier(jwks)
    with pytest.raises(ValueError, match="Invalid token"):
        verifier.verify(token)


def test_verifier_uses_cached_jwks(rsa_pair, monkeypatch) -> None:
    private_key, jwks = rsa_pair
    calls = {"n": 0}

    def boom(*_a, **_k):  # pragma: no cover - must not be called
        calls["n"] += 1
        raise AssertionError("network fetch should not run when JWKS is cached")

    verifier = _verifier(jwks)
    monkeypatch.setattr(verifier, "_get_client", boom)
    claims = verifier.verify(_make_token(private_key))
    assert claims["sub"] == "user_test_123"
    assert calls["n"] == 0


def test_jwks_json_roundtrip_helper(rsa_pair) -> None:
    """Ensure our JWK dict is usable by PyJWT (sanity for fixture)."""
    private_key, jwks = rsa_pair
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwks["keys"][0]))
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert b"BEGIN PUBLIC KEY" in pem
    token = _make_token(private_key)
    decoded = jwt.decode(token, public_key, algorithms=["RS256"], issuer=ISSUER)
    assert decoded["sub"] == "user_test_123"


def test_projects_scoped_to_jwt_sub(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    """Two Clerk users must not see each other's projects."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    private_key, jwks = rsa_pair
    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )
    token_a = _make_token(private_key, sub="user_alice")
    token_b = _make_token(private_key, sub="user_bob")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    created = client.post(
        "/v1/projects",
        headers=headers_a,
        json={"name": "Alice Only", "description": "private"},
    )
    assert created.status_code == 200
    assert created.json()["owner_id"] == "user_alice"
    project_id = created.json()["id"]

    listed_a = client.get("/v1/projects", headers=headers_a)
    assert listed_a.status_code == 200
    assert any(p["id"] == project_id for p in listed_a.json())

    listed_b = client.get("/v1/projects", headers=headers_b)
    assert listed_b.status_code == 200
    assert listed_b.json() == []

    assert client.get(f"/v1/projects/{project_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/v1/projects/{project_id}", headers=headers_b).status_code == 404
    assert client.get(f"/v1/projects/{project_id}", headers=headers_a).status_code == 200


def test_pipelines_scoped_to_jwt_sub(tmp_path: Path, monkeypatch, rsa_pair) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    private_key, jwks = rsa_pair
    client = TestClient(
        create_app(
            workspace=tmp_path,
            auth_settings=_enabled_settings(),
            auth_verifier=_verifier(jwks),
        )
    )
    headers_a = {
        "Authorization": f"Bearer {_make_token(private_key, sub='user_alice')}"
    }
    headers_b = {
        "Authorization": f"Bearer {_make_token(private_key, sub='user_bob')}"
    }

    created = client.post(
        "/v1/pipelines",
        headers=headers_a,
        json={
            "name": "Alice Pipe",
            "steps": [{"goal": "hello", "agent": "echo"}],
        },
    )
    assert created.status_code == 200
    assert created.json()["owner_id"] == "user_alice"
    pipeline_id = created.json()["id"]

    assert client.get("/v1/pipelines", headers=headers_b).json() == []
    assert client.get(f"/v1/pipelines/{pipeline_id}", headers=headers_b).status_code == 404
    assert (
        client.post(
            f"/v1/pipelines/{pipeline_id}/runs",
            headers=headers_b,
            json={"input_goal": "x"},
        ).status_code
        == 404
    )
    assert client.get(f"/v1/pipelines/{pipeline_id}", headers=headers_a).status_code == 200

    # Alice runs; Bob cannot read that run by id.
    run = client.post(
        f"/v1/pipelines/{pipeline_id}/runs",
        headers=headers_a,
        json={"input_goal": "hello"},
    )
    assert run.status_code == 200
    run_id = run.json()["id"]
    assert client.get(f"/v1/pipeline-runs/{run_id}", headers=headers_a).status_code == 200
    assert client.get(f"/v1/pipeline-runs/{run_id}", headers=headers_b).status_code == 404
    assert client.get(f"/v1/pipelines/{pipeline_id}/runs", headers=headers_b).status_code == 404
