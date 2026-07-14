from __future__ import annotations

import json
import re
from typing import Any

import httpx

from aeios.config import Settings


class Planner:
    """Deterministic planner with optional OpenAI-compatible LLM enhancement."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def plan(self, goal: str, agent_role: str = "software_engineer") -> list[str]:
        deterministic = self.deterministic_plan(goal, agent_role)
        if not self.settings.openai_api_key:
            return deterministic
        try:
            llm_plan = self._llm_plan(goal, agent_role)
            return llm_plan or deterministic
        except Exception:  # noqa: BLE001 — fall back silently
            return deterministic

    def deterministic_plan(self, goal: str, agent_role: str = "software_engineer") -> list[str]:
        lowered = goal.strip().lower()
        if lowered in {"hello", "hi", "ping"}:
            return ["Acknowledge goal", "Call echo tool", "Return greeting"]

        if agent_role == "architect":
            return [
                "Clarify constraints and success criteria",
                "Propose module boundaries",
                "List risks and open questions",
            ]

        if any(k in lowered for k in ("shell", "command", "pwd", "ls ")):
            return [
                "Acknowledge goal",
                "Run sandboxed shell inspection",
                "Summarize findings",
            ]

        return [
            "Acknowledge goal",
            "Inspect workspace listing",
            "Propose next implementation step",
        ]

    def _llm_plan(self, goal: str, agent_role: str) -> list[str] | None:
        """Call OpenAI-compatible chat completions; return step list or None."""
        api_key = self.settings.openai_api_key
        if not api_key:
            return None

        payload: dict[str, Any] = {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an AEIOS planner. Return ONLY a JSON array of 3-6 short "
                        f"action steps for a {agent_role} agent. No markdown."
                    ),
                },
                {"role": "user", "content": goal},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

        return self._parse_steps(content)

    @staticmethod
    def _parse_steps(content: str) -> list[str] | None:
        text = content.strip()
        # Strip fenced code if present
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            return None
        steps = [s.strip() for s in data if s.strip()]
        return steps or None
