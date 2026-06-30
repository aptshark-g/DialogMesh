# -*- coding: utf-8 -*-
"""
core/agent/persistence/tests/test_persistence_graph.py
────────────────────────────────────────────────────────
Persistence graph / entity / wave / window / tiered tests.
"""

import os
import tempfile
import unittest
import time

from core.agent.persistence.sqlite_store import SQLiteSessionStore
from core.agent.persistence.graph_store import GraphStore
from core.agent.persistence.entity_index import EntityIndex
from core.agent.persistence.wave_query import WaveQueryEngine, WaveQueryResult
from core.agent.persistence.window_snapshot import WindowSnapshot, WindowSnapshotStore
from core.agent.persistence.tiered_storage import TieredStorageManager, TierPolicy, TierLevel
from core.agent.persistence.models import Session, TurnRecord
from core.agent.topic_tree.models import TopicNode, TopicEdge, TopicEdgeType


class TestGraphStore(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.store._ensure_connection()  # 初始化连接
        self.graph = GraphStore(self.store._conn, self.store._lock)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_save_and_load_node(self):
        node = TopicNode(id="n1", name="test_topic", entities=[{"type": "file", "value": "main.py"}])
        self.assertTrue(self.graph.save_node("sess-1", node))

        loaded = self.graph.load_node("n1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test_topic")
        self.assertEqual(loaded.entities[0]["value"], "main.py")

    def test_save_and_load_edge(self):
        e = TopicEdge(source_id="n1", target_id="n2", edge_type=TopicEdgeType.PARENT_CHILD, weight=0.8)
        self.assertTrue(self.graph.save_edge("sess-1", e))

        edges = self.graph.load_edges_from("n1")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].target_id, "n2")
        self.assertEqual(edges[0].weight, 0.8)

    def test_bfs_neighbors(self):
        # n1 -> n2 -> n3
        nodes = [
            TopicNode(id="n1", name="root"),
            TopicNode(id="n2", name="child"),
            TopicNode(id="n3", name="grandchild"),
        ]
        for n in nodes:
            self.graph.save_node("sess-1", n)

        edges = [
            TopicEdge("n1", "n2", TopicEdgeType.PARENT_CHILD, 1.0),
            TopicEdge("n2", "n3", TopicEdgeType.PARENT_CHILD, 0.9),
        ]
        for e in edges:
            self.graph.save_edge("sess-1", e)

        result = self.graph.bfs_neighbors("n1", max_depth=2)
        self.assertEqual(len(result), 2)
        # depth order: n2(depth=1), n3(depth=2)
        ids = [r[0] for r in result]
        self.assertIn("n2", ids)
        self.assertIn("n3", ids)

    def test_find_nodes_by_entity(self):
        node = TopicNode(id="n1", name="topic1", entities=[{"type": "file", "value": "test.py"}])
        self.graph.save_node("sess-1", node)

        found = self.graph.find_nodes_by_entity("sess-1", "file", "test.py")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].id, "n1")

        not_found = self.graph.find_nodes_by_entity("sess-1", "file", "notexist.py")
        self.assertEqual(len(not_found), 0)

    def test_delete_node_cascade(self):
        self.graph.save_node("sess-1", TopicNode(id="n1"))
        self.graph.save_edge("sess-1", TopicEdge("n1", "n2", TopicEdgeType.ENTITY_REFERENCE))
        self.graph.delete_node("n1")

        self.assertIsNone(self.graph.load_node("n1"))
        self.assertEqual(len(self.graph.load_edges_from("n1")), 0)

    def test_batch_save(self):
        nodes = [TopicNode(id=f"n{i}") for i in range(5)]
        self.assertTrue(self.graph.save_nodes_batch("sess-1", nodes))
        self.assertEqual(self.graph.count_nodes("sess-1"), 5)

    def test_count(self):
        self.graph.save_node("sess-1", TopicNode(id="n1"))
        self.graph.save_node("sess-2", TopicNode(id="n2"))
        self.assertEqual(self.graph.count_nodes(), 2)
        self.assertEqual(self.graph.count_nodes("sess-1"), 1)


