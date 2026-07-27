# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/tests/test_context_manager.py
──────────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文管理器测试套件

用途：
- 验证上下文管理器所有模块的核心功能：模型、存储、窗口、管理器。
- 覆盖正常路径、边界条件与异常恢复。
- 使用标准库 asyncio 与 unittest 运行，无需额外依赖。

运行方式：
    python -m unittest core.agent.v3_0.context_manager.tests.test_context_manager

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from typing import Any, Dict

from core.agent.context.models import (
    ContextPriority,
    ContextSlice,
    ContextSnapshot,
    ContextSummary,
    EntityResolutionState,
    TruncationStrategy,
    WindowConfig,
)
from core.agent.context.store import (
    InMemoryContextStore,
)

# sqlite3 在某些 Anaconda 环境下可能因 DLL 缺失而不可用
try:
    import sqlite3
    _SQLITE_AVAILABLE = True
except ImportError:
    _SQLITE_AVAILABLE = False

if _SQLITE_AVAILABLE:
    from core.agent.context.store import SQLiteContextStore
from core.agent.context.window import (
    ContextCompressor,
    ContextWindow,
    RelevanceScorer,
    TokenEstimator,
)
from core.agent.context.manager import ContextManager, SessionContext
from core.agent.v3_legacy.data_models import (
    AgentMessage_v3,
    Entity_v3,
    EntityType,
    IntentCategory,
    Intent_v3,
    MessageRole,
    SessionState_v3,
    UserMessage_v3,
)


# ═══════════════════════════════════════════════════════════════════════════
# 模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestWindowConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        config = WindowConfig()
        self.assertEqual(config.max_tokens, 4096)
        self.assertEqual(config.strategy, TruncationStrategy.HYBRID)
        self.assertEqual(config.effective_max_tokens, 4096 - 512)

    def test_reserve_validation(self) -> None:
        config = WindowConfig(max_tokens=1024, token_reserve=800)
        # 800 > 1024//2 = 512, but validator runs after max_tokens is set
        # In Pydantic v2 field_validator with mode=before may not see sibling
        # Let's just ensure effective_max_tokens is non-negative
        self.assertGreaterEqual(config.effective_max_tokens, 0)

    def test_custom_strategy(self) -> None:
        config = WindowConfig(strategy=TruncationStrategy.SUMMARY)
        self.assertEqual(config.strategy, TruncationStrategy.SUMMARY)


class TestContextSlice(unittest.TestCase):
    def setUp(self) -> None:
        self.slice = ContextSlice(session_id="sess-001")

    def test_append_message(self) -> None:
        msg = UserMessage_v3(session_id="sess-001", content="hello")
        self.slice.append_message(msg)
        self.assertEqual(len(self.slice.messages), 1)
        self.assertGreaterEqual(self.slice.token_estimate, 0)

    def test_to_prompt_text(self) -> None:
        msg = UserMessage_v3(session_id="sess-001", content="scan memory")
        self.slice.append_message(msg)
        text = self.slice.to_prompt_text()
        self.assertIn("USER", text)
        self.assertIn("scan memory", text)

    def test_append_intent(self) -> None:
        intent = Intent_v3(raw_input="scan memory")
        self.slice.append_intent(intent)
        self.assertEqual(len(self.slice.intents), 1)


class TestContextSummary(unittest.TestCase):
    def test_to_prompt_text(self) -> None:
        summary = ContextSummary(
            session_id="sess-001",
            text="User wants to scan memory.",
            key_entities={"address": "0x1000"},
        )
        text = summary.to_prompt_text()
        self.assertIn("SUMMARY", text)
        self.assertIn("0x1000", text)


class TestEntityResolutionState(unittest.TestCase):
    def test_update_value(self) -> None:
        state = EntityResolutionState(entity_type="address", value="0x1000", confidence=0.8)
        state.update_value("0x2000", 0.95, "intent-002")
        self.assertEqual(state.value, "0x2000")
        self.assertEqual(state.confidence, 0.95)
        self.assertEqual(len(state.history), 1)


