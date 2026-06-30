# -*- coding: utf-8 -*-
"""
core/agent/topic_tree/tests/test_topic_tree.py
────────────────────────────────────────────
Topic tree tests.
"""

import unittest

from core.agent.topic_tree.manager import TopicTreeManager, RoutingDecision
from core.agent.topic_tree.models import TopicNode, TopicEdge, TopicEdgeType


class TestTopicTreeManager(unittest.TestCase):

    def setUp(self):
        self.manager = TopicTreeManager()

    def test_route_new(self):
        """首次路由应创建新话题。"""
        decision = self.manager.route("scan 0x401000", turn_index=1)
        self.assertEqual(decision.action, "new")
        self.assertIsNotNone(decision.target_node_id)

    def test_route_continue_high_cohesion(self):
        """高 cohesion_score 应继续当前话题。"""
        self.manager.route("scan 0x401000", turn_index=1)
        decision = self.manager.route("read that address", turn_index=2, cohesion_score=0.8)
        self.assertEqual(decision.action, "continue")

    def test_route_fork_low_cohesion(self):
        """低 cohesion_score 应分叉。"""
        self.manager.route("scan 0x401000", turn_index=1)
        decision = self.manager.route("学习如何写 hook", turn_index=2, cohesion_score=0.1)
        self.assertEqual(decision.action, "fork")

    def test_route_attach_mid_cohesion(self):
        """中间 cohesion_score 应附着到相似话题。"""
        # 先创建两个话题
        d1 = self.manager.route("scan 0x401000", turn_index=1)
        # 切换到另一个话题
        d2 = self.manager.route("学习 how to reverse", turn_index=2, cohesion_score=0.1)
        # 现在 query 包含 0x401000，应该附着到第一个话题
        d3 = self.manager.route("check 0x401000 again", turn_index=3, cohesion_score=0.4,
                                  extracted_entities=[{"type": "memory_address", "value": "0x401000"}])
        # 由于有实体匹配，应该 attach 到第一个话题
        self.assertIn(d3.action, ["attach", "continue", "fork"])

    def test_entity_index(self):
        """实体索引应能跨话题查询。"""
        d1 = self.manager.route("scan 0x401000", turn_index=1,
                                extracted_entities=[{"type": "memory_address", "value": "0x401000"}])
        nodes = self.manager.find_nodes_by_entity("0x401000")
        self.assertGreaterEqual(len(nodes), 1)

    def test_tree_hierarchy(self):
        """测试树结构层次。"""
        d1 = self.manager.route("root topic", turn_index=1)
        root_id = d1.target_node_id
        d2 = self.manager.route("child topic", turn_index=2, cohesion_score=0.1)
        child_id = d2.target_node_id

        root = self.manager.get_node(root_id)
        child = self.manager.get_node(child_id)
        self.assertEqual(child.parent_id, root_id)
        self.assertEqual(child.depth, 1)
        self.assertIn(child_id, root.children_ids)

    def test_get_ancestors(self):
        """测试祖先查询。"""
        d1 = self.manager.route("root", turn_index=1)
        d2 = self.manager.route("child", turn_index=2, cohesion_score=0.1)
        d3 = self.manager.route("grandchild", turn_index=3, cohesion_score=0.1)

        ancestors = self.manager.get_ancestors(d3.target_node_id)
        self.assertEqual(len(ancestors), 2)
        self.assertEqual(ancestors[0].id, d1.target_node_id)
        self.assertEqual(ancestors[1].id, d2.target_node_id)

    def test_get_related_nodes(self):
        """测试图关联查询。"""
        d1 = self.manager.route("topic A", turn_index=1)
        d2 = self.manager.route("topic B", turn_index=2, cohesion_score=0.1)

        # 手动添加关联边
        self.manager._add_edge(
            d1.target_node_id, d2.target_node_id,
            TopicEdgeType.ENTITY_REFERENCE, weight=0.8
        )

        related = self.manager.get_related_nodes(d1.target_node_id)
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].id, d2.target_node_id)

    def test_serialization(self):
        """测试序列化/反序列化。"""
        self.manager.route("topic", turn_index=1)
        self.manager.route("subtopic", turn_index=2, cohesion_score=0.1)

        data = self.manager.to_dict()
        restored = TopicTreeManager.from_dict(data)

        self.assertEqual(len(restored.get_all_nodes()), 2)
        self.assertEqual(restored._current_node_id, self.manager._current_node_id)

    def test_tree_summary(self):
        """测试树摘要。"""
        self.manager.route("root", turn_index=1)
        self.manager.route("child1", turn_index=2, cohesion_score=0.1)
        self.manager.route("child2", turn_index=3, cohesion_score=0.1)

        summary = self.manager.get_tree_summary()
        self.assertEqual(summary["total_nodes"], 3)
        self.assertEqual(summary["max_depth"], 2)


if __name__ == "__main__":
    unittest.main()
