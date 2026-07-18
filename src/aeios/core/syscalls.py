from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, ToolResult

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel


class Syscalls:
    """Stable syscall boundary between interfaces and the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel

    def execute_task(
        self,
        goal: str,
        agent: str | None = None,
        *,
        wait: bool = True,
        owner_id: str = "local",
    ) -> Task:
        from aeios.observability.metrics import get_metrics

        get_metrics().record_task_started()
        # Finished metric is recorded in Kernel._execute_queued.
        if wait:
            return self._kernel.run_goal(goal, agent=agent, owner_id=owner_id)
        return self._kernel.run_goal_async(goal, agent=agent, owner_id=owner_id)

    def get_task(
        self, task_id: str, *, owner_id: str | None = None
    ) -> Task | None:
        return self._kernel.get_task(task_id, owner_id=owner_id)

    def list_tasks(
        self, limit: int = 50, *, owner_id: str | None = None
    ) -> list[Task]:
        return self._kernel.list_tasks(limit=limit, owner_id=owner_id)

    def cancel_task(
        self, task_id: str, *, owner_id: str | None = None
    ) -> Task | None:
        task = self._kernel.get_task(task_id, owner_id=owner_id)
        if not task:
            return None
        return self._kernel.request_cancel(task_id)

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
