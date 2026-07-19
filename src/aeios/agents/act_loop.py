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
_MAX_INVALID_ACTIONS = 3
_MAX_LLM_RETRIES = 2
_MAX_CONSECUTIVE_TOOL_FAILURES = 3
_HISTORY_KEEP = 16

# Compact schemas injected into the system prompt so the model knows args.
_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "echo": {
        "args": {"message": "string"},
        "notes": "Echo a short message back.",
    },
    "filesystem": {
        "args": {
            "action": "list|read|write|update",
            "path": "string (relative, no ..)",
            "content": "string (write/update)",
            "mode": "replace|append (update only)",
        },
        "notes": "Workspace jail only. Prefer write for new files.",
    },
    "shell": {
        "args": {"command": "string (allowlisted binary)"},
        "notes": "Sandboxed; cwd is the workspace root.",
    },
    "http": {
        "args": {
            "method": "GET|HEAD|POST",
            "url": "http(s) URL",
            "body": "optional string",
        },
        "notes": "http/https only; response body may be truncated.",
    },
}


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
    max_steps: int | None = None,
    client: ModelClient | None = None,
) -> bool:
    """Run an LLM-driven act loop. Return False if no model (use heuristics)."""
    model = resolve_act_model(agent, task.owner_id)
    if model is None:
        return False

    if max_steps is None:
        max_steps = _max_steps_from_kernel(agent)
    max_steps = max(1, int(max_steps))

    llm = client or ModelClient(settings=agent.kernel.settings)
    tools = sorted(agent.kernel.tools.keys())
    system = _system_prompt(agent.role, tools)
    messages: list[dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"Goal: {task.goal}\n"
                f"Plan: {' → '.join(task.plan) if task.plan else '(none yet)'}\n"
                "Take the next action as a single JSON object."
            ),
        }
    ]

    task.steps.append(
        {
            "step": "llm_act_start",
            "status": "ok",
            "observation": f"LLM act loop via {model.provider}/{model.model_id}",
            "model_id": model.id,
            "max_steps": max_steps,
        }
    )

    invalid_actions = 0
    consecutive_tool_failures = 0
    steps_done = 0

    while steps_done < max_steps:
        if agent.kernel.is_cancel_requested(task.id):
            return _finish_cancelled(task)

        raw, llm_error = _llm_complete(llm, model, system, messages)
        if llm_error is not None:
            task.steps.append(
                {
                    "step": "llm_act",
                    "status": "error",
                    "attempt": steps_done + 1,
                    "error": llm_error,
                    "observation": f"LLM call failed after retries: {llm_error}",
                }
            )
            task.status = TaskStatus.FAILED
            task.error = llm_error
            task.touch()
            return True

        action = _parse_action(raw)
        task.steps.append(
            {
                "step": "llm_decide",
                "status": "ok" if action else "error",
                "attempt": steps_done + 1,
                "output": action,
                "raw": (raw or "")[:800],
                "observation": (
                    f"action={action.get('action')}" if action else "invalid LLM JSON"
                ),
            }
        )

        if not action:
            invalid_actions += 1
            messages.append({"role": "assistant", "content": raw or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Invalid JSON. Reply with ONLY one JSON object:\n"
                        '{"action":"tool","tool":"<name>","args":{...}}\n'
                        'or {"action":"done","result":"..."}\n'
                        'or {"action":"fail","error":"..."}.'
                    ),
                }
            )
            messages = _trim_messages(messages)
            if invalid_actions >= _MAX_INVALID_ACTIONS:
                task.status = TaskStatus.FAILED
                task.error = (
                    f"LLM returned invalid actions {_MAX_INVALID_ACTIONS} times"
                )
                task.touch()
                return True
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
            invalid_actions += 1
            messages.append({"role": "assistant", "content": json.dumps(action)})
            messages.append(
                {
                    "role": "user",
                    "content": 'Unknown action. Use "tool", "done", or "fail".',
                }
            )
            messages = _trim_messages(messages)
            if invalid_actions >= _MAX_INVALID_ACTIONS:
                task.status = TaskStatus.FAILED
                task.error = "LLM kept returning unknown actions"
                task.touch()
                return True
            continue

        tool_name = str(action.get("tool") or "").strip()
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        validation_error = _validate_tool_call(agent, tool_name, args)
        if validation_error:
            invalid_actions += 1
            messages.append({"role": "assistant", "content": json.dumps(action)})
            messages.append(
                {
                    "role": "user",
                    "content": f"Invalid tool call: {validation_error}. Try again.",
                }
            )
            messages = _trim_messages(messages)
            task.steps.append(
                {
                    "step": "llm_tool_validate",
                    "status": "error",
                    "tool": tool_name,
                    "args": args,
                    "error": validation_error,
                    "observation": validation_error,
                }
            )
            if invalid_actions >= _MAX_INVALID_ACTIONS:
                task.status = TaskStatus.FAILED
                task.error = validation_error
                task.touch()
                return True
            continue

        # Valid action path — reset invalid counter
        invalid_actions = 0

        if agent.kernel.is_cancel_requested(task.id):
            return _finish_cancelled(task)

        result = agent.call_tool(tool_name, **args)
        steps_done += 1
        obs = _summarize_tool(tool_name, result.ok, result.output, result.error)
        task.steps.append(
            {
                "step": "llm_tool",
                "status": "ok" if result.ok else "error",
                "tool": tool_name,
                "args": _safe_args(args),
                "output": _truncate(result.output),
                "error": result.error,
                "observation": obs,
                "attempt": steps_done,
            }
        )

        if result.ok:
            consecutive_tool_failures = 0
        else:
            consecutive_tool_failures += 1

        messages.append({"role": "assistant", "content": json.dumps(action)})
        follow = (
            f"Tool {tool_name} → ok={result.ok}\n"
            f"Output: {_truncate(result.output)}\n"
            f"Error: {result.error or 'none'}\n"
            f"Steps used: {steps_done}/{max_steps}.\n"
        )
        if consecutive_tool_failures >= _MAX_CONSECUTIVE_TOOL_FAILURES:
            follow += (
                "Several tools failed in a row. Either try a different approach "
                'or finish with {"action":"fail","error":"..."} / '
                '{"action":"done","result":"..."}.\n'
            )
        else:
            follow += "Continue with the next JSON action."
        messages.append({"role": "user", "content": follow})
        messages = _trim_messages(messages)

    # Budget exhausted — summarize progress rather than silently claiming success.
    observations = [
        str(s.get("observation"))
        for s in task.steps
        if isinstance(s, dict) and s.get("observation")
    ]
    tail = "; ".join(observations[-5:]) if observations else "no observations"
    task.status = TaskStatus.COMPLETED
    task.result = (
        f"Act loop reached step budget ({max_steps}) without an explicit done.\n"
        f"Goal: {task.goal}\n"
        f"Recent: {tail}"
    )
    task.touch()
    return True


