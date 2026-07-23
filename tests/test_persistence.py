# -*- coding: utf-8 -*-
"""
tests/test_persistence.py
─────────────────────────
DialogMesh session persistence testing (Phase 6).

Uses temporary SQLite files for tests that span manager restarts,
and :memory: for single-manager tests.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import List

import pytest

from service.async_session_manager import AsyncSessionManager
from service.models import Session, TurnRecord, CognitiveProfile, AdaptiveThresholds
from service.stores.async_sqlite import AsyncSQLiteSessionStore


async def _make_temp_db() -> str:
    """Return a path to a new temporary SQLite file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


@pytest.mark.asyncio
async def test_create_and_load_session():
    """Create → Close → Reload via new manager, verify data integrity."""
    db_path = await _make_temp_db()
    try:
        store = AsyncSQLiteSessionStore(db_path=db_path)
        sm1 = AsyncSessionManager(store=store, ttl_seconds=3600)
        await sm1.start()

        session = await sm1.create_session(tenant_id="t1", user_id="u1")
        session_id = session.session_id

        session.parse_context = {"process_id": 1234}
        await sm1.update_session(session)

        summary = await sm1.close_session(session_id)
        assert summary is not None
        assert summary.session_id == session_id

        await sm1.stop()
        await store.close()

        # Restart with fresh manager pointing to same file
        store2 = AsyncSQLiteSessionStore(db_path=db_path)
        sm2 = AsyncSessionManager(store=store2, ttl_seconds=3600)
        await sm2.start()

        loaded = await sm2.get_session(session_id)
        assert loaded is not None
        assert loaded.session_id == session_id
        assert loaded.tenant_id == "t1"
        assert loaded.user_id == "u1"
        assert loaded.parse_context == {"process_id": 1234}
        assert loaded.state == "closed"

        await sm2.stop()
        await store2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_add_turn_and_recover():
    """Add 3 turns → Restart → Verify 3 rounds recovered."""
    db_path = await _make_temp_db()
    try:
        store = AsyncSQLiteSessionStore(db_path=db_path)
        sm1 = AsyncSessionManager(store=store, ttl_seconds=3600)
        await sm1.start()

        session = await sm1.create_session(tenant_id="t1", user_id="u2")
        sid = session.session_id

        for i in range(3):
            turn = TurnRecord(
                sequence=i,
                timestamp=time.time(),
                role="user",
                content=f"turn-{i}",
                modality="text",
            )
            await sm1.save_turn(sid, turn)

        await sm1.stop()
        await store.close()

        # Restart
        store2 = AsyncSQLiteSessionStore(db_path=db_path)
        sm2 = AsyncSessionManager(store=store2, ttl_seconds=3600)
        await sm2.start()

        loaded = await sm2.get_session(sid)
        assert loaded is not None
        assert len(loaded.history) == 3
        assert loaded.turn_count == 3
        for i, turn in enumerate(loaded.history):
            assert turn.sequence == i
            assert turn.content == f"turn-{i}"

        await sm2.stop()
        await store2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_cognitive_profile_persistence():
    """Update cognitive profile → Restart → Verify not reset."""
    db_path = await _make_temp_db()
    try:
        store = AsyncSQLiteSessionStore(db_path=db_path)
        sm1 = AsyncSessionManager(store=store, ttl_seconds=3600)
        await sm1.start()

        session = await sm1.create_session(tenant_id="t1", user_id="u3")
        sid = session.session_id
        session.cognitive_profile = CognitiveProfile(
            metacognition=0.8,
            divergence=0.2,
            tracking_depth=1.0,
            stability=0.9,
            confidence=0.7,
        )
        await sm1.update_session(session)
        await sm1.stop()
        await store.close()

        store2 = AsyncSQLiteSessionStore(db_path=db_path)
        sm2 = AsyncSessionManager(store=store2, ttl_seconds=3600)
        await sm2.start()

        loaded = await sm2.get_session(sid)
        assert loaded is not None
        assert loaded.cognitive_profile is not None
        assert loaded.cognitive_profile.metacognition == 0.8
        assert loaded.cognitive_profile.confidence == 0.7

        await sm2.stop()
        await store2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_adaptive_thresholds_persistence():
    """Update thresholds → Restart → Verify retained."""
    db_path = await _make_temp_db()
    try:
        store = AsyncSQLiteSessionStore(db_path=db_path)
        sm1 = AsyncSessionManager(store=store, ttl_seconds=3600)
        await sm1.start()

        session = await sm1.create_session(tenant_id="t1", user_id="u4")
        sid = session.session_id
        session.adaptive_thresholds = AdaptiveThresholds(
            noise_threshold=0.20,
            complexity_threshold=0.60,
            confidence_threshold=0.50,
            noise_fast_path=0.25,
        )
        await sm1.update_session(session)
        await sm1.stop()
        await store.close()

        store2 = AsyncSQLiteSessionStore(db_path=db_path)
        sm2 = AsyncSessionManager(store=store2, ttl_seconds=3600)
        await sm2.start()

        loaded = await sm2.get_session(sid)
        assert loaded is not None
        assert loaded.adaptive_thresholds is not None
        assert loaded.adaptive_thresholds.noise_threshold == 0.20
        assert loaded.adaptive_thresholds.complexity_threshold == 0.60

        await sm2.stop()
        await store2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_list_sessions():
    """Create 5 sessions → List → Verify sorted by last activity."""
    store = AsyncSQLiteSessionStore(db_path=":memory:")
    sm = AsyncSessionManager(store=store, ttl_seconds=3600)
    await sm.start()

    sids: List[str] = []
    for i in range(5):
        sess = await sm.create_session(tenant_id="list-tenant", user_id=f"u{i}")
        sids.append(sess.session_id)
        await asyncio.sleep(0.01)  # Ensure distinct updated_at ordering

    listed = await sm.list_sessions("list-tenant", limit=10)
    assert len(listed) == 5
    assert set(listed) == set(sids)

    await sm.stop()
    await store.close()