class TestEntityIndex(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.store._ensure_connection()  # 初始化连接
        self.index = EntityIndex(self.store._conn, self.store._lock)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_index_and_search(self):
        self.assertTrue(self.index.index_entity("file", "main.py", "sess-1", node_id="n1", turn_seq=1))
        self.assertTrue(self.index.index_entity("file", "utils.py", "sess-1", node_id="n2", turn_seq=2))
        self.assertTrue(self.index.index_entity("file", "main.py", "sess-2", node_id="n3", turn_seq=1))

        results = self.index.search_by_value("main.py")
        self.assertEqual(len(results), 2)
        sids = [r["session_id"] for r in results]
        self.assertIn("sess-1", sids)
        self.assertIn("sess-2", sids)

    def test_search_by_type(self):
        self.index.index_entity("file", "a.py", "sess-1")
        self.index.index_entity("file", "b.py", "sess-1")
        self.index.index_entity("dir", "src", "sess-1")

        files = self.index.search_by_type("file")
        self.assertEqual(len(files), 2)

    def test_search_by_session(self):
        self.index.index_entity("file", "a.py", "sess-1")
        self.index.index_entity("file", "b.py", "sess-1")
        self.index.index_entity("file", "c.py", "sess-2")

        results = self.index.search_by_session("sess-1")
        self.assertEqual(len(results), 2)

    def test_find_sessions_by_entity(self):
        self.index.index_entity("keyword", "Python", "sess-1")
        self.index.index_entity("keyword", "Python", "sess-2")
        self.index.index_entity("keyword", "Rust", "sess-3")

        sids = self.index.find_sessions_by_entity("keyword", "Python")
        self.assertEqual(len(sids), 2)
        self.assertIn("sess-1", sids)
        self.assertIn("sess-2", sids)

    def test_top_entities(self):
        self.index.index_entity("file", "common.py", "sess-1")
        self.index.index_entity("file", "common.py", "sess-1")
        self.index.index_entity("file", "common.py", "sess-2")
        self.index.index_entity("file", "rare.py", "sess-1")

        top = self.index.get_top_entities(limit=2)
        self.assertEqual(len(top), 2)
        # common.py 出现 3 次
        self.assertEqual(top[0][1], "common.py")
        self.assertEqual(top[0][2], 3)

    def test_cleanup_old(self):
        self.index.index_entity("file", "old.py", "sess-1")
        # 修改时间为过去
        self.store._conn.execute(
            "UPDATE entity_index SET timestamp = ? WHERE entity_value = ?",
            (time.time() - 10000, "old.py")
        )
        self.store._conn.commit()

        count = self.index.cleanup_old(ttl_seconds=3600)
        self.assertEqual(count, 1)
        results = self.index.search_by_value("old.py")
        self.assertEqual(len(results), 0)

    def test_stats(self):
        self.index.index_entity("type1", "val1", "sess-1")
        self.index.index_entity("type1", "val2", "sess-1")
        self.index.index_entity("type2", "val1", "sess-2")

        stats = self.index.get_stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertEqual(stats["distinct_types"], 2)
        self.assertEqual(stats["distinct_values"], 2)
        self.assertEqual(stats["distinct_sessions"], 2)


class TestWaveQuery(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.store._ensure_connection()  # 初始化连接
        self.graph = GraphStore(self.store._conn, self.store._lock)
        self.index = EntityIndex(self.store._conn, self.store._lock)
        self.engine = WaveQueryEngine(self.graph, self.index)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_wave_from_node(self):
        # 创建链式图: n1 -> n2 -> n3
        for i in range(1, 4):
            self.graph.save_node("sess-1", TopicNode(id=f"n{i}", name=f"node{i}"))

        self.graph.save_edge("sess-1", TopicEdge("n1", "n2", TopicEdgeType.PARENT_CHILD, 1.0))
        self.graph.save_edge("sess-1", TopicEdge("n2", "n3", TopicEdgeType.PARENT_CHILD, 0.9))
        self.graph.save_edge("sess-1", TopicEdge("n1", "n3", TopicEdgeType.ENTITY_REFERENCE, 0.5))

        results = self.engine.wave_from_node("n1", max_depth=2, top_k=10)
        self.assertGreaterEqual(len(results), 2)
        # n2 深度=1, weight=1.0; n3 深度=2, weight=0.9（经由 n2）或 0.5（直接）
        ids = {r.node_id: r for r in results}
        self.assertIn("n2", ids)
        self.assertIn("n3", ids)

    def test_wave_from_entity(self):
        self.graph.save_node("sess-1", TopicNode(id="n1", entities=[{"type": "file", "value": "main.py"}]))
        self.graph.save_node("sess-1", TopicNode(id="n2", entities=[]))
        self.graph.save_edge("sess-1", TopicEdge("n1", "n2", TopicEdgeType.ENTITY_REFERENCE, 1.0))
        self.index.index_entity("file", "main.py", "sess-1", node_id="n1")

        results = self.engine.wave_from_entity("file", "main.py", max_depth=1)
        self.assertGreaterEqual(len(results), 1)

    def test_hybrid_query_anchor(self):
        self.graph.save_node("sess-1", TopicNode(id="n1"))
        self.graph.save_node("sess-1", TopicNode(id="n2"))
        self.graph.save_edge("sess-1", TopicEdge("n1", "n2", TopicEdgeType.PARENT_CHILD, 1.0))

        results = self.engine.hybrid_query(anchor_node_id="n1", max_depth=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node_id, "n2")

    def test_hybrid_query_entity(self):
        self.graph.save_node("sess-1", TopicNode(id="n1", entities=[{"type": "x", "value": "y"}]))
        self.graph.save_node("sess-1", TopicNode(id="n2"))
        self.graph.save_edge("sess-1", TopicEdge("n1", "n2", TopicEdgeType.PARENT_CHILD, 1.0))
        self.index.index_entity("x", "y", "sess-1", node_id="n1")

        results = self.engine.hybrid_query(entity_type="x", entity_value="y", max_depth=1)
        self.assertGreaterEqual(len(results), 1)

    def test_sql_generation(self):
        sql = WaveQueryEngine.generate_bfs_sql("n1", max_depth=2, min_weight=0.5)
        self.assertIn("WITH RECURSIVE wave", sql)
        self.assertIn("n1", sql)
        self.assertIn("depth < 2", sql.lower())

    def test_anchor_suggestions(self):
        self.graph.save_node("sess-1", TopicNode(id="n1", name="root", depth=0, entities=[{"type": "t", "value": "v"}]))
        self.graph.save_node("sess-1", TopicNode(id="n2", name="child", depth=1))

        suggestions = self.engine.get_anchor_suggestions("sess-1")
        self.assertGreaterEqual(len(suggestions), 1)


class TestWindowSnapshot(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.store._ensure_connection()  # 初始化连接
        self.snapshot_store = WindowSnapshotStore(self.store._conn, self.store._lock)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_checkpoint_and_restore(self):
        from core.agent.pcr.datacontract import HistoryEntry

        snapshot = WindowSnapshot(
            session_id="sess-1",
            current_node_id="n1",
            history=[HistoryEntry(role="user", content="hello")],
            entity_cache_entries=[{"type": "file", "value": "a.py"}],
            cognitive_profile={"expertise": 0.8},
            adaptive_thresholds={"noise": 0.3},
            window_metadata={"topic": "test"},
        )
        self.assertTrue(self.snapshot_store.checkpoint(snapshot))

        restored = self.snapshot_store.restore("sess-1")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.current_node_id, "n1")
        self.assertEqual(len(restored.history), 1)
        self.assertEqual(restored.history[0].content, "hello")
        self.assertEqual(restored.cognitive_profile["expertise"], 0.8)

    def test_versioning(self):
        s1 = WindowSnapshot(session_id="sess-1", current_node_id="n1", timestamp=1000.0)
        s2 = WindowSnapshot(session_id="sess-1", current_node_id="n2", timestamp=2000.0)

        self.assertTrue(self.snapshot_store.checkpoint_with_history(s1, keep_versions=3))
        self.assertTrue(self.snapshot_store.checkpoint_with_history(s2, keep_versions=3))

        versions = self.snapshot_store.list_versions("sess-1")
        self.assertEqual(len(versions), 2)

    def test_cleanup_old(self):
        s = WindowSnapshot(session_id="sess-1", timestamp=time.time())
        self.snapshot_store.checkpoint(s)

        count = self.snapshot_store.cleanup_old(ttl_seconds=1)
        # 默认 1 秒内不删除，所以 count=0
        self.assertEqual(count, 0)

        # 修改为过去
        self.store._conn.execute(
            "UPDATE window_snapshots SET timestamp = ? WHERE session_id = ?",
            (time.time() - 100, "sess-1")
        )
        self.store._conn.commit()

        count = self.snapshot_store.cleanup_old(ttl_seconds=1)
        self.assertEqual(count, 1)

    def test_delete(self):
        s = WindowSnapshot(session_id="sess-1")
        self.snapshot_store.checkpoint(s)
        self.assertTrue(self.snapshot_store.delete("sess-1"))
        self.assertIsNone(self.snapshot_store.restore("sess-1"))


class TestTieredStorage(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = SQLiteSessionStore(self.db_path)
        self.store._ensure_connection()  # 初始化连接
        self.cold_dir = tempfile.mkdtemp()
        self.policy = TierPolicy(
            hot_ttl_seconds=1,       # 1秒未访问即淘汰
            warm_ttl_seconds=2,    # 2秒即归档
            cold_retention_days=30,
            cold_compression=False,
            max_hot_sessions=2,
        )
        self.tiered = TieredStorageManager(self.store, cold_dir=self.cold_dir, policy=self.policy)

    def tearDown(self):
        self.tiered.shutdown()
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
        import shutil
        shutil.rmtree(self.cold_dir, ignore_errors=True)

    def test_hot_put_and_get(self):
        session = Session(session_id="s1")
        self.tiered.put_hot(session)
        loaded = self.tiered.get_hot("s1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "s1")

    def test_hot_eviction(self):
        # 超过 max_hot_sessions=2，应自动驱逐到 warm
        for i in range(3):
            self.tiered.put_hot(Session(session_id=f"s{i}"))

        # s0 应该被驱逐到 warm
        hot_s0 = self.tiered.get_hot("s0")
        self.assertIsNone(hot_s0)

        # 但可以从 warm 加载
        warm_s0 = self.store.load_session("s0")
        self.assertIsNotNone(warm_s0)

    def test_archive_and_rehydrate(self):
        # 创建会话并保存到 warm
        session = Session(session_id="s1")
        self.store.save_session(session)
        for i in range(3):
            self.store.save_turn("s1", TurnRecord(sequence=i+1, role="user", content=f"q{i}"))

        # 修改为过去时间
        self.store._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (time.time() - 10, "s1")
        )
        self.store._conn.commit()

        # 归档
        archived, turns = self.tiered.archive_warm_to_cold(dry_run=False)
        self.assertEqual(archived, 1)
        self.assertEqual(turns, 3)

        # 验证 warm 已删除
        self.assertIsNone(self.store.load_session("s1"))

        # 回热
        rehydrated = self.tiered.rehydrate_cold_to_warm("s1")
        self.assertIsNotNone(rehydrated)
        self.assertEqual(rehydrated.session_id, "s1")
        self.assertEqual(rehydrated.turn_count, 3)

    def test_storage_stats(self):
        self.tiered.put_hot(Session(session_id="s1"))
        self.store.save_session(Session(session_id="s2"))

        stats = self.tiered.get_storage_stats()
        self.assertEqual(stats["hot"]["sessions"], 1)
        self.assertGreaterEqual(stats["warm"]["sessions"], 1)
        self.assertIn("cold", stats)

    def test_cleanup_cold(self):
        # 创建冷文件
        import pathlib
        old_file = pathlib.Path(self.cold_dir) / "old.jsonl"
        old_file.write_text("{}")
        # 修改 mtime 到过去
        os.utime(old_file, (time.time() - 100 * 86400, time.time() - 100 * 86400))

        count = self.tiered.cleanup_cold(dry_run=False)
        self.assertEqual(count, 1)
        self.assertFalse(old_file.exists())


if __name__ == "__main__":
    unittest.main()
