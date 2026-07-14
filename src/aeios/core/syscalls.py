from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, ToolResult

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel


class Syscalls:
    """Stable syscall boundary between interfaces and the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel

    def execute_task(self, goal: str, agent: str | None = None) -> Task:
        return self._kernel.run_goal(goal, agent=agent)

    def request_memory(self, action: str, key: str, value: Any = None) -> Any:
        if action == "get":
            return self._kernel.memory.get(key)
        if action == "set":
            self._kernel.memory.set(key, value)
            return True
        if action == "list":
            return self._kernel.memory.keys()
        raise ValueError(f"Unknown memory action: {action}")

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        return self._kernel.call_tool(name, **kwargs)

    def list_agents(self) -> list[str]:
        return sorted(self._kernel.agents.keys())

    def list_tools(self) -> list[str]:
        return sorted(self._kernel.tools.keys())
