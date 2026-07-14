from __future__ import annotations

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus


class SoftwareEngineerAgent(BaseAgent):
    name = "software_engineer"
    role = "software_engineer"

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

        # Optional shell inspection when tool is registered and goal implies it
        goal_l = task.goal.lower()
        if "shell" in self.kernel.tools and any(
            k in goal_l for k in ("shell", "pwd", "ls ", "command")
        ):
            shell = self.call_tool("shell", command="pwd")
            task.steps.append(
                {
                    "step": "shell_pwd",
                    "status": "ok" if shell.ok else "error",
                    "output": shell.output,
                    "error": shell.error,
                }
            )

        task.status = TaskStatus.COMPLETED
        task.result = (
            f"Accepted goal: {task.goal}\n"
            f"Plan: {' → '.join(task.plan)}\n"
            f"Workspace entries: {listing.output if listing.ok else 'unavailable'}\n"
            "Next: expand LLM-backed implementation loop in Phase 1.x."
        )
        task.touch()
        return task
