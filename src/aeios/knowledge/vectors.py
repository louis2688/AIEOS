"""Optional Qdrant vector index for knowledge/memory search.

Uses a deterministic local hash embedder (no external embedding API).
Soft-fails when qdrant-client is missing or Qdrant is unreachable —
callers should keep lexical search as the primary path.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any


VECTOR_DIM = 384


def hash_embed(text: str, dim: int = VECTOR_DIM) -> list[float]:
    """Deterministic bag-of-tokens hash embedding (MVP; not semantic)."""
    vec = [0.0] * dim
    tokens = [t for t in re.split(r"\W+", (text or "").lower()) if t]
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@dataclass
class VectorHit:
    kind: str
    id: str
    title: str
    snippet: str
    score: float
    href: str | None = None
    meta: dict[str, Any] | None = None


class QdrantKnowledgeIndex:
    """Thin Qdrant wrapper. All public methods soft-fail (return False / [])."""

    def __init__(
        self,
        url: str,
        *,
        collection: str = "aeios_knowledge",
        dim: int = VECTOR_DIM,
    ) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.dim = dim
        self._client: Any = None
        self._available: bool | None = None
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._connect()
        return self._available

    def _connect(self) -> bool:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm
        except ImportError:
            self._last_error = "qdrant-client not installed (pip install 'aeios[vector]')"
            return False

        try:
            client = QdrantClient(url=self.url, timeout=2.0)
            # Probe
            client.get_collections()
            names = {c.name for c in client.get_collections().collections}
            if self.collection not in names:
                client.create_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(
                        size=self.dim,
                        distance=qm.Distance.COSINE,
                    ),
                )
            self._client = client
            self._last_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{exc.__class__.__name__}: {exc}"
            self._client = None
            return False

    def upsert_document(
        self,
        *,
        point_id: str,
        kind: str,
        title: str,
        text: str,
        href: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        if not self.available or self._client is None:
            return False
        try:
            from qdrant_client.http import models as qm

            payload = {
                "kind": kind,
                "id": point_id,
                "title": title,
                "text": text[:4000],
                "href": href,
                "meta": meta or {},
            }
            # Stable UUID-ish id from kind+id
            uid = _point_uuid(f"{kind}:{point_id}")
            self._client.upsert(
                collection_name=self.collection,
                points=[
                    qm.PointStruct(
                        id=uid,
                        vector=hash_embed(f"{title}\n{text}", self.dim),
                        payload=payload,
                    )
                ],
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{exc.__class__.__name__}: {exc}"
            self._available = False
            return False

    def search(self, query: str, *, limit: int = 20) -> list[VectorHit]:
        if not query.strip() or not self.available or self._client is None:
            return []
        try:
            results = self._client.search(
                collection_name=self.collection,
                query_vector=hash_embed(query, self.dim),
                limit=limit,
                with_payload=True,
            )
            hits: list[VectorHit] = []
            for r in results:
                payload = r.payload or {}
                hits.append(
                    VectorHit(
                        kind=str(payload.get("kind") or "memory"),
                        id=str(payload.get("id") or ""),
                        title=str(payload.get("title") or payload.get("id") or ""),
                        snippet=str(payload.get("text") or "")[:160],
                        score=float(r.score or 0.0),
                        href=payload.get("href"),
                        meta=payload.get("meta") or {},
                    )
                )
            return hits
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{exc.__class__.__name__}: {exc}"
            self._available = False
            return []

    def status(self) -> dict[str, Any]:
        ok = self.available
        return {
            "ok": ok,
            "url": self.url,
            "collection": self.collection,
            "detail": "ready" if ok else (self._last_error or "unavailable"),
        }


def _point_uuid(key: str) -> str:
    """Deterministic UUID string for Qdrant point ids."""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-"
        f"{digest[16:20]}-{digest[20:32]}"
    )


def try_open_qdrant(
    url: str | None,
    *,
    collection: str = "aeios_knowledge",
    enabled: bool = True,
) -> QdrantKnowledgeIndex | None:
    """Return an index when enabled and URL set; connection is lazy/soft."""
    if not enabled or not (url or "").strip():
        return None
    return QdrantKnowledgeIndex(url.strip(), collection=collection)
