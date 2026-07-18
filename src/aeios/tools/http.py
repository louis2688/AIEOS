"""Sandboxed HTTP tool — http/https only, with timeout and response size limits."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
DEFAULT_TIMEOUT_SEC = 15.0
DEFAULT_MAX_BYTES = 1_048_576  # 1 MiB
MAX_REDIRECTS = 5


def validate_url(url: str) -> tuple[str | None, str | None]:
    """Return (normalized_url, error). Rejects non-http(s) schemes including file://."""
    raw = (url or "").strip()
    if not raw:
        return None, "Empty URL"
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        label = scheme or "(none)"
        return None, f"Scheme not allowed: {label}. Allowed: {sorted(ALLOWED_SCHEMES)}"
    if not parsed.netloc:
        return None, "URL missing host"
    return raw, None


class HttpTool(BaseTool):
    name = "http"
    description = "Sandboxed HTTP client (http/https only; timeout + size limited)."

    def __init__(
        self,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_sec = float(timeout_sec)
        self.max_bytes = int(max_bytes)
        self.max_redirects = int(max_redirects)
        self._transport = transport

    def run(
        self,
        url: str = "",
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        **_: Any,
    ) -> ToolResult:
        checked, err = validate_url(url)
        if err or checked is None:
            return ToolResult(ok=False, error=err or "Invalid URL")

        verb = (method or "GET").strip().upper()
        if verb not in ALLOWED_METHODS:
            return ToolResult(
                ok=False,
                error=f"Method not allowed: {verb}. Allowed: {sorted(ALLOWED_METHODS)}",
            )

        req_headers = dict(headers or {})
        client_kwargs: dict[str, Any] = {
            "timeout": self.timeout_sec,
            "follow_redirects": False,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        try:
            with httpx.Client(**client_kwargs) as client:
                response, final_url, truncated = self._request_with_redirects(
                    client,
                    verb=verb,
                    url=checked,
                    headers=req_headers,
                    body=body,
                )
        except httpx.TimeoutException:
            return ToolResult(ok=False, error=f"Timed out after {self.timeout_sec}s")
        except httpx.InvalidURL as exc:
            return ToolResult(ok=False, error=str(exc))
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=str(exc))

        text = response.text
        if truncated and len(text.encode("utf-8", errors="replace")) >= self.max_bytes:
            # Ensure callers see truncation even when decode reshapes length.
            text = text[: self.max_bytes]

        output = {
            "url": final_url,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": text,
            "truncated": truncated,
            "bytes": len(response.content),
        }
        if response.status_code >= 400:
            return ToolResult(
                ok=False,
                output=output,
                error=f"HTTP {response.status_code}",
            )
        return ToolResult(ok=True, output=output)

    def _request_with_redirects(
        self,
        client: httpx.Client,
        *,
        verb: str,
        url: str,
        headers: dict[str, str],
        body: str | None,
    ) -> tuple[httpx.Response, str, bool]:
        current = url
        method = verb
        for _ in range(self.max_redirects + 1):
            checked, err = validate_url(current)
            if err or checked is None:
                raise httpx.InvalidURL(err or "Invalid redirect URL")

            with client.stream(
                method,
                checked,
                headers=headers,
                content=body if method == "POST" else None,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        # Consume body so connection can close cleanly.
                        _ = self._read_limited(response)
                        raise httpx.HTTPError("Redirect without Location header")
                    next_url = urljoin(str(response.url), location)
                    # Drain redirect body (usually empty) before next hop.
                    _ = self._read_limited(response)
                    current = next_url
                    # RFC: 303 → GET; 301/302 historically treated as GET for non-GET.
                    if response.status_code in {301, 302, 303} and method != "HEAD":
                        method = "GET"
                        body = None
                    continue

                content, truncated = self._read_limited(response)
                # Build a Response-like object with bounded content for .text/.content.
                bounded = httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    content=content,
                    request=response.request,
                    extensions=response.extensions,
                )
                return bounded, str(response.url), truncated

        raise httpx.HTTPError(f"Too many redirects (max {self.max_redirects})")

    def _read_limited(self, response: httpx.Response) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        total = 0
        truncated = False
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            if total + len(chunk) > self.max_bytes:
                remain = self.max_bytes - total
                if remain > 0:
                    chunks.append(chunk[:remain])
                    total += remain
                truncated = True
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks), truncated
