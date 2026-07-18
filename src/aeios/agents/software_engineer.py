from __future__ import annotations

import re

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _extract_url(goal: str) -> str | None:
    match = _URL_RE.search(goal)
    return match.group(0).rstrip(".,);]") if match else None


class SoftwareEngineerAgent(BaseAgent):
    name = "software_engineer"
    role = "software_engineer"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        # Plan
        task.plan = self.plan(task.goal)
        task.touch()

        observations: list[str] = []
        goal_l = task.goal.lower()

        # Act → observe: workspace listing
        listing = self.call_tool("filesystem", action="list", path=".")
        task.steps.append(
            {
                "step": "list_workspace",
                "status": "ok" if listing.ok else "error",
                "output": listing.output,
                "error": listing.error,
            }
        )
        if listing.ok:
            entries = listing.output if isinstance(listing.output, list) else [listing.output]
            observations.append(f"workspace: {len(entries)} entries")

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

        # Act → observe: sandboxed shell when goal implies it
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
            if shell.ok and isinstance(shell.output, dict):
                observations.append(f"cwd: {(shell.output.get('stdout') or '').strip()}")
            elif not shell.ok:
                observations.append(f"shell error: {shell.error}")

        # Act → observe: HTTP fetch when URL or fetch/http keywords present
        url = _extract_url(task.goal)
        wants_http = url is not None or any(
            k in goal_l for k in ("http", "fetch", "download", "api endpoint")
        )
        if wants_http and "http" in self.kernel.tools and url:
            http = self.call_tool("http", method="GET", url=url)
            body_preview = ""
            if isinstance(http.output, dict):
                body = str(http.output.get("body") or "")
                body_preview = body[:400]
            task.steps.append(
                {
                    "step": "http_fetch",
                    "status": "ok" if http.ok else "error",
                    "url": url,
                    "output": (
                        {
                            "status_code": http.output.get("status_code")
                            if isinstance(http.output, dict)
                            else None,
                            "truncated": http.output.get("truncated")
                            if isinstance(http.output, dict)
                            else None,
                            "body_preview": body_preview,
                        }
                        if http.output
                        else None
                    ),
                    "error": http.error,
                }
            )
            if http.ok and isinstance(http.output, dict):
                observations.append(
                    f"http {http.output.get('status_code')} from {url} "
                    f"({http.output.get('bytes', 0)} bytes)"
                )
            else:
                observations.append(f"http error for {url}: {http.error}")

        # Lightweight read when goal names a workspace file that exists
        if listing.ok and isinstance(listing.output, list):
            named = self._maybe_read_named_file(task, listing.output, observations)
            if named:
                pass  # step already recorded

        task.status = TaskStatus.COMPLETED
        obs_block = "; ".join(observations) if observations else "none"
        task.result = (
            f"Accepted goal: {task.goal}\n"
            f"Plan: {' → '.join(task.plan)}\n"
            f"Observations: {obs_block}\n"
            f"Workspace entries: {listing.output if listing.ok else 'unavailable'}"
        )
        task.touch()
        return task

    def _maybe_read_named_file(
        self,
        task: Task,
        entries: list[str],
        observations: list[str],
    ) -> bool:
        """If the goal mentions a top-level file, read it (observe)."""
        goal_l = task.goal.lower()
        for name in entries:
            if not name or name.startswith("."):
                continue
            if name.lower() in goal_l and ("." in name or name.lower() in {"readme", "makefile"}):
                read = self.call_tool("filesystem", action="read", path=name)
                task.steps.append(
                    {
                        "step": "read_file",
                        "status": "ok" if read.ok else "error",
                        "path": name,
                        "output": (str(read.output)[:500] if read.ok else None),
                        "error": read.error,
                    }
                )
                if read.ok:
                    observations.append(f"read {name} ({len(str(read.output))} chars)")
                return True
        return False
