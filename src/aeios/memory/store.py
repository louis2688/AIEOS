from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryStore:
    """Phase 0 local memory: in-process dict + optional JSON persistence.

    Keys are process-global (not per-owner). Knowledge search must exclude
    shared memory for signed-in tenants; see KnowledgeSearch._search_memory.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data: dict[str, Any] = {}
        self._data_dir = data_dir
        self._path = (data_dir / "memory.json") if data_dir else None
        if self._path and self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._persist()

    def keys(self) -> list[str]:
        return sorted(self._data.keys())

    def is_shared(self) -> bool:
        """True — this store has no owner partitioning (Phase 0)."""
        return True

    def append_history(self, entry: dict[str, Any]) -> None:
        history = self._data.setdefault("task_history", [])
        if not isinstance(history, list):
            history = []
            self._data["task_history"] = history
        history.append(entry)
        self._persist()

    def _persist(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
