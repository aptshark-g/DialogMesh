# -*- coding: utf-8 -*-
"""G10-P1: ChunkStore unified backend (UnifiedStore BGE+LSH) wiring tests."""
from __future__ import annotations

import numpy as np
import pytest

from core.agent.storage.chunk_store import Atom, ChunkStore


class _FakeBGE:
    """Deterministic char-hash embedder — stands in for BGE in tests."""

    def encode(self, texts, batch_size=32, normalize=True, use_cache=True):
        if isinstance(texts, str):
            texts = [texts]
        vecs = []
        rng = np.random.RandomState(7)
        for t in texts:
            v = np.array([(ord(c) % 17) / 17.0 for c in t[:64]], dtype=float)
            v = np.pad(v, (0, max(0, 512 - v.shape[0])))[:512]
            v = v + rng.rand(512) * 1e-6
            if normalize:
                n = np.linalg.norm(v)
                if n > 0:
                    v = v / n
            vecs.append(v)
        return np.array(vecs)


@pytest.fixture
def fake_bge():
    return _FakeBGE()


def test_unified_backend_add_search_roundtrip(fake_bge):
    store = ChunkStore(backend="unified", bge_model=fake_bge)
    store.add_text("AES key rotation policy for gateway", block_id="b1")
    store.add_text("nginx upstream timeout tuning", block_id="b2")
    store.add_text("deepseek gateway route config", block_id="b3")

    assert store.stats()["backend"] == "unified"
    assert store.stats()["unified_indexed"] == 3
    hits = store.search("gateway route configuration", top_k=2)
    assert len(hits) > 0
    assert hits[0].block_id in {"b1", "b2", "b3"}
    assert hits[0].text


def test_unified_backend_fallback_keyword_without_bge():
    """No BGE → keyword fallback still works (same interface)."""
    store = ChunkStore(backend="unified", bge_model=None)
    store.add_text("hello world gateway", block_id="b1")
    store.add_text("completely unrelated topic", block_id="b2")
    hits = store.search("gateway")
    assert len(hits) >= 1
    assert hits[0].block_id == "b1"
    assert store.stats()["unified_indexed"] == 0  # no BGE → nothing indexed


def test_unified_backend_metadata_roundtrip(fake_bge):
    store = ChunkStore(backend="unified", bge_model=fake_bge)
    store.add_text("causal substrate DAG expansion", block_id="c1")
    atom = store.add_text("profile track A fact", block_id="c2")
    assert atom is not None
    hits = store.search("causal DAG", top_k=1)
    assert hits
    assert hits[0].block_id == "c1"


def test_unified_backend_stats(fake_bge):
    store = ChunkStore(backend="unified", bge_model=fake_bge)
    assert store.stats()["backend"] == "unified"
    assert store.stats()["total_atoms"] == 0
    store.add([Atom(text="one", block_id="x1"), Atom(text="two", block_id="x2")])
    assert store.stats()["total_atoms"] == 2
    assert store.stats()["unified_indexed"] == 2
