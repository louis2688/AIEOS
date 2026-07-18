"""MCP bridge tests — mocked client only (no network / no mcp package required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios.config import Settings
from aeios.core.kernel import Kernel
from aeios.tools.mcp import (
    FakeMcpClient,
    McpBridge,
    McpServerConfig,
    McpToolSpec,
    load_mcp_tools,
    parse_mcp_servers,
    sanitize_tool_name,
)


def test_parse_mcp_servers_empty_or_disabled() -> None:
    assert parse_mcp_servers(None) == []
    assert parse_mcp_servers({}) == []
    assert parse_mcp_servers({"enabled": False, "servers": [{"name": "x"}]}) == []
    assert parse_mcp_servers({"servers": []}) == []


def test_parse_mcp_servers_stdio_and_sse() -> None:
    servers = parse_mcp_servers(
        {
            "enabled": True,
            "servers": [
                {
                    "name": "fs",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "pkg"],
                    "env": {"FOO": "bar"},
                },
                {"name": "remote", "transport": "sse", "url": "http://127.0.0.1:9/sse"},
            ],
        }
    )
    assert len(servers) == 2
    assert servers[0].name == "fs"
    assert servers[0].command == "npx"
    assert servers[0].args == ["-y", "pkg"]
    assert servers[0].env == {"FOO": "bar"}
    assert servers[1].transport == "sse"
    assert servers[1].url == "http://127.0.0.1:9/sse"


def test_sanitize_tool_name() -> None:
    assert sanitize_tool_name("mcp", "File System", "read-file") == "mcp_file_system_read_file"


def test_fake_client_bridge_discovers_and_calls() -> None:
    fake = FakeMcpClient(
        [McpToolSpec(name="add", description="Add two numbers")],
        handler=lambda name, args: args["a"] + args["b"] if name == "add" else None,
    )
    bridge = McpBridge(
        [McpServerConfig(name="math", transport="stdio", command="unused")],
        client_factory=lambda _cfg: fake,
    )
    tools = bridge.discover_tools()
    assert len(tools) == 1
    assert tools[0].name == "mcp_math_add"
    result = tools[0].run(a=2, b=3)
    assert result.ok is True
    assert result.output == 5
    assert fake.calls == [("add", {"a": 2, "b": 3})]
    bridge.close()
    assert fake.closed is True


def test_load_mcp_tools_noop_without_servers() -> None:
    tools, bridge = load_mcp_tools({"enabled": True, "servers": []})
    assert tools == []
    assert bridge is None


def test_kernel_without_mcp_servers_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: echo
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
  mcp:
    enabled: true
    servers: []
agents:
  echo:
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(config_path=tmp_path / "configs" / "default.yaml")
    k = Kernel(settings=settings, workspace=tmp_path)
    assert not any(n.startswith("mcp_") for n in k.tools)
    # Builtin path still works
    r = k.call_tool("echo", message="hi")
    assert r.ok and r.output == "hi"
    doctor = k.doctor()
    mcp_check = next(c for c in doctor["checks"] if c["name"] == "mcp_bridge")
    assert mcp_check["ok"] is True
    assert "disabled" in mcp_check["detail"]


def test_kernel_registers_mcp_tools_via_factory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: echo
  max_tool_retries: 0
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: false
  mcp:
    enabled: true
    name_prefix: mcp
    servers:
      - name: demo
        transport: stdio
        command: fake
agents:
  echo:
    enabled: true
""".strip(),
        encoding="utf-8",
    )

    fake = FakeMcpClient(
        [McpToolSpec(name="ping", description="Ping")],
        handler=lambda _n, _a: "pong",
    )

    # Patch load path used by kernel by injecting factory via monkeypatch on load_mcp_tools
    import aeios.core.kernel as kernel_mod
    import aeios.tools.mcp as mcp_mod

    original = mcp_mod.load_mcp_tools

    def _load(mcp_cfg: dict[str, Any] | None, **kwargs: Any):
        return original(mcp_cfg, client_factory=lambda _c: fake, **kwargs)

    monkeypatch.setattr(kernel_mod, "load_mcp_tools", _load)

    settings = Settings(config_path=tmp_path / "configs" / "default.yaml")
    k = Kernel(settings=settings, workspace=tmp_path)
    assert "mcp_demo_ping" in k.tools

    # Syscall boundary: agents/kernel call_tool only
    result = k.syscalls.call_tool("mcp_demo_ping", x=1)
    assert result.ok is True
    assert result.output == "pong"
    assert fake.calls == [("ping", {"x": 1})]
    assert "mcp_demo_ping" in k.syscalls.list_tools()


def test_mcp_tool_failure_surfaces_as_tool_result() -> None:
    def _boom(_name: str, _args: dict[str, Any]) -> Any:
        raise RuntimeError("remote blew up")

    fake = FakeMcpClient(
        [McpToolSpec(name="boom")],
        handler=_boom,
    )
    bridge = McpBridge(
        [McpServerConfig(name="s", command="x")],
        client_factory=lambda _c: fake,
    )
    tool = bridge.discover_tools()[0]
    result = tool.run()
    assert result.ok is False
    assert "remote blew up" in (result.error or "")


def test_bridge_soft_fails_bad_server() -> None:
    def factory(cfg: McpServerConfig) -> FakeMcpClient:
        if cfg.name == "bad":
            raise ConnectionError("refused")
        return FakeMcpClient([McpToolSpec(name="ok")])

    bridge = McpBridge(
        [
            McpServerConfig(name="bad", command="x"),
            McpServerConfig(name="good", command="y"),
        ],
        client_factory=factory,
    )
    tools = bridge.discover_tools()
    assert len(tools) == 1
    assert tools[0].name == "mcp_good_ok"
    assert any("bad" in e for e in bridge.errors)
