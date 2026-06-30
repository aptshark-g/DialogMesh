# -*- coding: utf-8 -*-
"""
core/agent/topic_tree/tests/test_manager_v2.py
────────────────────────────────────────────
TopicTree Manager V2 极致化功能测试。
"""

import unittest
from core.agent.topic_tree.manager_v2 import (
    TopicTreeManagerV2,
    EmbeddingEngine,
    CohesionCalculator,
    CohesionMetrics,
    TopicDecisionClassifier,
    ForkPointLocator,
    MergeEngine,
    ReactFlowExporter,
    RoutingDecisionV2,
)
from core.agent.topic_tree.models import TopicNode


class TestEmbeddingEngine(unittest.TestCase):
    def test_encode_fallback(self):
        """无 sentence-transformers 时回退到 hash embedding。"""
        vec = EmbeddingEngine.encode("test query")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), 384)
        # 归一化检查
        import math
        norm = math.sqrt(sum(v * v for v in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_deterministic(self):
        """相同输入相同输出。"""
        v1 = EmbeddingEngine.encode("hello world")
        v2 = EmbeddingEngine.encode("hello world")
        self.assertEqual(v1, v2)


class TestCohesionCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = CohesionCalculator()

    def test_perfect_match(self):
        """完全匹配时 cohesion = 1.0。"""
        emb = [0.1] * 384
        node = TopicNode(
            name="test", embedding=emb, intent_category="ADVISOR",
            entities=[{"type": "PID", "value": "1234"}],
        )
        result = self.calc.calculate(
            query="test", query_embedding=emb, query_intent="ADVISOR",
            query_entities=[{"type": "PID", "value": "1234"}], target_node=node,
        )
        self.assertAlmostEqual(result.semantic, 1.0, places=2)
        self.assertAlmostEqual(result.entity, 1.0, places=2)
        self.assertAlmostEqual(result.intent, 1.0, places=2)
        self.assertAlmostEqual(result.composite, 1.0, places=2)

    def test_no_match(self):
        """完全不匹配时 cohesion 低。"""
        emb_a = [1.0] + [0.0] * 383
        emb_b = [-1.0] + [0.0] * 383
        node = TopicNode(
            name="A", embedding=emb_b, intent_category="DIRECTIVE",
            entities=[{"type": "PID", "value": "5678"}],
        )
        result = self.calc.calculate(
            query="B", query_embedding=emb_a, query_intent="ADVISOR",
            query_entities=[{"type": "PID", "value": "1234"}], target_node=node,
        )
        self.assertLess(result.composite, 0.5)


class TestTopicDecisionClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = TopicDecisionClassifier()

    def test_continue(self):
        """高 cohesion + 低意图漂移 → continue。"""
        cohesion = CohesionMetrics(semantic=1.0, entity=1.0, intent=1.0, composite=1.0)
        node = TopicNode(name="current", intent_category="ADVISOR")
        decision = self.clf.decide(cohesion, "test", "ADVISOR", node, [])
        self.assertEqual(decision.action, "continue")

    def test_fork(self):
        """低 cohesion + 高意图漂移 → fork。"""
        cohesion = CohesionMetrics(semantic=0.0, entity=0.0, intent=0.0, composite=0.0)
        decision = self.clf.decide(cohesion, "test", "DIRECTIVE", None, [])
        self.assertEqual(decision.action, "fork")


class TestForkPointLocator(unittest.TestCase):
    def setUp(self):
        self.locator = ForkPointLocator()

    def test_locate_with_match(self):
        """有相似节点时返回分叉点。"""
        emb = EmbeddingEngine.encode("hello")
        node = TopicNode(name="n1", embedding=emb, intent_category="ADVISOR")
        result = self.locator.locate("hello", "ADVISOR", emb, [node])
        self.assertEqual(result.node_id, node.id)
        self.assertGreater(result.similarity, 0.0)

    def test_locate_no_match(self):
        """无匹配时返回空。"""
        result = self.locator.locate("xyz", "UNKNOWN", EmbeddingEngine.encode("xyz"), [])
        self.assertEqual(result.node_id, "")
        self.assertTrue(result.intent_drift_detected)


class TestMergeEngine(unittest.TestCase):
    def setUp(self):
        self.calc = CohesionCalculator()
        self.engine = MergeEngine(self.calc)

    def test_lca(self):
        """LCA 查找正确。"""
        root = TopicNode(name="root")
        child_a = TopicNode(name="a", parent_id=root.id)
        child_b = TopicNode(name="b", parent_id=root.id)
        nodes = {root.id: root, child_a.id: child_a, child_b.id: child_b}
        lca = self.engine.find_lca(child_a.id, child_b.id, nodes)
        self.assertEqual(lca, root.id)

    def test_merge_no_conflict(self):
        """无冲突时合并成功。"""
        root = TopicNode(name="root")
        a = TopicNode(name="a", parent_id=root.id, entities=[{"type": "PID", "value": "1"}])
        b = TopicNode(name="b", parent_id=root.id, entities=[{"type": "PID", "value": "1"}])
        nodes = {root.id: root, a.id: a, b.id: b}
        result = self.engine.merge(a.id, b.id, nodes)
        self.assertTrue(result.success)
        self.assertEqual(len(result.conflicts), 0)

    def test_merge_with_conflict(self):
        """有冲突时检测成功。"""
        root = TopicNode(name="root")
        a = TopicNode(name="a", parent_id=root.id, entities=[{"type": "PID", "value": "1"}])
        b = TopicNode(name="b", parent_id=root.id, entities=[{"type": "PID", "value": "2"}])
        nodes = {root.id: root, a.id: a, b.id: b}
        result = self.engine.merge(a.id, b.id, nodes)
        self.assertTrue(result.success)
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0]["entity_type"], "PID")


