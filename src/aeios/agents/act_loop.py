"""Shared LLM observe → act → reflect loop for AEIOS agents.

When a task owner has a library model, agents call ``try_llm_act`` to drive
tool use via a simple JSON protocol. Callers fall back to heuristics when this
returns False (no model / auth-scoped env key unavailable).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from aeios.core.types import Task, TaskStatus
from aeios.models.client import ModelClient

if TYPE_CHECKING:
    from aeios.agents.base import BaseAgent
    from aeios.persistence.models import ModelRecord

_MAX_OUTPUT_CHARS = 2_000
_DEFAULT_MAX_STEPS = 8


def resolve_act_model(agent: BaseAgent, owner_id: str | None) -> ModelRecord | None:
    """Resolve a library model for the act loop.

    Uses ``ModelStore.get_default`` only — no silent env-key synthetic model.
    Heuristic agent paths remain available when the library is empty.
    """
    store = getattr(agent.kernel, "models", None)
    if store is None:
        return None
    model = store.get_default(owner_id=owner_id)
    if model and model.enabled:
        return model
    return None


def try_llm_act(
    agent: BaseAgent,
    task: Task,
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
    client: ModelClient | None = None,
) -> bool:
    """Run an LLM-driven act loop. Return False if no model (use heuristics)."""
    model = resolve_act_model(agent, task.owner_id)
    if model is None:
        return False

    llm = client or ModelClient(settings=agent.kernel.settings)
    tools = sorted(agent.kernel.tools.keys())
    system = _system_prompt(agent.role, tools)
    history: list[dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"Goal: {task.goal}\n"
                f"Plan: {' → '.join(task.plan) if task.plan else '(none yet)'}\n"
                "Take the next action."
            ),
        }
    ]

    task.steps.append(
        {
            "step": "llm_act_start",
            "status": "ok",
            "observation": f"LLM act loop via {model.provider}/{model.model_id}",
            "model_id": model.id,
        }
    )

    for step_i in range(max(1, max_steps)):
        if agent.kernel.is_cancel_requested(task.id):
            task.status = TaskStatus.CANCELLED
            task.error = task.error or "Cancelled by user"
            task.touch()
            return True

        try:
            raw = llm.complete(
                model,
                system=system,
                user=_history_as_user(history),
                temperature=0.2,
                timeout=45.0,
            )
        except Exception as exc:  # noqa: BLE001
            task.steps.append(
                {
                    "step": "llm_act",
                    "status": "error",
                    "attempt": step_i + 1,
                    "error": str(exc),
                    "observation": f"LLM call failed: {exc}",
                }
            )
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.touch()
            return True

        action = _parse_action(raw)
        task.steps.append(
            {
                "step": "llm_decide",
                "status": "ok" if action else "error",
                "attempt": step_i + 1,
                "output": action,
                "raw": raw[:800],
                "observation": (
                    f"action={action.get('action')}" if action else "invalid LLM JSON"
                ),
            }
        )
        if not action:
            history.append({"role": "assistant", "content": raw})
            history.append(
                {
                    "role": "user",
                    "content": (
                        "Invalid JSON. Reply with only a JSON object: "
                        '{"action":"tool","tool":"<name>","args":{...}} or '
                        '{"action":"done","result":"..."} or '
                        '{"action":"fail","error":"..."}.'
                    ),
                }
            )
            continue

        kind = str(action.get("action") or "").lower()
        if kind == "done":
            task.result = str(action.get("result") or "Done.")
            task.status = TaskStatus.COMPLETED
            task.error = None
            task.touch()
            return True
        if kind == "fail":
            task.error = str(action.get("error") or "Agent reported failure")
            task.status = TaskStatus.FAILED
            task.touch()
            return True
        if kind != "tool":
            history.append({"role": "assistant", "content": raw})
            history.append(
                {
                    "role": "user",
                    "content": 'Unknown action. Use "tool", "done", or "fail".',
                }
            )
            continue

        tool_name = str(action.get("tool") or "").strip()
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        if not tool_name:
            history.append({"role": "assistant", "content": raw})
            history.append(
                {"role": "user", "content": 'Tool actions require "tool" and "args".'}
            )
            continue

        if agent.kernel.is_cancel_requested(task.id):
            task.status = TaskStatus.CANCELLED
            task.error = task.error or "Cancelled by user"
            task.touch()
            return True

        result = agent.call_tool(tool_name, **args)
        obs = _summarize_tool(tool_name, result.ok, result.output, result.error)
        task.steps.append(
            {
                "step": "llm_tool",
                "status": "ok" if result.ok else "error",
                "tool": tool_name,
                "args": args,
                "output": _truncate(result.output),
                "error": result.error,
                "observation": obs,
                "attempt": step_i + 1,
            }
        )
        history.append({"role": "assistant", "content": json.dumps(action)})
        history.append(
            {
                "role": "user",
                "content": (
                    f"Tool {tool_name} → ok={result.ok}\n"
                    f"Output: {_truncate(result.output)}\n"
                    f"Error: {result.error or 'none'}\n"
                    "Continue with the next JSON action."
                ),
            }
        )

    # Budget exhausted without done/fail
    task.status = TaskStatus.COMPLETED
    task.result = task.result or (
        f"LLM act loop finished after {max_steps} steps without an explicit done. "
        f"Goal: {task.goal}"
    )
    task.touch()
    return True


def _system_prompt(role: str, tools: list[str]) -> str:
    tool_list = ", ".join(tools) if tools else "(none)"
    return (
        f"You are an AEIOS {role} agent executing a goal with tools.\n"
        f"Available tools: {tool_list}\n"
        "Reply with ONLY one JSON object (no markdown) each turn:\n"
        '  {"action":"tool","tool":"<name>","args":{...}}\n'
        '  {"action":"done","result":"<summary for the user>"}\n'
        '  {"action":"fail","error":"<why>"}\n'
        "Prefer filesystem list/read/write, shell (if available), http (if available), "
        "and echo. Keep args small. Finish with done when the goal is satisfied.\n"
        "filesystem args: action=list|read|write|update, path=..., content=... (for write/update).\n"
        "shell args: command=...\n"
        "http args: method=GET|POST, url=...\n"
        "echo args: message=..."
    )


def _history_as_user(history: list[dict[str, str]]) -> str:
    # ModelClient only accepts a single user string — flatten the dialogue.
    parts: list[str] = []
    for msg in history[-12:]:
        parts.append(f"{msg['role'].upper()}: {msg['content']}")
    return "\n\n".join(parts)


def _parse_action(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Find first JSON object if the model added prose
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _truncate(value: Any, limit: int = _MAX_OUTPUT_CHARS) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    try:
        blob = json.dumps(value, default=str)
    except TypeError:
        blob = str(value)
    if len(blob) <= limit:
        return value
    return blob[:limit] + "…"


def _summarize_tool(name: str, ok: bool, output: Any, error: str | None) -> str:
    if not ok:
        return f"{name} failed: {error}"
    if isinstance(output, dict):
        if "path" in output:
            return f"{name} ok path={output.get('path')} bytes={output.get('bytes')}"
        if "status_code" in output:
            return f"{name} ok status={output.get('status_code')}"
        if "stdout" in output:
            return f"{name} ok stdout={str(output.get('stdout') or '')[:120]}"
    if isinstance(output, list):
        return f"{name} ok ({len(output)} items)"
    return f"{name} ok"
