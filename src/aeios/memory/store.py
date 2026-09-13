from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_OWNER = "local"
_VERSION = 2


class MemoryStore:
    """Local memory: in-process dict + optional JSON persistence.

    Keys are partitioned by ``owner_id`` (Clerk JWT ``sub``, or ``"local"``
    for CLI / auth-off). Legacy flat ``memory.json`` files migrate into the
    ``local`` bag on load.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._owners: dict[str, dict[str, Any]] = {}
        self._data_dir = data_dir
        self._path = (data_dir / "memory.json") if data_dir else None
        if self._path and self._path.exists():
            self._owners = self._load(self._path)

    def get(
        self, key: str, default: Any = None, *, owner_id: str = _DEFAULT_OWNER
    ) -> Any:
        return self._bag(owner_id).get(key, default)

    def set(
        self, key: str, value: Any, *, owner_id: str = _DEFAULT_OWNER
    ) -> None:
        self._bag(owner_id)[key] = value
        self._persist()

    def keys(self, *, owner_id: str = _DEFAULT_OWNER) -> list[str]:
        return sorted(self._bag(owner_id).keys())

    def is_shared(self) -> bool:
        """False — memory is partitioned by owner_id."""
        return False

    def append_history(
        self, entry: dict[str, Any], *, owner_id: str = _DEFAULT_OWNER
    ) -> None:
        bag = self._bag(owner_id)
        history = bag.setdefault("task_history", [])
        if not isinstance(history, list):
            history = []
            bag["task_history"] = history
        history.append(entry)
        self._persist()

    def _bag(self, owner_id: str) -> dict[str, Any]:
        oid = owner_id or _DEFAULT_OWNER
        if oid not in self._owners:
            self._owners[oid] = {}
        return self._owners[oid]

    def _persist(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _VERSION, "owners": self._owners}
        self._path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )

    @staticmethod
    def _load(path: Path) -> dict[str, dict[str, Any]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        owners = raw.get("owners")
        if raw.get("version") == _VERSION and isinstance(owners, dict):
            return {
                str(oid): (bag if isinstance(bag, dict) else {})
                for oid, bag in owners.items()
            }
        # Legacy flat dict → local bag
        return {_DEFAULT_OWNER: raw}
