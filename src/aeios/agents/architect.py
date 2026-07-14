from __future__ import annotations

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus


class ArchitectAgent(BaseAgent):
    name = "architect"
    role = "design"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        task.plan = [
            "Clarify constraints",
            "Propose module boundaries",
            "List risks and open questions",
        ]
        task.touch()

        task.steps.append(
            {
                "step": "architecture_stub",
                "status": "ok",
                "output": {
                    "modules": ["kernel", "memory", "agents", "tools", "interfaces"],
                    "recommendation": "Keep CLI/kernel local-first; defer GraphQL/K8s.",
                    "goal": task.goal,
                },
            }
        )
        task.status = TaskStatus.COMPLETED
        task.result = (
            "Architecture stub complete. "
            "Kernel → agents/tools/memory → CLI/API/web. "
            f"Goal noted: {task.goal}"
        )
        task.touch()
        return task
