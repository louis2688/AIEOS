"""Qdrant vector index — unit tests with mocks; live test skips if unavailable."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from aeios.knowledge.vectors import (
    VECTOR_DIM,
    QdrantKnowledgeIndex,
    hash_embed,
    try_open_qdrant,
)


def test_hash_embed_deterministic() -> None:
    a = hash_embed("neon billing module")
    b = hash_embed("neon billing module")
    c = hash_embed("something else entirely")
    assert len(a) == VECTOR_DIM
    assert a == b
    assert a != c
    # L2-ish normalized
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_try_open_qdrant_disabled() -> None:
    assert try_open_qdrant("http://localhost:6333", enabled=False) is None
    assert try_open_qdrant("", enabled=True) is None


def test_qdrant_connect_import_error() -> None:
    idx = QdrantKnowledgeIndex("http://localhost:6333")
    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == "qdrant_client" or name.startswith("qdrant_client."):
            raise ImportError("no qdrant")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        assert idx._connect() is False
    assert idx.last_error is not None
    assert "qdrant-client" in idx.last_error or "no qdrant" in idx.last_error


def test_qdrant_search_soft_fail_when_unavailable() -> None:
    idx = QdrantKnowledgeIndex("http://127.0.0.1:1")
    idx._available = False
    idx._client = None
    assert idx.search("hello") == []
    assert idx.upsert_document(
        point_id="k", kind="memory", title="t", text="hello"
    ) is False


def test_qdrant_upsert_and_search_mocked() -> None:
    pytest.importorskip("qdrant_client")

    idx = QdrantKnowledgeIndex("http://localhost:6333")
    client = MagicMock()
    collections = MagicMock()
    collections.collections = []
    client.get_collections.return_value = collections
    idx._client = client
    idx._available = True

    assert idx.upsert_document(
        point_id="mem1",
        kind="memory",
        title="memory:mem1",
        text="neon billing notes",
    )
    client.upsert.assert_called_once()

    hit = MagicMock()
    hit.score = 0.9
    hit.payload = {
        "kind": "memory",
        "id": "mem1",
        "title": "memory:mem1",
        "text": "neon billing notes",
        "href": None,
        "meta": {},
    }
    client.search.return_value = [hit]
    results = idx.search("neon billing")
    assert len(results) == 1
    assert results[0].id == "mem1"
    assert results[0].kind == "memory"


def test_live_qdrant_roundtrip() -> None:
    qdrant_client = pytest.importorskip("qdrant_client")
    url = os.environ.get("AEIOS_TEST_QDRANT_URL", "http://localhost:6333")
    try:
        c = qdrant_client.QdrantClient(url=url, timeout=1.5)
        c.get_collections()
    except Exception:  # noqa: BLE001
        pytest.skip("Qdrant not reachable")

    idx = QdrantKnowledgeIndex(url, collection="aeios_test_knowledge")
    assert idx.available
    assert idx.upsert_document(
        point_id="live1",
        kind="memory",
        title="memory:live1",
        text="vector live probe for aeios",
    )
    hits = idx.search("vector live probe", limit=5)
    assert any(h.id == "live1" for h in hits)
