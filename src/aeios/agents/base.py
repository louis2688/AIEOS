from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, ToolResult

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel
    from aeios.models.client import ModelClient


class BaseAgent(ABC):
    name: str
    role: str = "agent"

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def plan(self, goal: str, *, owner_id: str | None = None) -> list[str]:
        return self.kernel.planner.plan(
            goal, agent_role=self.role, owner_id=owner_id
        )

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        return self.kernel.call_tool(name, **kwargs)

    def run_with_optional_llm(
        self,
        task: Task,
        heuristic,
        *,
        client: ModelClient | None = None,
        max_steps: int = 8,
    ) -> Task:
        """Plan, then LLM act loop if a model is available, else ``heuristic(task)``."""
        from aeios.agents.act_loop import try_llm_act
        from aeios.core.types import TaskStatus

        task.status = TaskStatus.RUNNING
        task.plan = self.plan(task.goal, owner_id=task.owner_id)
        task.touch()
        if try_llm_act(self, task, max_steps=max_steps, client=client):
            return task
        return heuristic(task)

    @abstractmethod
    def execute(self, task: Task) -> Task:
        raise NotImplementedError
