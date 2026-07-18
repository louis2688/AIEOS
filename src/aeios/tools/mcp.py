"""MCP bridge — expose external MCP server tools as kernel BaseTool instances.

Agents never talk to MCP directly; they invoke tools only via ``call_tool``.
The ``mcp`` package is an optional dependency (``pip install aeios[mcp]``).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Callable

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool

logger = logging.getLogger(__name__)

_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class McpServerConfig:
    """One MCP server entry from YAML ``tools.mcp.servers``."""

    name: str
    transport: str = "stdio"  # stdio | sse
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None
    cwd: str | None = None


@dataclass(frozen=True)
class McpToolSpec:
    """Remote tool metadata discovered from an MCP server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


def parse_mcp_servers(mcp_cfg: dict[str, Any] | None) -> list[McpServerConfig]:
    """Parse YAML ``tools.mcp`` into server configs. Empty/missing → []."""
    if not mcp_cfg or not mcp_cfg.get("enabled", True):
        return []
    raw = mcp_cfg.get("servers") or []
    if not isinstance(raw, list):
        return []
    servers: list[McpServerConfig] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        transport = str(entry.get("transport") or "stdio").lower().strip()
        args = entry.get("args") or []
        if not isinstance(args, list):
            args = []
        env = entry.get("env")
        if env is not None and not isinstance(env, dict):
            env = None
        servers.append(
            McpServerConfig(
                name=name,
                transport=transport,
                command=entry.get("command"),
                args=[str(a) for a in args],
                env={str(k): str(v) for k, v in env.items()} if env else None,
                url=entry.get("url"),
                cwd=entry.get("cwd"),
            )
        )
    return servers


def sanitize_tool_name(prefix: str, server: str, tool: str) -> str:
    """Build a stable kernel tool name: ``{prefix}_{server}_{tool}``."""

    def _clean(part: str) -> str:
        cleaned = _NAME_SAFE.sub("_", part.strip()).strip("_").lower()
        return cleaned or "unnamed"

    return f"{_clean(prefix)}_{_clean(server)}_{_clean(tool)}"


def _format_mcp_content(content: Any) -> Any:
    """Normalize MCP call_tool content blocks into a JSON-friendly value."""
    if content is None:
        return None
    if isinstance(content, (str, int, float, bool, dict)):
        return content
    if isinstance(content, list):
        parts: list[Any] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
                continue
            data = getattr(block, "data", None)
            if data is not None:
                parts.append(data)
                continue
            if isinstance(block, dict):
                parts.append(block.get("text") or block)
            else:
                parts.append(str(block))
        if len(parts) == 1:
            return parts[0]
        return parts
    return str(content)


class McpClient(ABC):
    """Sync façade over one MCP server session (real or fake)."""

    @abstractmethod
    def list_tools(self) -> list[McpToolSpec]:
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class FakeMcpClient(McpClient):
    """In-memory client for unit tests (no network / no ``mcp`` package)."""

    def __init__(
        self,
        tools: list[McpToolSpec] | None = None,
        *,
        handler: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._tools = list(tools or [])
        self._handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def list_tools(self) -> list[McpToolSpec]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = dict(arguments or {})
        self.calls.append((name, args))
        if self._handler is not None:
            return self._handler(name, args)
        return {"tool": name, "arguments": args}

    def close(self) -> None:
        self.closed = True


class SdkMcpClient(McpClient):
    """Persistent MCP session using the optional ``mcp`` SDK on a background loop."""

    def __init__(self, config: McpServerConfig, *, timeout_sec: float = 30.0) -> None:
        self.config = config
        self.timeout_sec = timeout_sec
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"aeios-mcp-{config.name}",
            daemon=True,
        )
        self._ready = threading.Event()
        self._session: Any = None
        self._error: BaseException | None = None
        self._stack: AsyncExitStack | None = None
        self._thread.start()
        if not self._ready.wait(timeout=timeout_sec):
            self.close()
            raise TimeoutError(f"MCP server '{config.name}' failed to connect in time")
        if self._error is not None:
            err = self._error
            self.close()
            raise RuntimeError(f"MCP server '{config.name}' connect failed: {err}") from err

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
        except BaseException as exc:  # noqa: BLE001 — surface on connect wait
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    async def _connect(self) -> None:
        from mcp import ClientSession

        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        read, write = await self._open_transport(self._stack)
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def _open_transport(self, stack: AsyncExitStack) -> tuple[Any, Any]:
        transport = self.config.transport
        if transport == "stdio":
            if not self.config.command:
                raise ValueError(f"MCP server '{self.config.name}' stdio requires 'command'")
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            params_kwargs: dict[str, Any] = {
                "command": self.config.command,
                "args": list(self.config.args),
                "env": self.config.env,
            }
            if self.config.cwd is not None:
                params_kwargs["cwd"] = self.config.cwd
            params = StdioServerParameters(**params_kwargs)
            return await stack.enter_async_context(stdio_client(params))

        if transport in {"sse", "http"}:
            if not self.config.url:
                raise ValueError(f"MCP server '{self.config.name}' {transport} requires 'url'")
            if transport == "sse":
                from mcp.client.sse import sse_client

                return await stack.enter_async_context(sse_client(self.config.url))
            # Streamable HTTP (MCP SDK ≥1.x) — may yield (read, write) or + get_session_id
            try:
                from mcp.client.streamable_http import streamablehttp_client
            except ImportError as exc:  # pragma: no cover - older sdk
                raise RuntimeError(
                    "MCP HTTP transport requires a newer 'mcp' package "
                    "(streamablehttp_client). Use transport: sse or upgrade mcp."
                ) from exc
            streams = await stack.enter_async_context(streamablehttp_client(self.config.url))
            return streams[0], streams[1]

        raise ValueError(
            f"Unsupported MCP transport '{transport}' for server '{self.config.name}' "
            "(use stdio, sse, or http)"
        )

    def _run(self, coro: Any) -> Any:
        if not self._thread.is_alive() or self._session is None:
            raise RuntimeError(f"MCP server '{self.config.name}' is not connected")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=self.timeout_sec)

    def list_tools(self) -> list[McpToolSpec]:
        result = self._run(self._session.list_tools())
        tools = getattr(result, "tools", None) or []
        specs: list[McpToolSpec] = []
        for tool in tools:
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            if schema is not None and hasattr(schema, "model_dump"):
                schema = schema.model_dump()
            specs.append(
                McpToolSpec(
                    name=str(tool.name),
                    description=str(getattr(tool, "description", None) or ""),
                    input_schema=schema if isinstance(schema, dict) else None,
                )
            )
        return specs

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = self._run(self._session.call_tool(name, arguments=arguments or {}))
        is_error = bool(getattr(result, "isError", None) or getattr(result, "is_error", False))
        structured = getattr(result, "structuredContent", None) or getattr(
            result, "structured_content", None
        )
        content = _format_mcp_content(getattr(result, "content", None))
        if is_error:
            raise RuntimeError(str(content) if content is not None else f"MCP tool '{name}' failed")
        if structured is not None:
            return structured
        return content

    def close(self) -> None:
        if self._loop.is_closed():
            return

        async def _teardown() -> None:
            if self._stack is not None:
                await self._stack.aclose()
                self._stack = None
            self._session = None

        try:
            if self._thread.is_alive():
                fut = asyncio.run_coroutine_threadsafe(_teardown(), self._loop)
                try:
                    fut.result(timeout=5)
                except Exception:  # noqa: BLE001
                    logger.debug("MCP teardown error for %s", self.config.name, exc_info=True)
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=5)
        finally:
            if not self._loop.is_closed():
                self._loop.close()


