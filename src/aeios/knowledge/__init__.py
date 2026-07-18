"""Knowledge search package.

Keep this module free of imports from ``aeios.core.kernel`` so the kernel
can safely import ``aeios.knowledge.vectors`` at boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aeios.knowledge.vectors import QdrantKnowledgeIndex, hash_embed, try_open_qdrant

if TYPE_CHECKING:
    from aeios.knowledge.search import KnowledgeHit, KnowledgeSearch

__all__ = [
    "KnowledgeHit",
    "KnowledgeSearch",
    "QdrantKnowledgeIndex",
    "hash_embed",
    "try_open_qdrant",
]


def __getattr__(name: str) -> Any:
    if name in {"KnowledgeHit", "KnowledgeSearch"}:
        from aeios.knowledge.search import KnowledgeHit, KnowledgeSearch

        return {"KnowledgeHit": KnowledgeHit, "KnowledgeSearch": KnowledgeSearch}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
