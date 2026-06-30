# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_production_optimizations.py
────────────────────────────────────────────────────────
生产优化测试（v2.4 生产优化）。

覆盖：
  - AsyncSQLiteSessionStore（异步 CRUD）
  - RedisSessionStore（占位测试，需要 redis 服务）
  - AsyncSessionManager（异步生命周期 + 后台清理）
  - RequestQueue（优先队列 + 超时 + 背压）
  - 集成：异步会话 + 队列 + 服务

跳过无依赖的测试（aiosqlite / redis 未安装）。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from core.agent.service.models import Session, TurnRecord


class TestAsyncSQLiteSessionStore(unittest.TestCase):
    """验证异步 SQLite 存储。"""

    @classmethod
    def setUpClass(cls):
        try:
            import aiosqlite
            cls.has_aiosqlite = True
        except ImportError:
            cls.has_aiosqlite = False

    def setUp(self):
        if not self.has_aiosqlite:
            self.skipTest("aiosqlite not installed")
        self.fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        from core.agent.service.stores.async_sqlite import AsyncSQLiteSessionStore
        self.store = AsyncSQLiteSessionStore(db_path=self.path)

    def tearDown(self):
        # asyncio.run(self.store.close())  # 可能抛异常
        try:
            os.unlink(self.path)
        except PermissionError:
            pass

    def test_save_and_load_session(self):
        async def _test():
            s = Session(session_id="test-123", tenant_id="t1", user_id="u1")
            s.parse_context = {"foo": "bar"}
            ok = await self.store.save_session(s)
            self.assertTrue(ok)

            loaded = await self.store.load_session("test-123")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.session_id, "test-123")
            self.assertEqual(loaded.tenant_id, "t1")
            self.assertEqual(loaded.parse_context, {"foo": "bar"})

        asyncio.run(_test())

    def test_save_turn_and_history(self):
        async def _test():
            s = Session(session_id="h1")
            await self.store.save_session(s)

            t1 = TurnRecord(sequence=0, timestamp=1.0, role="user", content="hello")
            t2 = TurnRecord(sequence=1, timestamp=2.0, role="system", content="ok")
            await self.store.save_turn("h1", t1)
            await self.store.save_turn("h1", t2)

            hist = await self.store.get_history("h1", limit=10)
            self.assertEqual(len(hist), 2)
            self.assertEqual(hist[0].sequence, 0)
            self.assertEqual(hist[1].sequence, 1)

        asyncio.run(_test())

    def test_history_pagination(self):
        async def _test():
            s = Session(session_id="h2")
            await self.store.save_session(s)
            for i in range(10):
                t = TurnRecord(sequence=i, timestamp=float(i), content=f"msg{i}")
                await self.store.save_turn("h2", t)

            hist = await self.store.get_history("h2", limit=5, before_sequence=10)
            self.assertEqual(len(hist), 5)
            self.assertEqual(hist[0].sequence, 5)
            self.assertEqual(hist[-1].sequence, 9)

        asyncio.run(_test())

    def test_delete_session(self):
        async def _test():
            s = Session(session_id="d1")
            await self.store.save_session(s)
            ok = await self.store.delete_session("d1")
            self.assertTrue(ok)
            loaded = await self.store.load_session("d1")
            self.assertIsNone(loaded)

        asyncio.run(_test())

    def test_list_active_sessions(self):
        async def _test():
            s1 = Session(session_id="l1", tenant_id="t1")
            s2 = Session(session_id="l2", tenant_id="t1")
            await self.store.save_session(s1)
            await self.store.save_session(s2)
            ids = await self.store.list_active_sessions("t1", limit=100)
            self.assertIn("l1", ids)
            self.assertIn("l2", ids)

        asyncio.run(_test())

    def test_health_check(self):
        async def _test():
            ok = await self.store.health_check()
            self.assertTrue(ok)

        asyncio.run(_test())


