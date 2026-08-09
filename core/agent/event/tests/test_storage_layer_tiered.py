# -*- coding: utf-8 -*-
"""G10-P2: StorageLayer 主存储路径挂载 TieredStorageManager 测试."""
from __future__ import annotations

import tempfile
import time

from core.agent.event.storage import StorageLayer
from core.agent.persistence.models import Session, TurnRecord
from core.agent.persistence.tiered_storage import TierPolicy


def _make_layer(tmp_path, policy=None):
    db = str(tmp_path / "tiered.db")
    cold = str(tmp_path / "archive")
    return StorageLayer(
        enable_tiered=True,
        tiered_db=db,
        cold_dir=cold,
        tier_policy=policy,
    )


def test_default_layer_has_no_tiered():
    layer = StorageLayer()
    try:
        assert layer.tiered is None
        assert layer.tiered_stats()["enabled"] is False
    finally:
        layer.close()


def test_tiered_enabled_layer_stats(tmp_path):
    layer = _make_layer(tmp_path)
    try:
        assert layer.tiered is not None
        stats = layer.tiered_stats()
        assert stats["enabled"] is True
        assert "hot" in stats and "warm" in stats and "cold" in stats
        # merged into storage stats
        merged = layer.stats()
        assert "tiered" in merged
    finally:
        layer.close()


def test_tiered_hot_cache_roundtrip(tmp_path):
    layer = _make_layer(tmp_path)
    try:
        session = Session(session_id="s1")
        layer.put_tiered_hot(session)
        assert layer.get_tiered_hot("s1").session_id == "s1"
    finally:
        layer.close()


def test_tiered_archive_rehydrate(tmp_path):
    policy = TierPolicy(
        hot_ttl_seconds=3600,
        warm_ttl_seconds=2,
        cold_retention_days=30,
        cold_compression=False,
        max_hot_sessions=100,
    )
    layer = _make_layer(tmp_path, policy)
    try:
        # 直接写 warm 层（绕过 hot 缓存）
        session = Session(session_id="sa")
        layer.tiered._warm.save_session(session)
        for i in range(2):
            layer.tiered._warm.save_turn(
                "sa", TurnRecord(sequence=i + 1, role="user", content=f"q{i}"))
        # 把 updated_at 拨到过去 → 触发归档
        layer.tiered._warm._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?",
            (time.time() - 10, "sa"))
        layer.tiered._warm._conn.commit()

        result = layer.archive_tiered()
        assert result["archived_sessions"] == 1
        assert result["archived_turns"] == 2

        rehydrated = layer.rehydrate_tiered("sa")
        assert rehydrated is not None
        assert rehydrated.turn_count == 2
    finally:
        layer.close()
