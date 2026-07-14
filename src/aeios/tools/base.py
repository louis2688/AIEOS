from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aeios.core.types import ToolResult


class BaseTool(ABC):
    name: str
    description: str = ""

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