class TestAsyncSessionManager(unittest.TestCase):
    """验证异步会话管理器。"""

    def test_create_and_get_session(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager()
            await mgr.start()
            s = await mgr.create_session(tenant_id="t1", user_id="u1")
            self.assertEqual(s.tenant_id, "t1")

            got = await mgr.get_session(s.session_id)
            self.assertIsNotNone(got)
            self.assertEqual(got.session_id, s.session_id)

            await mgr.stop()

        asyncio.run(_test())

    def test_get_session_not_found(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager()
            got = await mgr.get_session("nonexistent")
            self.assertIsNone(got)

        asyncio.run(_test())

    def test_update_session(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager()
            s = await mgr.create_session()
            turn = TurnRecord(sequence=0, timestamp=time.time(), content="hello")
            updated = await mgr.update_session(s.session_id, turn)
            self.assertIsNotNone(updated)
            self.assertEqual(updated.turn_count, 1)

        asyncio.run(_test())

    def test_close_session(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager()
            s = await mgr.create_session()
            summary = await mgr.close_session(s.session_id)
            self.assertIsNotNone(summary)
            self.assertEqual(summary.session_id, s.session_id)
            self.assertEqual(summary.final_state, "closed")

            # 关闭后内存中应不存在
            got = await mgr.get_session(s.session_id)
            self.assertIsNone(got)

        asyncio.run(_test())

    def test_eviction_background(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager(ttl_seconds=1, eviction_interval_seconds=1)
            await mgr.start()
            s = await mgr.create_session()
            # 修改过期时间使其更快过期
            s.expires_at = time.time() + 0.5
            # 等待后台清理
            await asyncio.sleep(2)
            got = await mgr.get_session(s.session_id)
            self.assertIsNone(got)
            await mgr.stop()

        asyncio.run(_test())

    def test_list_active_sessions(self):
        async def _test():
            from core.agent.service.async_session_manager import AsyncSessionManager
            mgr = AsyncSessionManager()
            s1 = await mgr.create_session(tenant_id="t1")
            s2 = await mgr.create_session(tenant_id="t1")
            await mgr.create_session(tenant_id="t2")
            ids = await mgr.list_active_sessions("t1", limit=100)
            self.assertIn(s1.session_id, ids)
            self.assertIn(s2.session_id, ids)
            self.assertEqual(len(ids), 2)

        asyncio.run(_test())

    def test_with_async_sqlite_store(self):
        async def _test():
            try:
                import aiosqlite
            except ImportError:
                self.skipTest("aiosqlite not installed")

            from core.agent.service.async_session_manager import AsyncSessionManager
            from core.agent.service.stores.async_sqlite import AsyncSQLiteSessionStore

            fd, path = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            store = AsyncSQLiteSessionStore(db_path=path)
            mgr = AsyncSessionManager(store=store, ttl_seconds=3600)

            s = await mgr.create_session(tenant_id="t1", user_id="u1")
            s.parse_context = {"pid": 1234}

            # 关闭会话触发持久化
            summary = await mgr.close_session(s.session_id)
            self.assertTrue(summary.persisted)

            # 新建 manager，从持久化加载
            mgr2 = AsyncSessionManager(store=store, ttl_seconds=3600)
            loaded = await mgr2.get_session(s.session_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.tenant_id, "t1")
            self.assertEqual(loaded.user_id, "u1")
            self.assertEqual(loaded.parse_context, {"pid": 1234})

            await store.close()
            try:
                os.unlink(path)
            except PermissionError:
                pass

        asyncio.run(_test())


class TestRequestQueue(unittest.TestCase):
    """验证请求队列。"""

    def test_enqueue_and_process(self):
        async def _test():
            from core.agent.service.request_queue import RequestQueue

            processed = []
            async def processor(item):
                processed.append(item.request_id)
                return {"status": "ok"}

            q = RequestQueue()
            await q.start(processor)

            future = await q.enqueue("s1", {"content": "hello"})
            result = await future
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(processed), 1)

            await q.stop()

        asyncio.run(_test())

    def test_priority_order(self):
        async def _test():
            from core.agent.service.request_queue import RequestQueue

            order = []
            async def processor(item):
                order.append(item.priority)
                await asyncio.sleep(0.01)
                return {}

            q = RequestQueue()
            await q.start(processor)

            # 先入队低优先级，再入队高优先级
            f1 = await q.enqueue("s1", {"c": "1"}, priority=1)
            f2 = await q.enqueue("s1", {"c": "2"}, priority=0)
            f3 = await q.enqueue("s1", {"c": "3"}, priority=1)

            await asyncio.gather(f1, f2, f3)
            # 高优先级 (0) 应该先被处理
            self.assertEqual(order[0], 0)

            await q.stop()

        asyncio.run(_test())

    def test_backpressure(self):
        async def _test():
            from core.agent.service.request_queue import RequestQueue

            async def slow_processor(item):
                await asyncio.sleep(10)  # 很慢
                return {}

            q = RequestQueue(max_global_depth=2, per_session_max_depth=1)
            await q.start(slow_processor)

            # 第1个入队成功
            f1 = await q.enqueue("s1", {"c": "1"})
            # 同 session 第2个应该背压（per_session_max_depth=1）
            f2 = await q.enqueue("s1", {"c": "2"})
            with self.assertRaises(RuntimeError):
                await f2

            await q.stop()

        asyncio.run(_test())

    def test_timeout(self):
        async def _test():
            from core.agent.service.request_queue import RequestQueue

            async def slow_processor(item):
                await asyncio.sleep(10)
                return {}

            q = RequestQueue(default_timeout_seconds=0.5)
            await q.start(slow_processor)

            future = await q.enqueue("s1", {"c": "1"})
            with self.assertRaises(TimeoutError):
                await future

            await q.stop()

        asyncio.run(_test())

    def test_stats(self):
        async def _test():
            from core.agent.service.request_queue import RequestQueue

            async def processor(item):
                return {}

            q = RequestQueue()
            await q.start(processor)

            stats = await q.get_stats()
            self.assertIn("global_depth", stats)
            self.assertIn("session_depths", stats)
            self.assertTrue(stats["running"])

            await q.stop()

        asyncio.run(_test())


class TestIntegrationAsync(unittest.TestCase):
    """集成测试：异步会话 + 存储 + 队列。"""

    def test_end_to_end_with_async_sqlite(self):
        async def _test():
            try:
                import aiosqlite
            except ImportError:
                self.skipTest("aiosqlite not installed")

            from core.agent.service.async_session_manager import AsyncSessionManager
            from core.agent.service.stores.async_sqlite import AsyncSQLiteSessionStore
            from core.agent.service.request_queue import RequestQueue

            fd, path = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            store = AsyncSQLiteSessionStore(db_path=path)
            mgr = AsyncSessionManager(store=store, ttl_seconds=3600)
            await mgr.start()

            q = RequestQueue()
            async def processor(item):
                # 模拟处理：获取 session，更新历史
                sess = await mgr.get_session(item.session_id)
                if sess is None:
                    return {"error": "session not found"}
                turn = TurnRecord(
                    sequence=sess.turn_count,
                    timestamp=time.time(),
                    content=item.payload.get("content", ""),
                )
                await mgr.update_session(item.session_id, turn)
                return {"status": "ok", "turn": sess.turn_count}

            await q.start(processor)

            # 创建会话
            s = await mgr.create_session(tenant_id="t1")

            # 发送 3 条消息
            futures = []
            for i in range(3):
                fut = await q.enqueue(s.session_id, {"content": f"msg{i}"})
                futures.append(fut)

            results = await asyncio.gather(*futures)
            for r in results:
                self.assertEqual(r["status"], "ok")

            # 验证历史
            sess = await mgr.get_session(s.session_id)
            self.assertEqual(sess.turn_count, 3)

            await q.stop()
            await mgr.stop()
            await store.close()
            try:
                os.unlink(path)
            except PermissionError:
                pass

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
