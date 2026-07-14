from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, ToolResult

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel


class BaseAgent(ABC):
    name: str
    role: str = "agent"

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def plan(self, goal: str) -> list[str]:
        return self.kernel.planner.plan(goal, agent_role=self.role)

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        return self.kernel.call_tool(name, **kwargs)

    @abstractmethod
    def execute(self, task: Task) -> Task:
        raise NotImplementedError
