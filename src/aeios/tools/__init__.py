"""AEIOS tools — lazy exports to avoid circular imports with the kernel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["EchoTool", "FilesystemTool", "ShellTool"]

if TYPE_CHECKING:
    from aeios.tools.echo import EchoTool
    from aeios.tools.filesystem import FilesystemTool
    from aeios.tools.shell import ShellTool


def __getattr__(name: str) -> Any:
    if name == "EchoTool":
        from aeios.tools.echo import EchoTool

        return EchoTool
    if name == "FilesystemTool":
        from aeios.tools.filesystem import FilesystemTool

        return FilesystemTool
    if name == "ShellTool":
        from aeios.tools.shell import ShellTool

        return ShellTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
