from __future__ import annotations

from typing import Any

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo a message back (smoke / hello path)."

    def run(self, message: str = "", **_: Any) -> ToolResult:
        return ToolResult(ok=True, output=str(message))
