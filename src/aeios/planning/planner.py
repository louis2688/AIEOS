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

    def plan(
        self,
        goal: str,
        agent_role: str = "software_engineer",
        *,
        owner_id: str | None = None,
    ) -> list[str]:
        deterministic = self.deterministic_plan(goal, agent_role)
        model = self._resolve_model(owner_id=owner_id)
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
            steps = [
                "Clarify constraints and success criteria",
                "Inspect workspace module boundaries",
                "Propose module boundaries",
                "List risks and open questions",
            ]
            if "http://" in lowered or "https://" in lowered:
                steps.insert(2, "Fetch external reference over HTTP")
            if any(
                k in lowered
                for k in (
                    "write",
                    "document",
                    "save",
                    "persist",
                    "architecture.md",
                    "outline",
                    "design",
                )
            ):
                steps.append("Write short ARCHITECTURE.md in workspace jail")
            return steps

        if any(
            k in lowered
            for k in (
                "implement",
                "create ",
                "write ",
                "edit ",
                "update ",
                "scaffold",
                "generate ",
            )
        ):
            return [
                "Acknowledge goal",
                "Inspect workspace listing",
                "Write or update target file in workspace jail",
                "Summarize observations",
            ]

        if any(k in lowered for k in ("shell", "command", "pwd", "ls ")):
            return [
                "Acknowledge goal",
                "Run sandboxed shell inspection",
                "Summarize findings",
            ]

        if any(k in lowered for k in ("http://", "https://", "fetch ", "download ")):
            return [
                "Acknowledge goal",
                "Inspect workspace listing",
                "Fetch URL with sandboxed HTTP tool",
                "Summarize observations",
            ]

        return [
            "Acknowledge goal",
            "Inspect workspace listing",
            "Propose next implementation step",
        ]

    def reflect(
        self,
        goal: str,
        tool: str,
        error: str,
        attempt: int,
        agent_role: str = "software_engineer",
    ) -> tuple[str, list[str]]:
        """Produce a short reflection and a revised plan after a tool failure."""
        reflection = (
            f"Tool '{tool}' failed on attempt {attempt}: {error}. "
            "Re-planning with the same goal and retrying the step."
        )
        revised = self.deterministic_plan(goal, agent_role=agent_role)
        # Surface the failure in the plan so task steps/audit stay inspectable.
        revised = [
            f"Reflect on {tool} failure: {error}",
            *revised,
            f"Retry {tool} (attempt {attempt + 1})",
        ]
        return reflection, revised

    def _resolve_model(self, *, owner_id: str | None = None) -> ModelRecord | None:
        if self.model_store:
            model = self.model_store.get_default(owner_id=owner_id)
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
