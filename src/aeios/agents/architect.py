from __future__ import annotations

import re

from aeios.agents.base import BaseAgent
from aeios.core.types import Task, TaskStatus

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Top-level names that hint at module boundaries when present in the workspace.
_MODULE_HINTS = (
    "src",
    "apps",
    "configs",
    "tests",
    "api",
    "web",
    "agents",
    "tools",
    "kernel",
    "memory",
)


def _extract_url(goal: str) -> str | None:
    match = _URL_RE.search(goal)
    return match.group(0).rstrip(".,);]") if match else None


class ArchitectAgent(BaseAgent):
    name = "architect"
    role = "architect"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        # Plan
        task.plan = self.plan(task.goal)
        task.touch()

        observations: list[str] = []
        modules = ["kernel", "memory", "agents", "tools", "api", "web"]

        # Act → observe: ground outline in workspace layout
        listing = self.call_tool("filesystem", action="list", path=".")
        task.steps.append(
            {
                "step": "inspect_workspace",
                "status": "ok" if listing.ok else "error",
                "output": listing.output,
                "error": listing.error,
            }
        )
        if listing.ok and isinstance(listing.output, list):
            present = [n for n in listing.output if n.lower() in {h.lower() for h in _MODULE_HINTS}]
            if present:
                modules = sorted(set(modules) | set(present))
                observations.append(f"workspace modules: {', '.join(present)}")
            else:
                observations.append(f"workspace entries: {len(listing.output)}")

        # Act → observe: optional HTTP when goal references a URL (e.g. API docs)
        url = _extract_url(task.goal)
        if url and "http" in self.kernel.tools:
            http = self.call_tool("http", method="GET", url=url)
            preview = ""
            if isinstance(http.output, dict):
                preview = str(http.output.get("body") or "")[:300]
            task.steps.append(
                {
                    "step": "http_reference",
                    "status": "ok" if http.ok else "error",
                    "url": url,
                    "output": {
                        "status_code": (
                            http.output.get("status_code")
                            if isinstance(http.output, dict)
                            else None
                        ),
                        "body_preview": preview,
                    },
                    "error": http.error,
                }
            )
            if http.ok:
                observations.append(f"fetched reference {url}")
            else:
                observations.append(f"reference fetch failed: {http.error}")

        outline = {
            "modules": modules,
            "recommendation": "Keep CLI/kernel local-first; defer GraphQL/K8s.",
            "goal": task.goal,
            "plan": task.plan,
            "observations": observations,
        }
        task.steps.append(
            {
                "step": "architecture_outline",
                "status": "ok",
                "output": outline,
            }
        )

        task.status = TaskStatus.COMPLETED
        obs_block = "; ".join(observations) if observations else "none"
        task.result = (
            "Architecture outline complete.\n"
            f"Plan: {' → '.join(task.plan)}\n"
            f"Modules: {', '.join(modules)}\n"
            f"Observations: {obs_block}\n"
            f"Goal noted: {task.goal}"
        )
        task.touch()
        return task
