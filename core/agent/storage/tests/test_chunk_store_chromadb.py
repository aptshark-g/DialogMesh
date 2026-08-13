# -*- coding: utf-8 -*-
"""ChromaDB optional backend — offline-safe wiring tests (G10).

Coverage:
  - backend="chromadb" uses PersistentClient (no default model download)
  - explicit embeddings path (BGE or local char-hash) — zero network
  - cold reopen: search rebuilds Atoms from chromadb docs/metadatas
  - ChromaBridge (event/pluggable) offline add/search
  - ChromaStore (learning) lazy-init available fix
"""
from __future__ import annotations

import os

import pytest

chromadb = pytest.importorskip("chromadb")

from core.agent.storage.chunk_store import ChunkStore  # noqa: E402


def _make_store(tmp_path, backend="chromadb"):
    return ChunkStore(
        backend=backend,
        persist_dir=str(tmp_path / "chroma"),
    )


def test_chromadb_backend_no_bge_local_embed(tmp_path):
    """No BGE → local char-hash embedder, still works offline."""
    store = _make_store(tmp_path)
    try:
        store.add_text("AES key rotation policy for gateway", block_id="b1")
        store.add_text("nginx upstream timeout tuning", block_id="b2")
        store.add_text("deepseek gateway route config", block_id="b3")

        assert store.stats()["backend"] == "chromadb"
        hits = store.search("gateway route configuration", top_k=2)
        assert len(hits) > 0
        assert all(h.block_id in {"b1", "b2", "b3"} for h in hits)
    finally:
        store.close()


def test_chromadb_backend_metadata_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    try:
        store.add_text("causal substrate DAG expansion", block_id="c1")
        hits = store.search("causal DAG", top_k=1)
        assert hits
        assert hits[0].block_id == "c1"
        assert hits[0].text == "causal substrate DAG expansion"
    finally:
        store.close()


def test_chromadb_persistent_cold_reopen(tmp_path):
    """PersistentClient + reopen: search rebuilds atoms without in-memory."""
    store = _make_store(tmp_path)
    try:
        store.add_text("PostgreSQL transaction ACID semantics", block_id="p1")
        store.add_text("redis cache invalidation strategy", block_id="p2")

        store2 = _make_store(tmp_path)  # cold reopen — no in-memory atoms
        try:
            assert store2.stats()["total_atoms"] == 0
            hits = store2.search("transaction ACID", top_k=2)
            assert hits
            assert hits[0].block_id == "p1"
        finally:
            store2.close()
    finally:
        store.close()


def test_chromadb_add_via_atom_with_embedding(tmp_path):
    from core.agent.storage.chunk_store import Atom
    store = _make_store(tmp_path)
    try:
        atom = Atom(text="JWT stateless auth", block_id="j1",
                    embedding=[0.1] * 64)
        store.add([atom])
        hits = store.search("JWT auth", top_k=1)
        assert hits
        assert hits[0].block_id == "j1"
    finally:
        store.close()


def test_chroma_bridge_offline(tmp_path):
    """ChromaBridge (event/pluggable): offline add/search with local embed."""
    from core.agent.event.pluggable import ChromaBridge
    cb = ChromaBridge(persist_dir=str(tmp_path / "bridge"))
    assert cb.available
    assert cb.add("obj_1", "JWT认证是一种无状态的身份验证方案")
    assert cb.add("obj_2", "OAuth2授权框架支持第三方登录")
    results = cb.search("认证", limit=2)
    assert len(results) > 0
    assert any("JWT" in str(r) for r in results)
    assert cb.count() >= 2
    cb.close()


def test_chroma_store_lazy_init_available(tmp_path):
    """ChromaStore (learning): available now triggers lazy init."""
    from core.agent.learning.chroma_store import ChromaStore
    cs = ChromaStore(persist_dir=str(tmp_path / "learn"))
    try:
        assert cs.available
        cs.add("d1", "PostgreSQL使用事务保证ACID", [0.1] * 768, {"k": "v"})
        q = cs.query("事务", n_results=1)
        assert [i["doc_id"] for i in q] == ["d1"]
    finally:
        cs.close()
    # reopen persistence
    cs2 = ChromaStore(persist_dir=str(tmp_path / "learn"))
    try:
        assert cs2.available
        assert cs2.count() == 1
        q2 = cs2.query("事务", n_results=1)
        assert [i["doc_id"] for i in q2] == ["d1"]
    finally:
        cs2.close()
