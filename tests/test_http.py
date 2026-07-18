from __future__ import annotations

import httpx

# Import kernel first to avoid tools ↔ core circular import during collection.
from aeios.core.kernel import Kernel  # noqa: F401
from aeios.tools.http import ALLOWED_SCHEMES, HttpTool, validate_url


def test_validate_url_allows_http_https() -> None:
    ok, err = validate_url("https://example.com/path")
    assert err is None
    assert ok == "https://example.com/path"
    ok, err = validate_url("http://127.0.0.1:8080/")
    assert err is None
    assert ok is not None


def test_validate_url_rejects_file_and_other_schemes() -> None:
    _, err = validate_url("file:///etc/passwd")
    assert err is not None
    assert "not allowed" in err
    assert "file" in err
    _, err = validate_url("ftp://example.com/x")
    assert err is not None
    assert "ftp" in err
    _, err = validate_url("not-a-url")
    assert err is not None


def test_http_get_success_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://example.test/api"
        return httpx.Response(200, text='{"ok": true}', headers={"content-type": "application/json"})

    tool = HttpTool(transport=httpx.MockTransport(handler))
    result = tool.run(url="https://example.test/api", method="GET")
    assert result.ok is True
    assert isinstance(result.output, dict)
    assert result.output["status_code"] == 200
    assert '{"ok": true}' in result.output["body"]
    assert result.output["truncated"] is False


def test_http_rejects_file_scheme() -> None:
    tool = HttpTool(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    result = tool.run(url="file:///tmp/secret")
    assert result.ok is False
    assert "not allowed" in (result.error or "")


def test_http_rejects_disallowed_method() -> None:
    tool = HttpTool(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    result = tool.run(url="https://example.test/", method="DELETE")
    assert result.ok is False
    assert "Method not allowed" in (result.error or "")


def test_http_truncates_oversized_body() -> None:
    payload = "x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload.encode("utf-8"))

    tool = HttpTool(max_bytes=100, transport=httpx.MockTransport(handler))
    result = tool.run(url="https://example.test/big")
    assert result.ok is True
    assert isinstance(result.output, dict)
    assert result.output["truncated"] is True
    assert result.output["bytes"] == 100
    assert len(result.output["body"]) <= 100


def test_http_timeout_surfaces_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    tool = HttpTool(timeout_sec=0.01, transport=httpx.MockTransport(handler))
    result = tool.run(url="https://example.test/slow")
    assert result.ok is False
    assert "Timed out" in (result.error or "")


def test_http_blocks_redirect_to_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "file:///etc/passwd"})
        return httpx.Response(200, text="should not reach")

    tool = HttpTool(transport=httpx.MockTransport(handler))
    result = tool.run(url="https://example.test/start")
    assert result.ok is False
    assert result.error is not None


def test_http_follows_https_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.test/final"})
        return httpx.Response(200, text="landed")

    tool = HttpTool(transport=httpx.MockTransport(handler))
    result = tool.run(url="https://example.test/start")
    assert result.ok is True
    assert isinstance(result.output, dict)
    assert result.output["body"] == "landed"
    assert result.output["url"].endswith("/final")


def test_allowed_schemes_constant() -> None:
    assert ALLOWED_SCHEMES == frozenset({"http", "https"})
