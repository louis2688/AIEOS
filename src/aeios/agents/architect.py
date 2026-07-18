from __future__ import annotations

import re
from typing import Any

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
    "docs",
)

_DOC_HINTS = (
    "write",
    "document",
    "save",
    "persist",
    "architecture.md",
    "plan.md",
    "markdown",
)

_OUTLINE_HINTS = (
    "architecture",
    "architect",
    "outline",
    "design",
    "module",
    "boundaries",
)


def _extract_url(goal: str) -> str | None:
    match = _URL_RE.search(goal)
    return match.group(0).rstrip(".,);]") if match else None


def _wants_doc_file(goal: str) -> bool:
    goal_l = goal.lower()
    if any(k in goal_l for k in _DOC_HINTS):
        return True
    # Dogfood / pipeline: outline/design goals benefit from a persisted plan file.
    return any(k in goal_l for k in _OUTLINE_HINTS)


def _doc_path(goal: str, listing: list[str] | None) -> str:
    goal_l = goal.lower()
    if "plan.md" in goal_l:
        return "PLAN.md"
    if "architecture.md" in goal_l:
        if listing and "docs" in listing:
            return "docs/ARCHITECTURE.md"
        return "ARCHITECTURE.md"
    if listing and "docs" in listing:
        return "docs/ARCHITECTURE.md"
    return "ARCHITECTURE.md"


def _render_architecture_md(outline: dict[str, Any]) -> str:
    modules = outline.get("modules") or []
    plan = outline.get("plan") or []
    observations = outline.get("observations") or []
    lines = [
        "# Architecture outline",
        "",
        f"**Goal:** {outline.get('goal', '')}",
        "",
        "## Modules",
        "",
    ]
    for mod in modules:
        lines.append(f"- `{mod}`")
    lines.extend(["", "## Plan", ""])
    for i, step in enumerate(plan, 1):
        lines.append(f"{i}. {step}")
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            str(outline.get("recommendation", "")),
            "",
            "## Observations",
            "",
        ]
    )
    if observations:
        for obs in observations:
            lines.append(f"- {obs}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _step(
    name: str,
    *,
    status: str,
    output: Any = None,
    error: str | None = None,
    observation: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {"step": name, "status": status, "output": output, "error": error}
    if observation:
        row["observation"] = observation
    row.update(extra)
    return row


class ArchitectAgent(BaseAgent):
    name = "architect"
    role = "architect"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        # Plan
        task.plan = self.plan(task.goal, owner_id=task.owner_id)
        task.touch()

        observations: list[str] = []
        modules = ["kernel", "memory", "agents", "tools", "api", "web"]
        listing_names: list[str] | None = None

        # Act → observe: ground outline in workspace layout
        listing = self.call_tool("filesystem", action="list", path=".")
        if listing.ok and isinstance(listing.output, list):
            listing_names = listing.output
            present = [n for n in listing.output if n.lower() in {h.lower() for h in _MODULE_HINTS}]
            if present:
                modules = sorted(set(modules) | set(present))
                obs = f"workspace modules: {', '.join(present)}"
            else:
                obs = f"workspace entries: {len(listing.output)}"
            observations.append(obs)
        else:
            obs = f"inspect failed: {listing.error}"
            observations.append(obs)
        task.steps.append(
            _step(
                "inspect_workspace",
                status="ok" if listing.ok else "error",
                output=listing.output,
                error=listing.error,
                observation=obs,
            )
        )

        # Act → observe: optional HTTP when goal references a URL (e.g. API docs)
        url = _extract_url(task.goal)
        if url and "http" in self.kernel.tools:
            http = self.call_tool("http", method="GET", url=url)
            preview = ""
            if isinstance(http.output, dict):
                preview = str(http.output.get("body") or "")[:300]
            if http.ok:
                obs = f"fetched reference {url}"
            else:
                obs = f"reference fetch failed: {http.error}"
            observations.append(obs)
            task.steps.append(
                _step(
                    "http_reference",
                    status="ok" if http.ok else "error",
                    url=url,
                    output={
                        "status_code": (
                            http.output.get("status_code")
                            if isinstance(http.output, dict)
                            else None
                        ),
                        "body_preview": preview,
                    },
                    error=http.error,
                    observation=obs,
                )
            )

        outline = {
            "modules": modules,
            "recommendation": "Keep CLI/kernel local-first; defer GraphQL/K8s.",
            "goal": task.goal,
            "plan": task.plan,
            "observations": list(observations),
        }
        task.steps.append(
            _step(
                "architecture_outline",
                status="ok",
                output=outline,
                observation=f"outline with {len(modules)} modules",
            )
        )
        observations.append(f"outline with {len(modules)} modules")

        # Optionally persist a short ARCHITECTURE.md / PLAN.md for the next agent
        if _wants_doc_file(task.goal):
            path = _doc_path(task.goal, listing_names)
            body = _render_architecture_md(outline)
            write = self.call_tool("filesystem", action="write", path=path, content=body)
            if write.ok and isinstance(write.output, dict):
                obs = f"wrote {write.output.get('path', path)} ({write.output.get('bytes', 0)} bytes)"
                out = write.output
            elif write.ok:
                obs = f"wrote {path}"
                out = write.output
            else:
                obs = f"write {path} failed: {write.error}"
                out = None
            observations.append(obs)
            task.steps.append(
                _step(
                    "write_architecture_doc",
                    status="ok" if write.ok else "error",
                    path=path,
                    output=out,
                    error=write.error,
                    observation=obs,
                )
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
