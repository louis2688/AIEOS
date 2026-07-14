from __future__ import annotations

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus


class EchoAgent(BaseAgent):
    name = "echo"
    role = "smoke"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        task.plan = self.plan(task.goal)
        task.touch()

        for step in task.plan:
            task.steps.append({"step": step, "status": "started"})

        result = self.call_tool("echo", message=f"AEIOS received: {task.goal}")
        task.steps.append(
            {
                "step": "echo",
                "status": "ok" if result.ok else "error",
                "output": result.output,
                "error": result.error,
            }
        )

        if not result.ok:
            task.status = TaskStatus.FAILED
            task.error = result.error
            task.touch()
            return task

        task.status = TaskStatus.COMPLETED
        task.result = str(result.output)
        task.touch()
        return task