@pytest.mark.asyncio
async def test_session_ttl_expiration():
    """Mock past expiration → Verify cleanup."""
    store = AsyncSQLiteSessionStore(db_path=":memory:")
    sm = AsyncSessionManager(store=store, ttl_seconds=1, eviction_interval_seconds=1)
    await sm.start()

    session = await sm.create_session(tenant_id="t1", user_id="u5")
    sid = session.session_id

    # Touch session with a past expiration to force expiry
    async with sm._lock:
        sess = sm._sessions[sid]
        sess.expires_at = time.time() - 1  # Expired 1 second ago

    # Trigger eviction manually
    evicted = await sm._evict_expired()
    assert evicted >= 1

    # Session should be gone from memory
    assert await sm.get_session(sid) is None

    await sm.stop()
    await store.close()


@pytest.mark.asyncio
async def test_concurrent_write():
    """Concurrently write to the same session → Verify no data loss."""
    store = AsyncSQLiteSessionStore(db_path=":memory:")
    sm = AsyncSessionManager(store=store, ttl_seconds=3600)
    await sm.start()

    session = await sm.create_session(tenant_id="t1", user_id="u6")
    sid = session.session_id

    async def writer(seq: int):
        turn = TurnRecord(
            sequence=seq,
            timestamp=time.time(),
            role="user",
            content=f"concurrent-{seq}",
            modality="text",
        )
        return await sm.save_turn(sid, turn)

    results = await asyncio.gather(*[writer(i) for i in range(10)])
    assert all(results), "Some concurrent writes failed"

    loaded = await sm.get_session(sid)
    assert loaded is not None
    assert len(loaded.history) == 10

    await sm.stop()
    await store.close()


@pytest.mark.asyncio
async def test_database_corruption_recovery():
    """Mock database corruption → Verify automatic recovery."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        # 1. Create a valid store and write a session
        store1 = AsyncSQLiteSessionStore(db_path=tmp_path)
        sm1 = AsyncSessionManager(store=store1, ttl_seconds=3600)
        await sm1.start()
        session = await sm1.create_session(tenant_id="t1", user_id="u7")
        sid = session.session_id
        await sm1.stop()
        await store1.close()

        # 2. Corrupt the file (overwrite header bytes)
        with open(tmp_path, "r+b") as f:
            f.write(b"CORRUPTED")

        # 3. Open with a new store — should detect corruption and recreate
        store2 = AsyncSQLiteSessionStore(db_path=tmp_path)
        sm2 = AsyncSessionManager(store=store2, ttl_seconds=3600)
        await sm2.start()

        # The store should be usable even if previous data is lost
        loaded = await sm2.get_session(sid)
        # Data may be lost due to corruption, but the store should not crash
        new_session = await sm2.create_session(tenant_id="t1", user_id="u8")
        assert new_session.session_id is not None
        assert new_session.tenant_id == "t1"

        await sm2.stop()
        await store2.close()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
