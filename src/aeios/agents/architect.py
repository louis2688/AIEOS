from __future__ import annotations

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus


class ArchitectAgent(BaseAgent):
    name = "architect"
    role = "architect"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        task.plan = self.plan(task.goal)
        task.touch()

        task.steps.append(
            {
                "step": "architecture_outline",
                "status": "ok",
                "output": {
                    "modules": ["kernel", "memory", "agents", "tools", "api", "web"],
                    "recommendation": "Keep CLI/kernel local-first; defer GraphQL/K8s.",
                    "goal": task.goal,
                    "plan": task.plan,
                },
            }
        )
        task.status = TaskStatus.COMPLETED
        task.result = (
            "Architecture outline complete.\n"
            f"Plan: {' → '.join(task.plan)}\n"
            "Kernel → agents/tools/memory → CLI/API/web.\n"
            f"Goal noted: {task.goal}"
        )
        task.touch()
        return task
