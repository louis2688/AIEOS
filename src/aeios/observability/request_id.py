"""HTTP request ID middleware (X-Request-ID correlation)."""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from aeios.observability.metrics import get_metrics

logger = logging.getLogger("aeios.request")

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_var: ContextVar[str | None] = ContextVar("aeios_request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_var.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign or echo ``X-Request-ID`` and count HTTP requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        incoming = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
        request_id = incoming if incoming else new_request_id()
        token = _request_id_var.set(request_id)
        request.state.request_id = request_id
        get_metrics().record_http_request()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed request_id=%s path=%s", request_id, request.url.path)
            raise
        finally:
            _request_id_var.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
