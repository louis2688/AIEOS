from __future__ import annotations

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus


class SoftwareEngineerAgent(BaseAgent):
    name = "software_engineer"
    role = "implementation"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        task.plan = self.plan(task.goal)
        task.touch()

        listing = self.call_tool("filesystem", action="list", path=".")
        task.steps.append(
            {
                "step": "list_workspace",
                "status": "ok" if listing.ok else "error",
                "output": listing.output,
                "error": listing.error,
            }
        )

        if task.goal.strip().lower() in {"hello", "hi", "ping"}:
            echo = self.call_tool("echo", message="AEIOS kernel online.")
            task.steps.append(
                {
                    "step": "hello",
                    "status": "ok" if echo.ok else "error",
                    "output": echo.output,
                    "error": echo.error,
                }
            )
            task.status = TaskStatus.COMPLETED if echo.ok else TaskStatus.FAILED
            task.result = str(echo.output) if echo.ok else None
            task.error = echo.error
            task.touch()
            return task

        # Deterministic stub until LLM planning is wired.
        task.status = TaskStatus.COMPLETED
        task.result = (
            f"Accepted goal: {task.goal}\n"
            f"Workspace entries: {listing.output if listing.ok else 'unavailable'}\n"
            "Next: attach LLM planner (Phase 1) for real implementation steps."
        )
        task.touch()
        return task
