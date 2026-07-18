from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios.core.types import Task


def collect_task_artifacts(
    task: Task,
    workspace: Path,
    *,
    durable: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect files written/updated during a task (disk + durable DB rows)."""
    root = workspace.resolve()
    seen: dict[str, dict[str, Any]] = {}

    for row in durable or []:
        path = str(row.get("path") or "").replace("\\", "/").lstrip("./")
        if not path:
            continue
        seen[path] = {
            "path": path,
            "exists": True,
            "bytes": int(row.get("bytes") or 0),
            "content": row.get("content"),
            "source": row.get("source") or "db",
            "ephemeral_note": None,
            "id": row.get("id"),
        }

    for step in task.steps or []:
        if not isinstance(step, dict):
            continue
        paths = _paths_from_step(step)
        for rel in paths:
            disk = _read_artifact(root, rel, source="step")
            if not disk:
                continue
            existing = seen.get(rel)
            if existing and existing.get("source") == "db":
                # Prefer live disk content when present; keep DB as fallback.
                if disk.get("exists"):
                    seen[rel] = {
                        **disk,
                        "id": existing.get("id"),
                        "source": "step+db",
                    }
                continue
            if rel not in seen:
                seen[rel] = disk

    return sorted(seen.values(), key=lambda a: a["path"])


def _paths_from_step(step: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("path", "file", "filepath"):
        val = step.get(key)
        if isinstance(val, str) and val.strip():
            paths.append(val.replace("\\", "/").lstrip("./"))

    output = step.get("output")
    if isinstance(output, dict):
        p = output.get("path")
        if isinstance(p, str) and p.strip():
            paths.append(p.replace("\\", "/").lstrip("./"))
        if output.get("action") in {"write", "update"} and isinstance(
            output.get("path"), str
        ):
            paths.append(str(output["path"]).replace("\\", "/").lstrip("./"))
    elif isinstance(output, str):
        # Heuristic: "Wrote IMPLEMENTATION.md" style messages
        for token in output.replace("`", " ").split():
            if "/" in token or token.endswith(
                (".md", ".py", ".txt", ".json", ".yml", ".yaml")
            ):
                cleaned = token.strip(".,;:()[]\"'").replace("\\", "/").lstrip("./")
                if cleaned and ".." not in cleaned:
                    paths.append(cleaned)

    # Dedupe preserving order
    out: list[str] = []
    for p in paths:
        if p and p not in out:
            out.append(p)
    return out


def _read_artifact(root: Path, rel: str, *, source: str) -> dict[str, Any] | None:
    if not rel or ".." in rel.split("/"):
        return None
    try:
        target = (root / rel).resolve()
        target.relative_to(root)
    except ValueError:
        return None

    exists = target.is_file()
    content: str | None = None
    size = 0
    if exists:
        try:
            raw = target.read_bytes()
            size = len(raw)
            # Cap preview at 64 KiB for API responses
            preview = raw[: 64 * 1024]
            content = preview.decode("utf-8", errors="replace")
        except OSError:
            exists = False

    return {
        "path": rel.replace("\\", "/"),
        "exists": exists,
        "bytes": size,
        "content": content,
        "source": source,
        "ephemeral_note": (
            None
            if exists
            else "File not on disk (ephemeral workspace may have been wiped)."
        ),
    }