def _max_steps_from_kernel(agent: BaseAgent) -> int:
    try:
        cfg = agent.kernel.yaml.get("kernel", {}) or {}
        return int(cfg.get("max_act_steps", _DEFAULT_MAX_STEPS))
    except Exception:  # noqa: BLE001
        return _DEFAULT_MAX_STEPS


def _llm_complete(
    llm: ModelClient,
    model: ModelRecord,
    system: str,
    messages: list[dict[str, str]],
) -> tuple[str | None, str | None]:
    last_error: str | None = None
    for attempt in range(1, _MAX_LLM_RETRIES + 1):
        try:
            if hasattr(llm, "complete_messages"):
                text = llm.complete_messages(
                    model,
                    system=system,
                    messages=messages,
                    temperature=0.2,
                    timeout=45.0,
                )
            else:
                # Test doubles may only implement complete()
                text = llm.complete(
                    model,
                    system=system,
                    user=_flatten_messages(messages),
                    temperature=0.2,
                    timeout=45.0,
                )
            return text, None
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= _MAX_LLM_RETRIES:
                break
    return None, last_error or "LLM call failed"


def _finish_cancelled(task: Task) -> bool:
    task.status = TaskStatus.CANCELLED
    task.error = task.error or "Cancelled by user"
    task.touch()
    return True


def _validate_tool_call(
    agent: BaseAgent, tool_name: str, args: dict[str, Any]
) -> str | None:
    if not tool_name:
        return 'Tool actions require "tool" and "args"'
    if tool_name not in agent.kernel.tools:
        available = ", ".join(sorted(agent.kernel.tools.keys())) or "(none)"
        return f"Unknown tool {tool_name!r}. Available: {available}"
    if tool_name == "filesystem":
        action = str(args.get("action") or "").lower()
        if action not in {"list", "read", "write", "update"}:
            return "filesystem.action must be list|read|write|update"
        path = args.get("path")
        if action != "list" and (not isinstance(path, str) or not path.strip()):
            return "filesystem requires a non-empty path"
        if isinstance(path, str) and ".." in path.replace("\\", "/").split("/"):
            return "filesystem path must not contain .."
        if action in {"write", "update"} and "content" not in args:
            return f"filesystem.{action} requires content"
    if tool_name == "shell":
        cmd = args.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return "shell requires command"
    if tool_name == "http":
        url = args.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return "http requires an http(s) url"
    if tool_name == "echo":
        if "message" not in args:
            return "echo requires message"
    return None


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """Truncate large content fields before persisting on task.steps."""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if key == "content" and isinstance(value, str) and len(value) > 500:
            out[key] = value[:500] + "…"
        else:
            out[key] = value
    return out


def _system_prompt(role: str, tools: list[str]) -> str:
    schemas: list[str] = []
    for name in tools:
        base = name.split("_", 1)[0] if name.startswith("mcp_") else name
        schema = _TOOL_SCHEMAS.get(name) or _TOOL_SCHEMAS.get(base)
        if schema:
            schemas.append(f"- {name}: {json.dumps(schema, separators=(',', ':'))}")
        else:
            schemas.append(f"- {name}: args object (provider-specific)")
    schema_block = "\n".join(schemas) if schemas else "- (no tools registered)"
    return (
        f"You are an AEIOS {role} agent executing a goal with tools.\n"
        "Reply with ONLY one JSON object each turn (no markdown):\n"
        '  {"action":"tool","tool":"<name>","args":{...}}\n'
        '  {"action":"done","result":"<summary for the user>"}\n'
        '  {"action":"fail","error":"<why>"}\n'
        "Tool schemas:\n"
        f"{schema_block}\n"
        "Prefer small, correct tool args. Finish with done when the goal is met.\n"
        "If a tool fails, adapt (different path/args) or fail with a clear error."
    )


def _flatten_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for msg in messages[-_HISTORY_KEEP:]:
        parts.append(f"{msg['role'].upper()}: {msg['content']}")
    return "\n\n".join(parts)


def _trim_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(messages) <= _HISTORY_KEEP:
        return messages
    # Keep the first user goal message + recent tail
    head = messages[:1]
    tail = messages[-(_HISTORY_KEEP - 1) :]
    return head + tail


def _parse_action(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
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
