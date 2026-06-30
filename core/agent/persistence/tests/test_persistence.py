# -*- coding: utf-8 -*-
"""
core/agent/persistence/tests/test_persistence.py
────────────────────────────────────────────────
Persistence layer unit tests.
"""

import os
import tempfile
import unittest
import time

from core.agent.persistence.cli_middleware import CLISessionPersistence
from core.agent.persistence.sqlite_store import SQLiteSessionStore
from core.agent.persistence.session_manager import SessionManager
from core.agent.persistence.models import Session, TurnRecord, SessionState
from core.agent.gates import AdaptiveThresholds


class TestSQLiteSessionStore(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_load_session(self):
        sid = self.store.save_session(Session(session_id="test-1"))
        self.assertTrue(sid)
        session = self.store.load_session("test-1")
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, "test-1")

    def test_save_and_load_turns(self):
        self.store.save_session(Session(session_id="test-2"))
        for i in range(3):
            turn = TurnRecord(sequence=i + 1, role="user", content=f"query {i}")
            self.store.save_turn("test-2", turn)

        turns = self.store.load_turns("test-2", limit=10)
        self.assertEqual(len(turns), 3)
        self.assertEqual(turns[0].content, "query 0")
        self.assertEqual(turns[2].content, "query 2")

    def test_session_upsert(self):
        session = Session(session_id="test-3", version=1)
        self.store.save_session(session)
        session.version = 2
        self.store.save_session(session)
        loaded = self.store.load_session("test-3")
        self.assertEqual(loaded.version, 2)

    def test_list_active_sessions(self):
        for i in range(5):
            self.store.save_session(Session(session_id=f"sess-{i}"))
            time.sleep(0.01)  # 确保 updated_at 有差异

        sids = self.store.list_active_sessions(limit=3)
        self.assertEqual(len(sids), 3)
        # 最近创建的在前面
        self.assertEqual(sids[0], "sess-4")

    def test_delete_session_cascade(self):
        self.store.save_session(Session(session_id="del-1"))
        self.store.save_turn("del-1", TurnRecord(sequence=1, role="user", content="hi"))
        self.store.delete_session("del-1")
        self.assertIsNone(self.store.load_session("del-1"))
        turns = self.store.load_turns("del-1", limit=10)
        self.assertEqual(len(turns), 0)

    def test_cleanup_expired(self):
        self.store.save_session(Session(session_id="old-1"))
        # 手动把 updated_at 改到过去
        self.store._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (time.time() - 10000, "old-1")
        )
        self.store._conn.commit()
        count = self.store.cleanup_expired(ttl_seconds=3600)
        self.assertEqual(count, 1)
        self.assertIsNone(self.store.load_session("old-1"))


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.manager = SessionManager(self.store, auto_eviction=False)

    def tearDown(self):
        self.manager.shutdown()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_get_session(self):
        session = self.manager.create_session(user_id="alice")
        self.assertEqual(session.user_id, "alice")

        loaded = self.manager.get_session(session.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.user_id, "alice")

    def test_save_turn_updates_count(self):
        session = self.manager.create_session()
        sid = session.session_id
        self.manager.save_turn(sid, TurnRecord(role="user", content="hello"))
        self.manager.save_turn(sid, TurnRecord(role="assistant", content="hi"))

        loaded = self.manager.get_session(sid)
        self.assertEqual(loaded.turn_count, 2)
        self.assertEqual(len(loaded.history), 2)

    def test_close_session(self):
        session = self.manager.create_session()
        sid = session.session_id
        self.manager.close_session(sid)
        loaded = self.manager.get_session(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state.value, "closed")

    def test_lru_eviction(self):
        manager = SessionManager(self.store, max_memory_sessions=2, auto_eviction=False)
        s1 = manager.create_session()
        s2 = manager.create_session()
        s3 = manager.create_session()  # 应触发 LRU 淘汰 s1

        # 访问 s1 让它回到缓存
        manager.get_session(s1.session_id)
        # 再创建 s4，应该淘汰 s2
        s4 = manager.create_session()

        # s2 应该被保存到磁盘但不在缓存
        manager.get_session(s2.session_id)  # 从磁盘重新加载
        self.assertIsNotNone(manager.get_session(s2.session_id))
        manager.shutdown()


class TestCLISessionPersistence(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.persistence = CLISessionPersistence(db_path=self.db_path)

    def tearDown(self):
        self.persistence.shutdown()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_load(self):
        sid = self.persistence.create_session()
        self.persistence.close_session(sid)

        session = self.persistence.get_or_load(sid)
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, sid)

    def test_add_turn_and_recover(self):
        sid = self.persistence.create_session()
        for i in range(3):
            self.persistence.add_turn(sid, "user", f"query {i}")

        # 模拟重启：新建 persistence 实例
        self.persistence.shutdown()
        new_persistence = CLISessionPersistence(db_path=self.db_path)

        session = new_persistence.get_or_load(sid)
        self.assertEqual(session.turn_count, 3)
        self.assertEqual(len(session.history), 3)
        self.assertEqual(session.history[0].content, "query 0")
        self.assertEqual(session.history[2].content, "query 2")
        new_persistence.shutdown()

    def test_cognitive_profile_persistence(self):
        sid = self.persistence.create_session()
        profile = {"metacognition": 0.8, "stability": 0.9, "expertise": 0.7}
        self.persistence.update_cognitive_profile(sid, profile)
        self.persistence.close_session(sid)  # 触发 flush

        # 模拟重启
        self.persistence.shutdown()
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        session = new_persistence.get_or_load(sid)
        self.assertAlmostEqual(session.cognitive_profile["metacognition"], 0.8)
        self.assertAlmostEqual(session.cognitive_profile["stability"], 0.9)
        new_persistence.shutdown()

    def test_adaptive_thresholds_persistence(self):
        sid = self.persistence.create_session()
        adaptive = AdaptiveThresholds()
        adaptive.feedback(required_clarification=True)
        self.persistence.update_adaptive_thresholds(sid, adaptive.to_dict())
        self.persistence.close_session(sid)

        self.persistence.shutdown()
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        session = new_persistence.get_or_load(sid)
        self.assertLess(session.adaptive_thresholds["noise_fast_path"], 0.30)
        new_persistence.shutdown()

    def test_list_sessions(self):
        for _ in range(5):
            self.persistence.create_session()
        sessions = self.persistence.list_sessions(limit=3)
        self.assertEqual(len(sessions), 3)

    def test_batch_flush(self):
        sid = self.persistence.create_session()
        for i in range(4):
            self.persistence.update_cognitive_profile(sid, {"expertise": i * 0.1})
        # 第 5 次触发 flush
        self.persistence.update_cognitive_profile(sid, {"expertise": 0.5})

        session = self.persistence.get_or_load(sid)
        self.assertAlmostEqual(session.cognitive_profile["expertise"], 0.5)


if __name__ == "__main__":
    unittest.main()
