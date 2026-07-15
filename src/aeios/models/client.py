from __future__ import annotations

from typing import Any

import httpx

from aeios.persistence.models import ModelRecord


class ModelClient:
    """Thin multi-provider chat client for planning / smoke tests."""

    def complete(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        timeout: float = 30.0,
    ) -> str:
        if model.provider in {"openai", "ollama"}:
            return self._openai_compatible(
                model, system=system, user=user, temperature=temperature, timeout=timeout
            )
        if model.provider == "anthropic":
            return self._anthropic(
                model, system=system, user=user, temperature=temperature, timeout=timeout
            )
        raise ValueError(f"Unsupported provider: {model.provider}")

    def _openai_compatible(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float,
        timeout: float,
    ) -> str:
        base = (model.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if model.api_key:
            headers["Authorization"] = f"Bearer {model.api_key}"
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
        return str(data["choices"][0]["message"]["content"])

    def _anthropic(
        self,
        model: ModelRecord,
        *,
        system: str,
        user: str,
        temperature: float,
        timeout: float,
    ) -> str:
        if not model.api_key:
            raise ValueError("Anthropic model requires an API key")
        base = (model.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": model.api_key,
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
        return "".join(texts)
