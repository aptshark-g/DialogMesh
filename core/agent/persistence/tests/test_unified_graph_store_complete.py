# -*- coding: utf-8 -*-
"""G10-P3: UnifiedGraphStore 半实现补齐 — snapshot/maintenance/query/stats."""
from __future__ import annotations

import tempfile
import os

import pytest

from core.agent.persistence.unified_graph_store import (
    UnifiedGraphStore, SnapshotRecord,
)


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = UnifiedGraphStore(db_path=path)
    yield s
    s.close()
    os.unlink(path)


def test_open_is_open_stats(store):
    assert store.is_open is True
    store.open()  # idempotent
    assert store.is_open is True
    stats = store.stats
    assert stats["node_count"] == 0
    assert stats["edge_count"] == 0
    assert "tiers" in stats
    assert store.get_tier_counts() == {}


def test_query_nodes_filters(store):
    store.save_node("n1", "behavior_step", "B", {"action": "run"},
                    tier="H", importance=0.9)
    store.save_node("n2", "profile_dim", "P", {"name": "openness"},
                    tier="C", importance=0.5)
    store.save_node("n3", "behavior_step", "B", {"action": "stop"},
                    tier="W", importance=0.3)

    by_tier = store.query_nodes(tier="W")
    assert [n["node_id"] for n in by_tier] == ["n3"]

    by_type = store.query_nodes(node_type="behavior_step")
    assert len(by_type) == 2

    by_domain = store.query_nodes(domain="P")
    assert len(by_domain) == 1

    all_nodes = store.query_nodes(limit=100)
    assert len(all_nodes) == 3


def test_snapshot_roundtrip(store):
    store.save_node("n1", "test", "T", {"x": 1})
    store.save_node("n2", "test", "T", {"x": 2})
    record = store.create_snapshot({"reason": "test"})
    assert isinstance(record, SnapshotRecord)
    assert record.snapshot_id
    assert record.node_count == 2
    assert record.edge_count == 0

    snaps = store.get_snapshots(limit=10)
    assert len(snaps) == 1
    assert snaps[0].node_count == 2
    assert snaps[0].metadata.get("reason") == "test"

    assert store.delete_snapshot(record.snapshot_id) is True
    assert store.get_snapshots(limit=10) == []


def test_snapshot_manager_contract(store):
    """CLI/SnapshotManager 契约: create_snapshot + get_snapshots + is_open."""
    from core.agent.persistence.snapshot import SnapshotManager
    store.save_node("a", "test", "T", {})
    mgr = SnapshotManager(store, interval_sec=3600, max_snapshots=3, auto_prune=False)
    rec = mgr.snapshot_now(metadata={"k": "v"})
    assert mgr.snapshot_count == 1
    latest = mgr.get_latest()
    assert latest is not None and latest.snapshot_id == rec.snapshot_id
    assert mgr.restore_from_snapshot(rec.snapshot_id) is True
    assert mgr.restore_from_snapshot("missing") is False


def test_run_maintenance_migrates_tiers(store):
    for i in range(20):
        store.save_node(f"h{i}", "test", "T", {}, tier="H", importance=0.1)
    result = store.run_maintenance()
    assert isinstance(result, dict)
    # 20 hot nodes < HOT_MAX_NODES(999) → 不触发 H->W；W/C 空 → 0
    assert result["H->W"] == 0
    assert result["W->C"] == 0
    assert result["C->A"] == 0

    # warm > 100 → 触发 W->C
    for i in range(120):
        store.save_node(f"w{i}", "test", "T", {}, tier="W", importance=0.2)
    result = store.run_maintenance()
    assert result["W->C"] > 0
    counts = store.get_tier_counts()
    assert counts.get("C", 0) > 0
