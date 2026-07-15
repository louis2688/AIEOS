from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from aeios.config import Settings
from aeios.models.client import ModelClient

if TYPE_CHECKING:
    from aeios.persistence.models import ModelRecord, ModelStore


class Planner:
    """Deterministic planner with optional LLM enhancement from the model library."""

    def __init__(
        self,
        settings: Settings | None = None,
        model_store: ModelStore | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.model_store = model_store
        self.client = ModelClient()

    def plan(self, goal: str, agent_role: str = "software_engineer") -> list[str]:
        deterministic = self.deterministic_plan(goal, agent_role)
        model = self._resolve_model()
        if not model:
            return deterministic
        try:
            llm_plan = self._llm_plan(goal, agent_role, model)
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

    def _resolve_model(self) -> ModelRecord | None:
        if self.model_store:
            model = self.model_store.get_default()
            if model and model.enabled:
                return model
        # Legacy fallback: env OpenAI key without library entry
        if self.settings.openai_api_key:
            from aeios.persistence.models import ModelRecord

            return ModelRecord(
                id="env-openai",
                name="Env OpenAI",
                provider="openai",
                model_id="gpt-4o-mini",
                base_url="https://api.openai.com/v1",
                api_key=self.settings.openai_api_key,
                is_default=True,
                enabled=True,
                created_at="",
                updated_at="",
            )
        return None

    def _llm_plan(self, goal: str, agent_role: str, model: ModelRecord) -> list[str] | None:
        system = (
            "You are an AEIOS planner. Return ONLY a JSON array of 3-6 short "
            f"action steps for a {agent_role} agent. No markdown."
        )
        content = self.client.complete(model, system=system, user=goal)
        return self._parse_steps(content)

    @staticmethod
    def _parse_steps(content: str) -> list[str] | None:
        text = content.strip()
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
