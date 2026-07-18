from __future__ import annotations

from typing import Any

import httpx

from aeios.config import Settings, get_settings
from aeios.observability.metrics import get_metrics
from aeios.persistence.models import ModelRecord, resolve_api_key


def _usage_from_openai(data: dict[str, Any]) -> tuple[int, int, int]:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    return prompt, completion, total


def _usage_from_anthropic(data: dict[str, Any]) -> tuple[int, int, int]:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    prompt = int(usage.get("input_tokens") or 0)
    completion = int(usage.get("output_tokens") or 0)
    return prompt, completion, prompt + completion


class ModelClient:
    """Thin multi-provider chat client for planning / smoke tests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def complete(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        timeout: float = 30.0,
    ) -> str:
        try:
            if model.provider in {"openai", "ollama"}:
                text, prompt, completion, total = self._openai_compatible(
                    model, system=system, user=user, temperature=temperature, timeout=timeout
                )
            elif model.provider == "anthropic":
                text, prompt, completion, total = self._anthropic(
                    model, system=system, user=user, temperature=temperature, timeout=timeout
                )
            else:
                raise ValueError(f"Unsupported provider: {model.provider}")
        except Exception:
            get_metrics().record_llm_call(provider=model.provider, ok=False)
            raise

        get_metrics().record_llm_call(
            provider=model.provider,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            ok=True,
        )
        return text

    def _resolved_key(self, model: ModelRecord) -> str | None:
        return resolve_api_key(model, self.settings or get_settings())

    def _openai_compatible(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float,
        timeout: float,
    ) -> tuple[str, int, int, int]:
        base = (model.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._resolved_key(model)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload: dict[str, Any] = {
            "model": model.model_id,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = str(data["choices"][0]["message"]["content"])
        prompt, completion, total = _usage_from_openai(data)
        return text, prompt, completion, total

    def _anthropic(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float,
        timeout: float,
    ) -> tuple[str, int, int, int]:
        api_key = self._resolved_key(model)
        if not api_key:
            raise ValueError(
                "Anthropic model requires an API key "
                "(store encrypted with AEIOS_SECRETS_KEY or set ANTHROPIC_API_KEY)"
            )
        base = (model.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload: dict[str, Any] = {
            "model": model.model_id,
            "max_tokens": 1024,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        prompt, completion, total = _usage_from_anthropic(data)
        return "".join(texts), prompt, completion, total
