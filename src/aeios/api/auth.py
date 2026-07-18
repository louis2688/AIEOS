"""Clerk JWT authentication for the FastAPI control plane."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from aeios.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Public paths that never require a Bearer token.
PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})

# Owner stamped on rows when auth is disabled (must match ProjectStore / PipelineStore).
LOCAL_OWNER_ID = "local"


def resolve_owner_id(request: Request) -> str:
    """Return the Clerk ``sub`` (or local escape-hatch owner) for row scoping.

    Middleware sets ``request.state.user_id`` from verified JWT claims when auth
    is enabled, or to ``LOCAL_OWNER_ID`` (``"local"``) when auth is disabled.
    """
    user_id = getattr(request.state, "user_id", None)
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return LOCAL_OWNER_ID


def auth_is_enabled(settings: Settings | None = None) -> bool:
    """Return True when JWT validation should run.

    Disabled when ``AEIOS_AUTH_DISABLED`` is set, or when neither
    ``CLERK_JWKS_URL`` nor ``CLERK_ISSUER`` is configured (local CLI default).
    """
    cfg = settings or get_settings()
    if cfg.aeios_auth_disabled:
        return False
    return bool(cfg.clerk_jwks_url or cfg.clerk_issuer)


def resolve_jwks_url(settings: Settings) -> str | None:
    if settings.clerk_jwks_url:
        return settings.clerk_jwks_url.rstrip("/")
    if settings.clerk_issuer:
        return f"{settings.clerk_issuer.rstrip('/')}/.well-known/jwks.json"
    return None


class ClerkJWTVerifier:
    """Validate Clerk-issued session JWTs via JWKS (RS256)."""

    def __init__(
        self,
        jwks_url: str,
        *,
        issuer: str | None = None,
        audience: str | None = None,
        cache_ttl_seconds: float = 3600.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.jwks_url = jwks_url
        self.issuer = issuer.rstrip("/") if issuer else None
        self.audience = audience
        self.cache_ttl_seconds = cache_ttl_seconds
        self._client = http_client
        self._owns_client = http_client is None
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0.0

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=10.0)
        return self._client

    def fetch_jwks(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force
            and self._jwks is not None
            and (now - self._jwks_fetched_at) < self.cache_ttl_seconds
        ):
            return self._jwks
        response = self._get_client().get(self.jwks_url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or "keys" not in data:
            raise ValueError("Invalid JWKS response")
        self._jwks = data
        self._jwks_fetched_at = now
        return data

    def verify(self, token: str) -> dict[str, Any]:
        """Verify a Bearer JWT and return its claims."""
        try:
            import jwt
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PyJWT is required for Clerk auth. Install with: pip install 'aeios[api]'"
            ) from exc

        try:
            jwks = self.fetch_jwks()
        except Exception as exc:
            raise ValueError(f"Unable to fetch JWKS: {exc}") from exc

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise ValueError("Invalid token header") from exc

        kid = header.get("kid")
        if not kid:
            raise ValueError("Token missing kid")

        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            # Key rotation — refresh once
            jwks = self.fetch_jwks(force=True)
            key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            raise ValueError("Unknown signing key")

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid signing key") from exc

        options: dict[str, Any] = {
            "require": ["exp", "iat", "sub"],
            "verify_aud": bool(self.audience),
        }
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": options,
        }
        if self.issuer:
            decode_kwargs["issuer"] = self.issuer
        if self.audience:
            decode_kwargs["audience"] = self.audience

        try:
            claims = jwt.decode(token, public_key, **decode_kwargs)
        except jwt.PyJWTError as exc:
            raise ValueError(f"Invalid token: {exc}") from exc

        if not isinstance(claims, dict):
            raise ValueError("Invalid token claims")
        return claims


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests to protected API routes when auth is on."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings | None = None,
        verifier: ClerkJWTVerifier | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self._verifier = verifier
        self._owns_verifier = verifier is None

    def _get_verifier(self) -> ClerkJWTVerifier | None:
        if not auth_is_enabled(self.settings):
            return None
        if self._verifier is not None:
            return self._verifier
        jwks_url = resolve_jwks_url(self.settings)
        if not jwks_url:
            return None
        self._verifier = ClerkJWTVerifier(
            jwks_url,
            issuer=self.settings.clerk_issuer,
            audience=self.settings.clerk_audience,
        )
        return self._verifier

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        if not auth_is_enabled(self.settings):
            # Escape hatch (AEIOS_AUTH_DISABLED / no Clerk config): fixed local owner.
            request.state.user_id = LOCAL_OWNER_ID
            request.state.clerk_claims = None
            return await call_next(request)

        verifier = self._get_verifier()
        if verifier is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "Auth enabled but CLERK_JWKS_URL / CLERK_ISSUER not configured"},
            )

        token = _extract_bearer(request.headers.get("authorization"))
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization Bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            claims = verifier.verify(token)
        except ValueError as exc:
            logger.debug("JWT rejected: %s", exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            return JSONResponse(
                status_code=401,
                content={"detail": "Token missing subject (sub)"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.clerk_claims = claims
        request.state.user_id = sub.strip()
        return await call_next(request)
