from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from aeios.core.kernel import Kernel
from aeios.knowledge.vectors import QdrantKnowledgeIndex
from aeios.persistence.pipelines import PipelineStore
from aeios.persistence.projects import ProjectStore


@dataclass
class KnowledgeHit:
    kind: str
    id: str
    title: str
    snippet: str
    score: float
    href: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeSearch:
    """Unified search across tasks, pipelines, runs, projects, artifacts, memory.

    Lexical search is always used. When a Qdrant index is configured and
    reachable, memory (and optionally task) vectors are upserted lazily and
    merged into results. Qdrant failures never raise — lexical remains.

    Shared process memory is only searched for local / auth-off owners.
    """

    def __init__(
        self,
        kernel: Kernel,
        pipelines: PipelineStore,
        projects: ProjectStore,
        *,
        vector_index: QdrantKnowledgeIndex | None = None,
    ) -> None:
        self.kernel = kernel
        self.pipelines = pipelines
        self.projects = projects
        self.vector_index = vector_index

    def search(
        self,
        query: str,
        *,
        limit: int = 30,
        kinds: set[str] | None = None,
        owner_id: str | None = None,
    ) -> list[KnowledgeHit]:
        q = query.strip()
        if not q:
            return []

        allowed = kinds or {
            "task",
            "pipeline",
            "pipeline_run",
            "project",
            "memory",
            "artifact",
        }
        hits: list[KnowledgeHit] = []

        if "task" in allowed:
            hits.extend(self._search_tasks(q, owner_id=owner_id))
        if "pipeline" in allowed:
            hits.extend(self._search_pipelines(q, owner_id=owner_id))
        if "pipeline_run" in allowed:
            hits.extend(self._search_runs(q, owner_id=owner_id))
        if "project" in allowed:
            hits.extend(self._search_projects(q, owner_id=owner_id))
        if "artifact" in allowed:
            hits.extend(self._search_artifacts(q, owner_id=owner_id))
        if "memory" in allowed:
            hits.extend(self._search_memory(q, owner_id=owner_id))

        # Optional vector enrichment (soft-fail inside index)
        if self.vector_index is not None:
            hits.extend(self._vector_hits(q, allowed, owner_id=owner_id))

        hits = _dedupe_hits(hits)
        hits.sort(key=lambda h: (-h.score, h.kind, h.id))
        return hits[:limit]

    def _search_tasks(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        hits: list[KnowledgeHit] = []
        for task in self.kernel.store.list_tasks(limit=500, owner_id=owner_id):
            blob = " ".join(
                [
                    task.id,
                    task.goal or "",
                    task.agent or "",
                    task.status.value,
                    task.result or "",
                    task.error or "",
                    " ".join(task.plan or []),
                    json.dumps(task.steps or [], default=str),
                ]
            )
            score, snippet = _match(query, blob, preferred=task.goal or task.result or "")
            if score <= 0:
                continue
            hits.append(
                KnowledgeHit(
                    kind="task",
                    id=task.id,
                    title=task.goal[:120] or task.id,
                    snippet=snippet,
                    score=score + 0.1,  # slight boost — most actionable
                    href=f"/tasks/{task.id}",
                    meta={"status": task.status.value, "agent": task.agent},
                )
            )
        return hits

    def _search_pipelines(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        hits: list[KnowledgeHit] = []
        for pipeline in self.pipelines.list(limit=200, owner_id=owner_id):
            step_text = " ".join(f"{s.agent} {s.goal}" for s in pipeline.steps)
            blob = " ".join(
                [
                    pipeline.id,
                    pipeline.name,
                    pipeline.description or "",
                    pipeline.project_id or "",
                    step_text,
                ]
            )
            score, snippet = _match(query, blob, preferred=pipeline.description or pipeline.name)
            if score <= 0:
                continue
            hits.append(
                KnowledgeHit(
                    kind="pipeline",
                    id=pipeline.id,
                    title=pipeline.name,
                    snippet=snippet,
                    score=score,
                    href=f"/pipelines/{pipeline.id}",
                    meta={"steps": len(pipeline.steps)},
                )
            )
        return hits

    def _search_runs(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        hits: list[KnowledgeHit] = []
        for run in self.pipelines.list_runs(limit=300, owner_id=owner_id):
            step_blob = json.dumps(run.step_results, default=str)
            blob = " ".join(
                [
                    run.id,
                    run.pipeline_id,
                    run.input_goal or "",
                    run.status,
                    run.result or "",
                    run.error or "",
                    step_blob,
                ]
            )
            score, snippet = _match(
                query, blob, preferred=run.input_goal or run.result or ""
            )
            if score <= 0:
                continue
            hits.append(
                KnowledgeHit(
                    kind="pipeline_run",
                    id=run.id,
                    title=run.input_goal[:120] or run.id,
                    snippet=snippet,
                    score=score,
                    href=f"/pipelines/{run.pipeline_id}",
                    meta={
                        "status": run.status,
                        "pipeline_id": run.pipeline_id,
                        "steps": len(run.step_results),
                    },
                )
            )
        return hits

    def _search_projects(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        hits: list[KnowledgeHit] = []
        for project in self.projects.list(limit=200, owner_id=owner_id):
            blob = " ".join(
                [project.id, project.name, project.description or ""]
            )
            score, snippet = _match(
                query, blob, preferred=project.description or project.name
            )
            if score <= 0:
                continue
            hits.append(
                KnowledgeHit(
                    kind="project",
                    id=project.id,
                    title=project.name,
                    snippet=snippet,
                    score=score,
                    href="/projects",
                    meta={},
                )
            )
        return hits

    def _search_artifacts(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        hits: list[KnowledgeHit] = []
        artifacts = getattr(self.kernel, "artifacts", None)
        if artifacts is None:
            return hits
        for art in artifacts.list(limit=500, owner_id=owner_id):
            path = art.get("path") or ""
            content = art.get("content") or ""
            blob = " ".join(
                [
                    art.get("id") or "",
                    art.get("task_id") or "",
                    path,
                    content,
                ]
            )
            score, snippet = _match(query, blob, preferred=content[:240] or path)
            if score <= 0:
                continue
            task_id = art.get("task_id") or ""
            hits.append(
                KnowledgeHit(
                    kind="artifact",
                    id=art["id"],
                    title=path or art["id"],
                    snippet=snippet,
                    score=score,
                    href=f"/tasks/{task_id}" if task_id else None,
                    meta={
                        "path": path,
                        "task_id": task_id,
                        "bytes": art.get("bytes", 0),
                    },
                )
            )
        return hits

    def _search_memory(
        self, query: str, *, owner_id: str | None = None
    ) -> list[KnowledgeHit]:
        # Shared memory has no owner column — exclude for signed-in tenants.
        if owner_id is not None and owner_id != "local":
            return []
        hits: list[KnowledgeHit] = []
        memory = self.kernel.memory
        for key in memory.keys():
            value = memory.get(key)
            text = json.dumps(value, default=str) if not isinstance(value, str) else value
            blob = f"{key} {text}"
            score, snippet = _match(query, blob, preferred=text[:240])
            if score <= 0:
                continue
            hits.append(
                KnowledgeHit(
                    kind="memory",
                    id=key,
                    title=f"memory:{key}",
                    snippet=snippet,
                    score=score * 0.9,
                    href=None,
                    meta={"key": key},
                )
            )
        return hits

    def _vector_hits(
        self,
        query: str,
        allowed: set[str],
        *,
        owner_id: str | None = None,
    ) -> list[KnowledgeHit]:
        idx = self.vector_index
        if idx is None:
            return []
        # Lazy upsert of memory + recent tasks (best-effort)
        try:
            self._sync_vectors(allowed, owner_id=owner_id)
            raw = idx.search(query, limit=20)
        except Exception:  # noqa: BLE001
            return []
        hits: list[KnowledgeHit] = []
        for v in raw:
            if v.kind not in allowed or not v.id:
                continue
            # Drop shared-memory vector hits for signed-in tenants.
            if v.kind == "memory" and owner_id is not None and owner_id != "local":
                continue
            hits.append(
                KnowledgeHit(
                    kind=v.kind,
                    id=v.id,
                    title=v.title,
                    snippet=v.snippet,
                    score=min(float(v.score) + 0.05, 1.5),
                    href=v.href,
                    meta={**(v.meta or {}), "source": "qdrant"},
                )
            )
        return hits

    def _sync_vectors(
        self, allowed: set[str], *, owner_id: str | None = None
    ) -> None:
        idx = self.vector_index
        if idx is None or not idx.available:
            return
        allow_memory = "memory" in allowed and (
            owner_id is None or owner_id == "local"
        )
        if allow_memory:
            memory = self.kernel.memory
            for key in memory.keys():
                value = memory.get(key)
                text = (
                    json.dumps(value, default=str)
                    if not isinstance(value, str)
                    else value
                )
                idx.upsert_document(
                    point_id=key,
                    kind="memory",
                    title=f"memory:{key}",
                    text=text,
                    meta={"key": key},
                )
        if "task" in allowed:
            for task in self.kernel.store.list_tasks(limit=100, owner_id=owner_id):
                idx.upsert_document(
                    point_id=task.id,
                    kind="task",
                    title=(task.goal or task.id)[:120],
                    text=" ".join(
                        [
                            task.goal or "",
                            task.result or "",
                            task.error or "",
                            " ".join(task.plan or []),
                        ]
                    ),
                    href=f"/tasks/{task.id}",
                    meta={"status": task.status.value, "agent": task.agent},
                )
        if "artifact" in allowed:
            artifacts = getattr(self.kernel, "artifacts", None)
            if artifacts is not None:
                for art in artifacts.list(limit=100, owner_id=owner_id):
                    path = art.get("path") or ""
                    content = art.get("content") or ""
                    idx.upsert_document(
                        point_id=art["id"],
                        kind="artifact",
                        title=path or art["id"],
                        text=f"{path} {content}",
                        href=(
                            f"/tasks/{art['task_id']}"
                            if art.get("task_id")
                            else None
                        ),
                        meta={
                            "path": path,
                            "task_id": art.get("task_id"),
                        },
                    )


def _dedupe_hits(hits: list[KnowledgeHit]) -> list[KnowledgeHit]:
    best: dict[tuple[str, str], KnowledgeHit] = {}
    for h in hits:
        key = (h.kind, h.id)
        prev = best.get(key)
        if prev is None or h.score > prev.score:
            best[key] = h
    return list(best.values())


def _match(query: str, blob: str, preferred: str = "") -> tuple[float, str]:
    """Return (score, snippet). Score 0 means no match."""
    hay = blob.lower()
    terms = [t for t in re.split(r"\s+", query.lower()) if t]
    if not terms:
        return 0.0, ""

    matched = [t for t in terms if t in hay]
    if not matched:
        return 0.0, ""

    score = len(matched) / len(terms)
    # Phrase bonus
    if query.lower() in hay:
        score += 0.35

    source = preferred or blob
    snippet = _snippet(source, matched[0])
    return min(score, 1.5), snippet


def _snippet(text: str, term: str, width: int = 160) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return ""
    lower = clean.lower()
    idx = lower.find(term.lower())
    if idx < 0:
        return clean[:width] + ("…" if len(clean) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(clean), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"
