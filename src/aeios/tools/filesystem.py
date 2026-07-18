from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = "Read, write, update, or list files inside the workspace jail."

    def __init__(self, root: Path, allow_write: bool = False) -> None:
        self.root = root.resolve()
        self.allow_write = allow_write

    def run(
        self,
        action: str = "read",
        path: str = "",
        content: str = "",
        mode: str = "replace",
        **_: Any,
    ) -> ToolResult:
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
            if not path or path in {".", "./"}:
                return ToolResult(ok=False, error="Write requires a file path")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, str) else str(content)
            target.write_text(data, encoding="utf-8")
            nbytes = len(data.encode("utf-8"))
            return ToolResult(
                ok=True,
                output={
                    "path": self._rel(target),
                    "bytes": nbytes,
                    "action": "write",
                },
            )

        if action == "update":
            if not self.allow_write:
                return ToolResult(ok=False, error="Write disabled in config")
            if not path or path in {".", "./"}:
                return ToolResult(ok=False, error="Update requires a file path")
            if not target.is_file():
                return ToolResult(ok=False, error=f"Not a file (use write to create): {path}")
            data = content if isinstance(content, str) else str(content)
            if mode == "append":
                existing = target.read_text(encoding="utf-8")
                merged = existing + data
            else:
                merged = data
            target.write_text(merged, encoding="utf-8")
            nbytes = len(merged.encode("utf-8"))
            return ToolResult(
                ok=True,
                output={
                    "path": self._rel(target),
                    "bytes": nbytes,
                    "action": "update",
                    "mode": mode if mode in {"replace", "append"} else "replace",
                },
            )

        if action == "list":
            if not target.exists():
                return ToolResult(ok=False, error=f"Path not found: {path}")
            if target.is_file():
                return ToolResult(ok=True, output=[target.name])
            names = sorted(p.name for p in target.iterdir())
            return ToolResult(ok=True, output=names)

        return ToolResult(ok=False, error=f"Unknown action: {action}")

    def _rel(self, target: Path) -> str:
        try:
            return str(target.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return target.name

    def _resolve(self, path: str) -> Path:
        if not path:
            return self.root
        # Normalize separators; reject absolute paths that are outside root.
        raw = path.replace("\\", "/").lstrip("/")
        candidate = (self.root / raw).resolve()
        if not self._is_inside(candidate):
            raise ValueError("Path escapes workspace jail")
        return candidate

    def _is_inside(self, candidate: Path) -> bool:
        try:
            candidate.relative_to(self.root)
            return True
        except ValueError:
            return False