class TestReactFlowExporter(unittest.TestCase):
    def test_export(self):
        """导出 ReactFlow 格式正确。"""
        root = TopicNode(name="root")
        child = TopicNode(name="child", parent_id=root.id)
        nodes = {root.id: root, child.id: child}
        edges = []
        data = ReactFlowExporter.export(nodes, edges, current_node_id=child.id)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertEqual(len(data["nodes"]), 2)
        # 当前节点标记
        current_nodes = [n for n in data["nodes"] if n["data"].get("is_current")]
        self.assertEqual(len(current_nodes), 1)
        self.assertEqual(current_nodes[0]["id"], child.id)


class TestTopicTreeManagerV2(unittest.TestCase):
    def setUp(self):
        self.mgr = TopicTreeManagerV2()
        self.mgr.activate([])

    def test_route_new(self):
        """首次路由创建新话题。"""
        result = self.mgr.route("hello", turn_index=1, query_intent="COMPANION")
        self.assertEqual(result.action, "new")
        self.assertIsNotNone(result.target_node_id)

    def test_route_continue(self):
        """相似输入继续话题。"""
        self.mgr.route("hello world", turn_index=1, query_intent="ADVISOR")
        result = self.mgr.route("hello again", turn_index=2, query_intent="ADVISOR")
        self.assertEqual(result.action, "continue")

    def test_route_fork(self):
        """完全不同输入分叉。"""
        self.mgr.route("hello world", turn_index=1, query_intent="ADVISOR")
        result = self.mgr.route("分析内存布局 0x7fff", turn_index=2, query_intent="DIRECTIVE")
        self.assertEqual(result.action, "fork")
        self.assertIsNotNone(result.fork_point)

    def test_tree_summary(self):
        """树摘要正确。"""
        self.mgr.route("hello", turn_index=1, query_intent="COMPANION")
        self.mgr.route("world", turn_index=2, query_intent="COMPANION")
        summary = self.mgr.get_tree_summary()
        self.assertEqual(summary["total_nodes"], 1)  # root + 1 continue
        self.assertTrue(summary["is_active"])

    def test_reactflow_export(self):
        """导出 ReactFlow。"""
        self.mgr.route("test", turn_index=1, query_intent="QUERY")
        data = self.mgr.to_reactflow()
        self.assertIn("nodes", data)
        self.assertGreater(len(data["nodes"]), 0)


if __name__ == "__main__":
    unittest.main()
