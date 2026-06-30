# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_service_layer.py
──────────────────────────────────────────
服务层（Layer 2）单元测试（v2.4 新增）。

覆盖：
  - Session 数据模型序列化/反序列化
  - SessionManager（创建、获取、更新、关闭、过期清理）
  - RateLimiter（租户级、会话级、限流、释放）
  - SQLiteSessionStore（保存/加载会话、历史查询、删除）
  - AgentService（创建会话、处理消息、限流、健康检查）

不依赖 FastAPI，测试纯业务逻辑。
"""

from __future__ import annotations

import os
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.agent.service.models import Session, TurnRecord, SessionSummary
from core.agent.service.session_manager import SessionManager
from core.agent.service.rate_limiter import RateLimiter, TokenBucket
from core.agent.service.agent_service import AgentService

try:
    import sqlite3
    from core.agent.service.stores.sqlite import SQLiteSessionStore
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False
    SQLiteSessionStore = None


class TestSessionModel(unittest.TestCase):
    """验证 Session 数据模型。"""

    def test_create_session_defaults(self):
        s = Session()
        self.assertIsNotNone(s.session_id)
        self.assertEqual(s.tenant_id, "default")
        self.assertEqual(s.state, "active")
        self.assertEqual(s.turn_count, 0)
        self.assertEqual(len(s.history), 0)

    def test_session_to_dict_roundtrip(self):
        s = Session(tenant_id="test", user_id="u1", turn_count=3)
        s.history.append(TurnRecord(sequence=0, timestamp=time.time(), content="hello"))
        d = s.to_persistent_dict()
        self.assertEqual(d["tenant_id"], "test")
        self.assertEqual(d["user_id"], "u1")
        self.assertEqual(len(d["history"]), 1)

        s2 = Session.from_persistent_dict(d)
        self.assertEqual(s2.tenant_id, "test")
        self.assertEqual(s2.user_id, "u1")
        self.assertEqual(s2.turn_count, 3)
        self.assertEqual(len(s2.history), 1)
        self.assertEqual(s2.history[0].content, "hello")

    def test_session_touch(self):
        s = Session()
        old = s.last_activity_at
        time.sleep(0.01)
        s.touch()
        self.assertGreater(s.last_activity_at, old)


class TestTurnRecord(unittest.TestCase):
    """验证 TurnRecord 序列化。"""

    def test_roundtrip(self):
        t = TurnRecord(
            sequence=5, timestamp=12345.0, role="user",
            content="scan memory", intent_result={"expectation": "TOOL"},
            latency_ms=12.3,
        )
        d = t.to_dict()
        t2 = TurnRecord.from_dict(d)
        self.assertEqual(t2.sequence, 5)
        self.assertEqual(t2.content, "scan memory")
        self.assertEqual(t2.intent_result["expectation"], "TOOL")
        self.assertEqual(t2.latency_ms, 12.3)


class TestSessionManager(unittest.TestCase):
    """验证 SessionManager 内存管理。"""

    def setUp(self):
        self.mgr = SessionManager(ttl_seconds=3600)

    def test_create_session(self):
        s = self.mgr.create_session(tenant_id="t1", user_id="u1")
        self.assertEqual(s.tenant_id, "t1")
        self.assertEqual(s.user_id, "u1")
        self.assertEqual(s.state, "active")

    def test_get_session_found(self):
        s = self.mgr.create_session()
        got = self.mgr.get_session(s.session_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.session_id, s.session_id)

    def test_get_session_not_found(self):
        got = self.mgr.get_session("nonexistent")
        self.assertIsNone(got)

    def test_get_session_expired(self):
        s = self.mgr.create_session()
        s.expires_at = time.time() - 1  # 已过期
        got = self.mgr.get_session(s.session_id)
        self.assertIsNone(got)

    def test_update_session(self):
        s = self.mgr.create_session()
        turn = TurnRecord(sequence=0, timestamp=time.time(), content="hello")
        updated = self.mgr.update_session(s.session_id, turn)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.turn_count, 1)
        self.assertEqual(len(updated.history), 1)

    def test_update_session_not_found(self):
        turn = TurnRecord(sequence=0, timestamp=time.time(), content="hello")
        updated = self.mgr.update_session("nonexistent", turn)
        self.assertIsNone(updated)

    def test_close_session(self):
        s = self.mgr.create_session()
        summary = self.mgr.close_session(s.session_id)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.session_id, s.session_id)
        self.assertEqual(summary.final_state, "closed")
        # 关闭后内存中应不存在
        self.assertIsNone(self.mgr.get_session(s.session_id))

    def test_close_session_not_found(self):
        summary = self.mgr.close_session("nonexistent")
        self.assertIsNone(summary)

    def test_list_active_sessions(self):
        s1 = self.mgr.create_session(tenant_id="t1")
        s2 = self.mgr.create_session(tenant_id="t1")
        self.mgr.create_session(tenant_id="t2")
        ids = self.mgr.list_active_sessions("t1", limit=100)
        self.assertIn(s1.session_id, ids)
        self.assertIn(s2.session_id, ids)
        self.assertEqual(len(ids), 2)

    def test_evict_expired(self):
        s1 = self.mgr.create_session()
        s2 = self.mgr.create_session()
        s2.expires_at = time.time() - 1
        count = self.mgr.evict_expired()
        self.assertEqual(count, 1)
        self.assertIsNotNone(self.mgr.get_session(s1.session_id))
        self.assertIsNone(self.mgr.get_session(s2.session_id))

    def test_with_sqlite_store(self):
        if not HAS_SQLITE:
            self.skipTest("sqlite3 not available")
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = SQLiteSessionStore(db_path=path)
            mgr = SessionManager(store=store, ttl_seconds=3600)
            s = mgr.create_session(tenant_id="t1", user_id="u1")
            s.parse_context = {"pid": 1234}

            # 关闭会话触发持久化
            summary = mgr.close_session(s.session_id)
            self.assertTrue(summary.persisted)

            # 新建 manager，从持久化加载
            mgr2 = SessionManager(store=store, ttl_seconds=3600)
            loaded = mgr2.get_session(s.session_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.tenant_id, "t1")
            self.assertEqual(loaded.user_id, "u1")
            self.assertEqual(loaded.parse_context, {"pid": 1234})
        finally:
            store._conn.close()
            os.unlink(path)


class TestTokenBucket(unittest.TestCase):
    """验证令牌桶算法。"""

    def test_acquire_basic(self):
        b = TokenBucket(rate=10, burst=5)
        self.assertTrue(b.acquire())
        self.assertTrue(b.acquire())
        self.assertTrue(b.acquire())
        self.assertTrue(b.acquire())
        self.assertTrue(b.acquire())
        # 第 6 次应失败（桶容量 5）
        self.assertFalse(b.acquire())

    def test_refill_over_time(self):
        b = TokenBucket(rate=100, burst=1)  # 100 RPS = 每 10ms 1 令牌
        self.assertTrue(b.acquire())
        self.assertFalse(b.acquire())
        time.sleep(0.02)  # 等待 20ms，应获得 2 令牌
        self.assertTrue(b.acquire())

    def test_wait_time(self):
        b = TokenBucket(rate=1, burst=1)
        b.acquire()
        self.assertFalse(b.acquire())
        wait = b.wait_time()
        self.assertGreater(wait, 0.0)


class TestRateLimiter(unittest.TestCase):
    """验证 RateLimiter 双层限流。"""

    def setUp(self):
        self.rl = RateLimiter(
            default_tenant_rps=10,
            session_burst=3,
        )

    def test_allow_within_burst(self):
        tid, sid = "t1", "s1"
        for _ in range(3):
            allowed, _, _ = self.rl.check(tid, sid)
            self.assertTrue(allowed)
        # 第 4 次应被会话级限流
        allowed, _, reason = self.rl.check(tid, sid)
        self.assertFalse(allowed)
        self.assertEqual(reason, "session_rate_limited")

    def test_tenant_rate_limit(self):
        tid, sid = "t1", "s1"
        # 大量请求应触发租户级限流
        for _ in range(20):
            self.rl.check(tid, sid)
        # 此时应该大概率被租户限流
        allowed, _, reason = self.rl.check(tid, sid)
        # 不一定 100% 触发，但桶已消耗很多
        self.assertFalse(allowed)

    def test_release_session(self):
        tid, sid = "t1", "s1"
        for _ in range(3):
            self.rl.check(tid, sid)
        self.assertFalse(self.rl.check(tid, sid)[0])
        self.rl.release_session(sid)
        # 释放后重新创建 bucket
        allowed, _, _ = self.rl.check(tid, sid)
        self.assertTrue(allowed)

    def test_stats(self):
        stats = self.rl.get_stats()
        self.assertIn("tenant_buckets", stats)
        self.assertIn("session_buckets", stats)


@unittest.skipUnless(HAS_SQLITE, "sqlite3 not available")
class TestSQLiteSessionStore(unittest.TestCase):
    """验证 SQLite 存储。"""

    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.store = SQLiteSessionStore(db_path=self.path)

    def tearDown(self):
        self.store._conn.close()
        os.unlink(self.path)

    def test_save_and_load_session(self):
        import asyncio
        s = Session(session_id="test-123", tenant_id="t1", user_id="u1")
        s.parse_context = {"foo": "bar"}
        ok = asyncio.run(self.store.save_session(s))
        self.assertTrue(ok)

        loaded = asyncio.run(self.store.load_session("test-123"))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "test-123")
        self.assertEqual(loaded.tenant_id, "t1")
        self.assertEqual(loaded.parse_context, {"foo": "bar"})

    def test_load_not_found(self):
        import asyncio
        loaded = asyncio.run(self.store.load_session("nonexistent"))
        self.assertIsNone(loaded)

    def test_save_turn_and_history(self):
        import asyncio
        s = Session(session_id="h1")
        asyncio.run(self.store.save_session(s))

        t1 = TurnRecord(sequence=0, timestamp=1.0, role="user", content="hello")
        t2 = TurnRecord(sequence=1, timestamp=2.0, role="system", content="ok")
        asyncio.run(self.store.save_turn("h1", t1))
        asyncio.run(self.store.save_turn("h1", t2))

        hist = asyncio.run(self.store.get_history("h1", limit=10))
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0].sequence, 0)
        self.assertEqual(hist[1].sequence, 1)

    def test_history_pagination(self):
        import asyncio
        s = Session(session_id="h2")
        asyncio.run(self.store.save_session(s))
        for i in range(10):
            t = TurnRecord(sequence=i, timestamp=float(i), content=f"msg{i}")
            asyncio.run(self.store.save_turn("h2", t))

        hist = asyncio.run(self.store.get_history("h2", limit=5, before_sequence=10))
        self.assertEqual(len(hist), 5)
        self.assertEqual(hist[0].sequence, 5)
        self.assertEqual(hist[-1].sequence, 9)

    def test_delete_session(self):
        import asyncio
        s = Session(session_id="d1")
        asyncio.run(self.store.save_session(s))
        ok = asyncio.run(self.store.delete_session("d1"))
        self.assertTrue(ok)
        loaded = asyncio.run(self.store.load_session("d1"))
        self.assertIsNone(loaded)

    def test_list_active_sessions(self):
        import asyncio
        s1 = Session(session_id="l1", tenant_id="t1")
        s2 = Session(session_id="l2", tenant_id="t1")
        asyncio.run(self.store.save_session(s1))
        asyncio.run(self.store.save_session(s2))
        ids = asyncio.run(self.store.list_active_sessions("t1", limit=100))
        self.assertIn("l1", ids)
        self.assertIn("l2", ids)

    def test_health_check(self):
        import asyncio
        ok = asyncio.run(self.store.health_check())
        self.assertTrue(ok)


class TestAgentService(unittest.TestCase):
    """验证 AgentService 集成。"""

    def setUp(self):
        # Mock 核心引擎 — 需要返回具体属性（不能是 MagicMock 默认比较）
        self.mock_pcr = MagicMock()
        self.mock_parser = MagicMock()

        # 配置 PCR evaluate 返回带具体数值的对象
        mock_pcr_out = MagicMock()
        mock_pcr_out.expectation = "TOOL"
        mock_pcr_out.noise_level = 0.1
        mock_pcr_out.complexity_level = 0.2
        mock_pcr_out.confidence = 0.9
        mock_pcr_out.cognitive_profile = MagicMock()
        mock_pcr_out.cognitive_profile.metacognition = 0.5
        mock_pcr_out.cognitive_profile.stability = 0.8
        mock_pcr_out.cognitive_profile.to_dict = MagicMock(return_value={"metacognition": 0.5, "stability": 0.8})
        self.mock_pcr.evaluate = MagicMock(return_value=mock_pcr_out)

        mgr = SessionManager()
        rl = RateLimiter()
        self.service = AgentService(
            pcr=self.mock_pcr,
            parser=self.mock_parser,
            session_manager=mgr,
            rate_limiter=rl,
        )

    def test_create_and_get_session(self):
        s = self.service.create_session(tenant_id="t1", user_id="u1")
        self.assertEqual(s.tenant_id, "t1")
        self.assertEqual(s.user_id, "u1")

        status = self.service.get_status(s.session_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "active")
        self.assertEqual(status["current_turn"], 0)

    def test_process_message_unknown_session(self):
        status, intent, clar, error, trace = self.service.process_message(
            "bad-session", "hello"
        )
        self.assertEqual(status, "error")
        self.assertIsNotNone(error)
        self.assertEqual(error.code, "SESSION_EXPIRED")

    def test_process_message_rate_limited(self):
        s = self.service.create_session()
        # 触发 burst 限制
        for _ in range(5):
            self.service.process_message(s.session_id, "spam")
        status, intent, clar, error, trace = self.service.process_message(
            s.session_id, "spam"
        )
        self.assertEqual(status, "error")
        self.assertIsNotNone(error)
        self.assertEqual(error.code, "RATE_LIMITED")

    def test_close_session(self):
        s = self.service.create_session()
        summary = self.service.close_session(s.session_id)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.session_id, s.session_id)
        self.assertEqual(summary.final_state, "closed")

    def test_health_check(self):
        health = self.service.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertIn("pcr", health["components"])
        self.assertIn("parser", health["components"])
        self.assertIn("session_manager", health["components"])

    def test_submit_clarification_no_session(self):
        status, intent, clar, error = self.service.submit_clarification(
            "bad", "cid"
        )
        self.assertEqual(status, "error")
        self.assertEqual(error.code, "SESSION_EXPIRED")

    def test_get_history(self):
        s = self.service.create_session()
        # 先处理一些消息
        for i in range(3):
            self.service.process_message(s.session_id, f"msg{i}")
        hist = self.service.get_history(s.session_id, limit=10)
        self.assertEqual(len(hist), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
