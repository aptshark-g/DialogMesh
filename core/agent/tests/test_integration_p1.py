# -*- coding: utf-8 -*-
"""
core/agent/tests/test_integration_p1.py
─────────────────────────────────────
P1 端到端集成测试：五层链路验证。

链路：
  用户输入 → CognitiveCompiler.compile(entity_cache) → TopicTreeManager.route(cohesion_score) → WindowManager.add_turn → Persistence.save_turn
"""

import unittest
import time
import tempfile
import os

from core.agent.cognitive_compiler import CognitiveCompiler, CompilerMode, EntityCache
from core.agent.topic_tree import TopicTreeManager, RoutingDecision
from core.agent.context_window import WindowManager, WindowConfig
from core.agent.persistence import CLISessionPersistence, TurnRecord
from core.agent.observability import SessionMetrics, MetricsAggregator, AlertEngine


class TestP1EndToEnd(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.persistence = CLISessionPersistence(db_path=self.db_path)
        self.compiler = CognitiveCompiler(mode=CompilerMode.AUTO)
        self.topic_tree = TopicTreeManager()
        self.window = WindowManager()
        self.entity_cache = EntityCache(max_rounds=5)
        self.metrics = SessionMetrics(session_id="test-sess")
        self.aggregator = MetricsAggregator()
        self.alerts = AlertEngine()
        self._session_history = []

        self.sid = self.persistence.create_session()

    def tearDown(self):
        self.persistence.shutdown()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _turn(self, query: str, turn_index: int):
        """执行一轮完整链路。"""
        # 1. 编译（传入累积历史）
        compiled = self.compiler.compile(
            query, turn_index=turn_index,
            session_history=list(self._session_history),
            entity_cache=self.entity_cache,
        )

        # 2. 话题路由
        entities = self._extract_entities_from_clauses(compiled.clauses)
        decision = self.topic_tree.route(
            query, turn_index, compiled.cohesion_score, entities
        )

        # 3. 窗口管理
        from core.agent.context_window.models import WindowTurn
        turn = WindowTurn(
            sequence=turn_index,
            role="user",
            content=query,
            intent_category=decision.action,
            metadata={
                "cohesion_score": compiled.cohesion_score,
                "topic_action": decision.action,
                "topic_node_id": decision.target_node_id,
                "compiled_query": compiled.query,
            },
        )
        self.window.add_turn(turn)

        # 4. 持久化
        self.persistence.add_turn(
            self.sid, "user", query,
            intent_result={"action": decision.action, "cohesion": compiled.cohesion_score},
            latency_ms=compiled.compilation_time_ms,
        )

        # 5. 观测性
        self.metrics.record_turn(
            confidence=0.8,
            latency_ms=compiled.compilation_time_ms,
            intent=decision.action,
            required_clarification=decision.action == "new",
        )

        # 6. 累积历史（供下一轮 cohesion 计算）
        self._session_history.append({"content": query, "role": "user"})
        self._session_history.append({"content": decision.action, "role": "system"})

        return compiled, decision

    def _extract_entities_from_clauses(self, clauses):
        entities = []
        for c in clauses:
            if c.subject and not c.backfilled:
                entities.append({"value": c.subject, "type": "subject"})
            if c.object:
                entities.append({"value": c.object, "type": "object"})
            if c.backfilled:
                entities.append({"value": c.subject, "type": "backfilled"})
        return entities

    def test_turn1_scan_address(self):
        """第一轮：扫描地址，创建新话题。"""
        compiled, decision = self._turn("scan 0x401000", 1)
        self.assertEqual(decision.action, "new")
        self.assertEqual(compiled.mode_used, "fast")
        self.assertIn("0x401000", compiled.query)
        self.assertEqual(self.topic_tree.get_tree_summary()["total_nodes"], 1)

    def test_turn2_read_backfill(self):
        """Round 2: pronoun 'read that address', triggers backfill."""
        self._turn("scan 0x401000", 1)
        compiled, decision = self._turn("read that address", 2)
        self.assertTrue(any(c.backfilled for c in compiled.clauses), "backfill should have triggered")
        self.assertIn("0x401000", compiled.query)
        self.assertEqual(decision.action, "continue")
        self.assertEqual(self.metrics.total_turns, 2)

    def test_turn3_topic_switch(self):
        """Round 3: topic switch, EntityCache cleared."""
        self._turn("scan 0x401000", 1)
        self._turn("read that address", 2)
        compiled, decision = self._turn("change topic, learn how to hook", 3)
        self.assertIn("topic_switch_cleared", compiled.injected_headers)
        self.assertEqual(decision.action, "fork")
        # turn1 (new node1) + turn2 (continue same node) + turn3 (fork new node2) = 2 nodes
        self.assertEqual(self.topic_tree.get_tree_summary()["total_nodes"], 2)

    def test_turn4_hot_zone_attach(self):
        """Round 4: back to old topic (hot zone match)."""
        self._turn("scan 0x401000", 1)
        self._turn("read that address", 2)
        self._turn("change topic, learn how to hook", 3)
        # Now back to first topic containing 0x401000
        compiled, decision = self._turn("read 0x401000 again", 4)
        # Hot zone match should trigger attach
        self.assertEqual(decision.action, "attach")

    def test_window_slide_and_compression(self):
        """Window slide and compression test."""
        for i in range(25):
            self._turn(f"query {i}", i + 1)
        summary = self.window.get_window_summary()
        self.assertEqual(summary["hot"]["count"], 5)
        self.assertEqual(summary["warm"]["count"], 15)
        self.assertEqual(summary["cold"]["count"], 5)
        self.assertLess(summary["total_tokens"], summary["total_max"] + 500)

    def test_persistence_recovery(self):
        """Persistence recovery test."""
        for i in range(5):
            self._turn(f"query {i}", i + 1)
        self.persistence.close_session(self.sid)
        self.persistence.shutdown()

        # Restart
        new_persistence = CLISessionPersistence(db_path=self.db_path)
        session = new_persistence.get_or_load(self.sid)
        self.assertEqual(session.turn_count, 5)
        new_persistence.shutdown()

    def test_alert_trigger(self):
        """Alert trigger test."""
        # Simulate high clarification rate (100%)
        m = SessionMetrics(session_id="alert-test")
        for i in range(10):
            m.record_turn(
                confidence=0.3, latency_ms=100.0,
                intent="unknown", required_clarification=True,
            )
        alerts = self.alerts.check_session_metrics(m.get_summary())
        self.assertGreater(len(alerts), 0)
        # 100% clarification triggers CRITICAL, not WARNING
        self.assertEqual(alerts[0].severity.value, "critical")

    def test_metrics_aggregator(self):
        """指标聚合器测试。"""
        for i in range(3):
            m = self.aggregator.get_or_create(f"sess-{i}")
            for j in range(5):
                m.record_turn(
                    confidence=0.8, latency_ms=15.0, intent="scan_memory"
                )
        summary = self.aggregator.get_global_summary()
        self.assertEqual(summary["sessions"], 3)
        self.assertEqual(summary["total_turns"], 15)

    def test_topic_tree_depth_compression(self):
        """话题树深度压缩测试。"""
        # 快速创建 8 层深度
        parent = None
        for i in range(8):
            node = self.topic_tree._create_node(
                name=f"level-{i}", parent_id=parent,
                entities=[{"value": f"v{i}", "type": "test"}]
            )
            parent = node.id

        self.topic_tree._current_node_id = parent
        self.topic_tree._check_depth_and_compress(parent)

        # 检查深度是否被压缩到 <= 6
        summary = self.topic_tree.get_tree_summary()
        self.assertLessEqual(summary["max_depth"], 6)


if __name__ == "__main__":
    unittest.main()