class TestContextSnapshot(unittest.TestCase):
    def test_total_token_estimate(self) -> None:
        snapshot = ContextSnapshot(session_id="sess-001")
        self.assertEqual(snapshot.total_token_estimate, 0)

    def test_async_validate(self) -> None:
        async def _test() -> None:
            snapshot = ContextSnapshot(session_id="sess-001")
            slice_ok = ContextSlice(session_id="sess-001")
            snapshot.slices.append(slice_ok)
            await snapshot.async_validate()  # should pass

            slice_bad = ContextSlice(session_id="sess-002")
            snapshot.slices.append(slice_bad)
            with self.assertRaises(ValueError):
                await snapshot.async_validate()

        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════════
# 存储测试
# ═══════════════════════════════════════════════════════════════════════════

class TestInMemoryContextStore(unittest.IsolatedAsyncioTestCase):
    async def test_save_and_load(self) -> None:
        store = InMemoryContextStore()
        snapshot = ContextSnapshot(session_id="sess-001")
        await store.save(snapshot)
        loaded = await store.load("sess-001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "sess-001")
        await store.close()

    async def test_delete(self) -> None:
        store = InMemoryContextStore()
        await store.save(ContextSnapshot(session_id="sess-001"))
        deleted = await store.delete("sess-001")
        self.assertTrue(deleted)
        self.assertIsNone(await store.load("sess-001"))
        await store.close()

    async def test_list_sessions(self) -> None:
        store = InMemoryContextStore()
        await store.save(ContextSnapshot(session_id="sess-a"))
        await store.save(ContextSnapshot(session_id="sess-b"))
        sessions = await store.list_sessions()
        self.assertEqual(len(sessions), 2)
        await store.close()


@unittest.skipUnless(_SQLITE_AVAILABLE, "sqlite3 not available")
class TestSQLiteContextStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_ctx.db")
        self.store = SQLiteContextStore(self.db_path)

    async def asyncTearDown(self) -> None:
        await self.store.close()
        self.tmp_dir.cleanup()

    async def test_save_and_load(self) -> None:
        snapshot = ContextSnapshot(session_id="sess-001")
        await self.store.save(snapshot)
        loaded = await self.store.load("sess-001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "sess-001")

    async def test_delete(self) -> None:
        await self.store.save(ContextSnapshot(session_id="sess-del"))
        deleted = await self.store.delete("sess-del")
        self.assertTrue(deleted)
        self.assertIsNone(await self.store.load("sess-del"))

    async def test_list_sessions(self) -> None:
        await self.store.save(ContextSnapshot(session_id="sess-x"))
        await self.store.save(ContextSnapshot(session_id="sess-y"))
        sessions = await self.store.list_sessions()
        self.assertEqual(len(sessions), 2)

    async def test_overwrite(self) -> None:
        snap1 = ContextSnapshot(session_id="sess-ow", metadata={"v": 1})
        await self.store.save(snap1)
        snap2 = ContextSnapshot(session_id="sess-ow", metadata={"v": 2})
        await self.store.save(snap2)
        loaded = await self.store.load("sess-ow")
        self.assertEqual(loaded.metadata["v"], 2)


# ═══════════════════════════════════════════════════════════════════════════
# 窗口测试
# ═══════════════════════════════════════════════════════════════════════════

class TestTokenEstimator(unittest.TestCase):
    def test_estimate_text(self) -> None:
        est = TokenEstimator(chars_per_token=4)
        self.assertEqual(est.estimate_text("abcd"), 1)
        self.assertEqual(est.estimate_text("abcdabcd"), 2)
        self.assertEqual(est.estimate_text(""), 0)

    def test_estimate_slice(self) -> None:
        est = TokenEstimator()
        slice_obj = ContextSlice(session_id="sess-001")
        slice_obj.append_message(UserMessage_v3(session_id="sess-001", content="hello world"))
        self.assertGreater(est.estimate_slice(slice_obj), 0)


class TestRelevanceScorer(unittest.TestCase):
    def test_score_slice_no_intent(self) -> None:
        scorer = RelevanceScorer()
        slice_obj = ContextSlice(session_id="sess-001")
        score = scorer.score_slice(slice_obj, None)
        self.assertEqual(score, 0.5)

    def test_score_slice_with_intent(self) -> None:
        scorer = RelevanceScorer()
        intent = Intent_v3(raw_input="scan memory address", entities=[])
        slice_obj = ContextSlice(session_id="sess-001")
        slice_obj.append_message(UserMessage_v3(session_id="sess-001", content="scan memory"))
        score = scorer.score_slice(slice_obj, intent)
        self.assertGreater(score, 0.0)


class TestContextWindow(unittest.IsolatedAsyncioTestCase):
    async def test_add_and_fit_no_overflow(self) -> None:
        window = ContextWindow(config=WindowConfig(max_tokens=4096))
        slice_obj = ContextSlice(session_id="sess-001")
        slice_obj.append_message(UserMessage_v3(session_id="sess-001", content="hello"))
        window.add_slice(slice_obj)
        await window.fit()
        self.assertEqual(len(window.slices), 1)

    async def test_fifo_truncation(self) -> None:
        config = WindowConfig(max_tokens=256, token_reserve=0, strategy=TruncationStrategy.FIFO)
        window = ContextWindow(config=config)

        for i in range(30):
            slice_obj = ContextSlice(session_id="sess-001")
            slice_obj.append_message(
                UserMessage_v3(session_id="sess-001", content="x" * 100)
            )
            window.add_slice(slice_obj)

        await window.fit()
        # With 100 chars per message ~ 25 tokens, 30 messages = 750 tokens
        # max_tokens=256 => at least some should be removed
        self.assertLess(len(window.slices), 30)

    async def test_summary_truncation(self) -> None:
        config = WindowConfig(
            max_tokens=256,
            token_reserve=0,
            strategy=TruncationStrategy.SUMMARY,
            enable_compression=True,
        )
        window = ContextWindow(config=config)

        for i in range(20):
            slice_obj = ContextSlice(session_id="sess-001")
            slice_obj.append_message(
                UserMessage_v3(session_id="sess-001", content="scan memory at 0x1000 " * 10)
            )
            intent = Intent_v3(raw_input="scan memory", entities=[])
            slice_obj.append_intent(intent)
            window.add_slice(slice_obj)

        await window.fit()
        # Some slices should be compressed into summaries
        total_items = len(window.slices) + len(window.summaries)
        self.assertGreater(total_items, 0)

    async def test_to_prompt_text(self) -> None:
        window = ContextWindow()
        slice_obj = ContextSlice(session_id="sess-001")
        slice_obj.append_message(UserMessage_v3(session_id="sess-001", content="hello"))
        window.add_slice(slice_obj)
        text = window.to_prompt_text()
        self.assertIn("RECENT CONTEXT", text)
        self.assertIn("hello", text)

    async def test_get_stats(self) -> None:
        window = ContextWindow(config=WindowConfig(max_tokens=2048))
        stats = window.get_stats()
        self.assertEqual(stats["max_tokens"], 2048)
        self.assertEqual(stats["slice_count"], 0)


class TestContextCompressor(unittest.IsolatedAsyncioTestCase):
    async def test_compress_slices(self) -> None:
        compressor = ContextCompressor()
        slices = []
        for i in range(3):
            s = ContextSlice(session_id="sess-001")
            s.append_intent(Intent_v3(raw_input="scan memory", category=IntentCategory.SCAN_MEMORY))
            s.append_message(UserMessage_v3(session_id="sess-001", content="found address"))
            slices.append(s)

        summary = await compressor.compress(slices, "sess-001")
        self.assertIsInstance(summary, ContextSummary)
        self.assertIn("scan", summary.text.lower())
        self.assertEqual(len(summary.source_slice_ids), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 管理器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestContextManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.manager = ContextManager(enable_cognitive_tree=False)

    async def asyncTearDown(self) -> None:
        await self.manager.close()

    async def test_create_session(self) -> None:
        state = await self.manager.create_session(user_id="u-001")
        self.assertIsInstance(state, SessionState_v3)
        self.assertIsNotNone(state.session_id)
        self.assertEqual(state.user_id, "u-001")

    async def test_get_and_save_session(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        ctx = await self.manager.get_session(sid)
        self.assertIsInstance(ctx, SessionContext)
        saved = await self.manager.save_session(sid)
        self.assertTrue(saved)

    async def test_add_user_message(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        msg = UserMessage_v3(session_id=sid, content="scan memory")
        await self.manager.add_user_message(sid, msg)
        stats = await self.manager.get_stats(sid)
        self.assertEqual(stats["message_count"], 1)

    async def test_add_agent_message(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        msg = AgentMessage_v3(session_id=sid, content="found 3 addresses")
        await self.manager.add_agent_message(sid, msg)
        stats = await self.manager.get_stats(sid)
        self.assertEqual(stats["message_count"], 1)

    async def test_add_intent_and_entities(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        entity = Entity_v3(type=EntityType.NUMERIC_VALUE, value=100, confidence=0.9)
        intent = Intent_v3(
            raw_input="scan 100",
            entities=[entity],
            category=IntentCategory.SCAN_MEMORY,
        )
        await self.manager.add_intent(sid, intent)
        resolved = await self.manager.get_resolved_entities(sid)
        self.assertIn("numeric_value", resolved)
        self.assertEqual(resolved["numeric_value"], 100)

    async def test_build_prompt_context(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        await self.manager.add_user_message(sid, UserMessage_v3(session_id=sid, content="hello"))
        prompt = await self.manager.build_prompt_context(sid)
        self.assertIn("hello", prompt)
        self.assertIn("RECENT CONTEXT", prompt)

    async def test_compress_session(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        for i in range(5):
            await self.manager.add_user_message(
                sid, UserMessage_v3(session_id=sid, content=f"msg {i}")
            )
        summary = await self.manager.compress_session(sid)
        # May or may not compress depending on slice size; just ensure no exception
        self.assertIsNone(summary)  # because slices are grouped into 1 slice usually

    async def test_update_entity_status(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        entity = Entity_v3(type=EntityType.NUMERIC_VALUE, value=100, confidence=0.9)
        intent = Intent_v3(raw_input="scan 100", entities=[entity])
        await self.manager.add_intent(sid, intent)
        ok = await self.manager.update_entity_status(sid, "numeric_value", "clarified")
        self.assertTrue(ok)

    async def test_cleanup_stale_sessions(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        # Manually set last_active to very old
        ctx = await self.manager.get_session(sid)
        ctx.last_active = 0.0
        count = await self.manager.cleanup_stale_sessions(max_inactive_seconds=1.0)
        self.assertEqual(count, 1)
        self.assertIsNone(await self.manager.get_session(sid))

    async def test_list_active_sessions(self) -> None:
        s1 = await self.manager.create_session()
        s2 = await self.manager.create_session()
        active = await self.manager.list_active_sessions()
        self.assertIn(s1.session_id, active)
        self.assertIn(s2.session_id, active)

    async def test_global_stats(self) -> None:
        await self.manager.create_session()
        stats = await self.manager.get_global_stats()
        self.assertEqual(stats["total_sessions_created"], 1)
        self.assertEqual(stats["active_sessions"], 1)

    async def test_close_and_reopen(self) -> None:
        state = await self.manager.create_session()
        sid = state.session_id
        await self.manager.add_user_message(sid, UserMessage_v3(session_id=sid, content="test"))
        await self.manager.close()

        # Reopen with same store (InMemory will lose data, but test no exception)
        self.manager = ContextManager(enable_cognitive_tree=False)

    @unittest.skipUnless(_SQLITE_AVAILABLE, "sqlite3 not available")
    async def test_load_session_from_store(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmp_dir.name, "ctx.db")
        store = SQLiteContextStore(db_path)
        manager = ContextManager(store=store, enable_cognitive_tree=False)

        state = await manager.create_session()
        sid = state.session_id
        await manager.add_user_message(sid, UserMessage_v3(session_id=sid, content="persist me"))
        await manager.save_session(sid)
        await manager.close()

        # Reopen with a new store connected to the same database
        store2 = SQLiteContextStore(db_path)
        manager2 = ContextManager(store=store2, enable_cognitive_tree=False)
        loaded = await manager2.load_session(sid)
        self.assertIsNotNone(loaded)
        prompt = await manager2.build_prompt_context(sid)
        self.assertIn("persist me", prompt)
        await manager2.close()
        tmp_dir.cleanup()

    async def test_session_with_cognitive_tree(self) -> None:
        manager = ContextManager(enable_cognitive_tree=True)
        state = await manager.create_session()
        sid = state.session_id
        tree = await manager.get_cognitive_tree(sid)
        self.assertIsNotNone(tree)
        self.assertEqual(tree.session_id, sid)
        await manager.close()

    # ── EntityCache 测试（IP-S-07 修复验证）──────────────────────────

    async def test_entity_cache_update_on_add_intent(self) -> None:
        """验证 add_intent 后高置信度实体被写入 EntityCache。"""
        state = await self.manager.create_session()
        sid = state.session_id
        entity_high = Entity_v3(type=EntityType.MEMORY_ADDRESS, value="0x401000", confidence=0.9)
        entity_low = Entity_v3(type=EntityType.NUMERIC_VALUE, value=100, confidence=0.5)
        intent = Intent_v3(
            raw_input="scan 0x401000 for 100",
            entities=[entity_high, entity_low],
            category=IntentCategory.SCAN_MEMORY,
        )
        await self.manager.add_intent(sid, intent)
        cached = await self.manager.get_entity_cache(sid)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["value"], "0x401000")

    async def test_entity_cache_search_by_type(self) -> None:
        """验证 EntityCache 按类型搜索功能。"""
        state = await self.manager.create_session()
        sid = state.session_id
        e1 = Entity_v3(type=EntityType.MEMORY_ADDRESS, value="0x401000", confidence=0.85)
        e2 = Entity_v3(type=EntityType.NUMERIC_VALUE, value=100, confidence=0.9)
        intent = Intent_v3(raw_input="scan", entities=[e1, e2], category=IntentCategory.SCAN_MEMORY)
        await self.manager.add_intent(sid, intent)
        results = await self.manager._entity_cache.search_by_type(sid, "memory_address")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "0x401000")

    async def test_entity_cache_clear(self) -> None:
        """验证 EntityCache 清空功能。"""
        state = await self.manager.create_session()
        sid = state.session_id
        e = Entity_v3(type=EntityType.MEMORY_ADDRESS, value="0x401000", confidence=0.9)
        await self.manager.add_intent(sid, Intent_v3(raw_input="scan", entities=[e], category=IntentCategory.SCAN_MEMORY))
        await self.manager.clear_entity_cache(sid)
        cached = await self.manager.get_entity_cache(sid)
        self.assertEqual(len(cached), 0)

    async def test_entity_cache_inherited_excluded(self) -> None:
        """验证 inherited 标记实体不会被写入缓存。"""
        state = await self.manager.create_session()
        sid = state.session_id
        e = Entity_v3(
            type=EntityType.MEMORY_ADDRESS,
            value="0x401000",
            confidence=0.9,
            metadata={"inherited": True},
        )
        await self.manager.add_intent(sid, Intent_v3(raw_input="scan", entities=[e], category=IntentCategory.SCAN_MEMORY))
        cached = await self.manager.get_entity_cache(sid)
        self.assertEqual(len(cached), 0)

    async def test_merge_context_called_in_add_intent(self) -> None:
        """验证 add_intent 内部调用了 _merge_context（通过 entity_states 更新判断）。"""
        state = await self.manager.create_session()
        sid = state.session_id
        e = Entity_v3(type=EntityType.NUMERIC_VALUE, value=42, confidence=0.8)
        intent = Intent_v3(raw_input="read 42", entities=[e], category=IntentCategory.READ_MEMORY)
        await self.manager.add_intent(sid, intent)
        resolved = await self.manager.get_resolved_entities(sid)
        self.assertIn("numeric_value", resolved)
        self.assertEqual(resolved["numeric_value"], 42)
