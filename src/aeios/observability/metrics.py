"""Process-wide counters for LLM usage, tools, tasks, and HTTP requests.

MVP only — not OpenTelemetry. Suitable for local dashboards and `/v1/metrics`.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any


# Rough USD per 1M tokens (placeholder; not provider-accurate billing).
_DEFAULT_COST_PER_1M = {
    "prompt": 0.50,
    "completion": 1.50,
}


@dataclass
class MetricsSnapshot:
    http_requests: int = 0
    llm_calls: int = 0
    llm_failures: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    llm_estimated_cost_usd: float = 0.0
    tool_calls: int = 0
    tool_failures: int = 0
    tasks_started: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    by_tool: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["llm_estimated_cost_usd"] = round(self.llm_estimated_cost_usd, 6)
        return data


class MetricsRegistry:
    """Thread-safe in-memory counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = MetricsSnapshot()

    def reset(self) -> None:
        with self._lock:
            self._snap = MetricsSnapshot()

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                http_requests=self._snap.http_requests,
                llm_calls=self._snap.llm_calls,
                llm_failures=self._snap.llm_failures,
                llm_prompt_tokens=self._snap.llm_prompt_tokens,
                llm_completion_tokens=self._snap.llm_completion_tokens,
                llm_total_tokens=self._snap.llm_total_tokens,
                llm_estimated_cost_usd=self._snap.llm_estimated_cost_usd,
                tool_calls=self._snap.tool_calls,
                tool_failures=self._snap.tool_failures,
                tasks_started=self._snap.tasks_started,
                tasks_completed=self._snap.tasks_completed,
                tasks_failed=self._snap.tasks_failed,
                by_provider=dict(self._snap.by_provider),
                by_tool=dict(self._snap.by_tool),
            )

    def record_http_request(self) -> None:
        with self._lock:
            self._snap.http_requests += 1

    def record_llm_call(
        self,
        *,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
        ok: bool = True,
        estimated_cost_usd: float | None = None,
    ) -> None:
        prompt = max(0, int(prompt_tokens))
        completion = max(0, int(completion_tokens))
        total = (
            max(0, int(total_tokens))
            if total_tokens is not None
            else prompt + completion
        )
        if estimated_cost_usd is None:
            estimated_cost_usd = (
                prompt * _DEFAULT_COST_PER_1M["prompt"]
                + completion * _DEFAULT_COST_PER_1M["completion"]
            ) / 1_000_000.0

        with self._lock:
            if ok:
                self._snap.llm_calls += 1
            else:
                self._snap.llm_failures += 1
            self._snap.llm_prompt_tokens += prompt
            self._snap.llm_completion_tokens += completion
            self._snap.llm_total_tokens += total
            self._snap.llm_estimated_cost_usd += float(estimated_cost_usd)
            key = provider or "unknown"
            self._snap.by_provider[key] = self._snap.by_provider.get(key, 0) + 1

    def record_tool_call(self, name: str, *, ok: bool) -> None:
        with self._lock:
            self._snap.tool_calls += 1
            if not ok:
                self._snap.tool_failures += 1
            key = name or "unknown"
            self._snap.by_tool[key] = self._snap.by_tool.get(key, 0) + 1

    def record_task_started(self) -> None:
        with self._lock:
            self._snap.tasks_started += 1

    def record_task_finished(self, *, ok: bool) -> None:
        with self._lock:
            if ok:
                self._snap.tasks_completed += 1
            else:
                self._snap.tasks_failed += 1


_METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _METRICS
