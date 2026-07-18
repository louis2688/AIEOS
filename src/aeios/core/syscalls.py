from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, TaskStatus, ToolResult

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel


class Syscalls:
    """Stable syscall boundary between interfaces and the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel

    def execute_task(self, goal: str, agent: str | None = None) -> Task:
        from aeios.observability.metrics import get_metrics

        get_metrics().record_task_started()
        task = self._kernel.run_goal(goal, agent=agent)
        get_metrics().record_task_finished(ok=task.status == TaskStatus.COMPLETED)
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._kernel.get_task(task_id)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        return self._kernel.list_tasks(limit=limit)

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

    def doctor(self) -> dict[str, Any]:
        return self._kernel.doctor()