ClientFactory = Callable[[McpServerConfig], McpClient]


def default_client_factory(config: McpServerConfig) -> McpClient:
    """Create a real SDK-backed client; raises ImportError if ``mcp`` missing."""
    try:
        import mcp  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "MCP bridge requires the optional 'mcp' package. "
            "Install with: pip install 'aeios[mcp]'"
        ) from exc
    return SdkMcpClient(config)


class McpBridgeTool(BaseTool):
    """Kernel tool that forwards ``run`` to a remote MCP tool via a client."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        remote_name: str,
        client: McpClient,
        server: str,
    ) -> None:
        self.name = name
        self.description = description
        self.remote_name = remote_name
        self.server = server
        self._client = client

    def run(self, **kwargs: Any) -> ToolResult:
        try:
            output = self._client.call_tool(self.remote_name, arguments=dict(kwargs))
            return ToolResult(ok=True, output=output)
        except Exception as exc:  # noqa: BLE001 — boundary; surface as ToolResult
            return ToolResult(ok=False, error=str(exc))


class McpBridge:
    """Connect to configured MCP servers and produce kernel-registrable tools."""

    def __init__(
        self,
        servers: list[McpServerConfig],
        *,
        name_prefix: str = "mcp",
        client_factory: ClientFactory | None = None,
        timeout_sec: float = 30.0,
    ) -> None:
        self.servers = servers
        self.name_prefix = name_prefix
        self.client_factory = client_factory or default_client_factory
        self.timeout_sec = timeout_sec
        self._clients: list[McpClient] = []
        self.errors: list[str] = []

    def discover_tools(self) -> list[BaseTool]:
        """Connect, list remote tools, wrap as BaseTool. Soft-fails per server."""
        tools: list[BaseTool] = []
        for cfg in self.servers:
            try:
                client = self.client_factory(cfg)
            except Exception as exc:  # noqa: BLE001
                msg = f"MCP server '{cfg.name}': connect failed ({exc})"
                logger.warning(msg)
                self.errors.append(msg)
                continue
            self._clients.append(client)
            try:
                specs = client.list_tools()
            except Exception as exc:  # noqa: BLE001
                msg = f"MCP server '{cfg.name}': list_tools failed ({exc})"
                logger.warning(msg)
                self.errors.append(msg)
                continue
            for spec in specs:
                registered = sanitize_tool_name(self.name_prefix, cfg.name, spec.name)
                desc = spec.description or f"MCP tool {spec.name} from server {cfg.name}"
                tools.append(
                    McpBridgeTool(
                        name=registered,
                        description=desc,
                        remote_name=spec.name,
                        client=client,
                        server=cfg.name,
                    )
                )
        return tools

    def close(self) -> None:
        for client in self._clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.debug("Error closing MCP client", exc_info=True)
        self._clients.clear()


def load_mcp_tools(
    mcp_cfg: dict[str, Any] | None,
    *,
    client_factory: ClientFactory | None = None,
) -> tuple[list[BaseTool], McpBridge | None]:
    """Load MCP tools from YAML config.

    Returns ``([], None)`` when no servers are configured (kernel unchanged).
    """
    servers = parse_mcp_servers(mcp_cfg)
    if not servers:
        return [], None
    prefix = str((mcp_cfg or {}).get("name_prefix") or "mcp")
    timeout = float((mcp_cfg or {}).get("timeout_sec") or 30)
    bridge = McpBridge(
        servers,
        name_prefix=prefix,
        client_factory=client_factory,
        timeout_sec=timeout,
    )
    return bridge.discover_tools(), bridge
