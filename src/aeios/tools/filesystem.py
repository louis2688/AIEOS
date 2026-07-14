from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = "Read files inside the workspace jail."

    def __init__(self, root: Path, allow_write: bool = False) -> None:
        self.root = root.resolve()
        self.allow_write = allow_write

    def run(self, action: str = "read", path: str = "", content: str = "", **_: Any) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as exc:
            return ToolResult(ok=False, error=str(exc))

        if action == "read":
            if not target.is_file():
                return ToolResult(ok=False, error=f"Not a file: {path}")
            return ToolResult(ok=True, output=target.read_text(encoding="utf-8"))

        if action == "write":
            if not self.allow_write:
                return ToolResult(ok=False, error="Write disabled in config")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(ok=True, output=f"Wrote {target}")

        if action == "list":
            if not target.exists():
                return ToolResult(ok=False, error=f"Path not found: {path}")
            if target.is_file():
                return ToolResult(ok=True, output=[target.name])
            names = sorted(p.name for p in target.iterdir())
            return ToolResult(ok=True, output=names)

        return ToolResult(ok=False, error=f"Unknown action: {action}")

    def _resolve(self, path: str) -> Path:
        if not path:
            return self.root
        candidate = (self.root / path).resolve()
        if not str(candidate).startswith(str(self.root)):
            raise ValueError("Path escapes workspace jail")
        return candidate
