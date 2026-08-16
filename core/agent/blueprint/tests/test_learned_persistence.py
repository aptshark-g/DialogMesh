# -*- coding: utf-8 -*-
"""学习闭环持久化 + 二阶抽象（可逆推验证）测试（2026-08-16）。

背景: LEARNED_TEMPLATES 此前纯内存, 学到即丢 —— "工作流自增长"核心闭环
断。本文件固化:
  1. DAG 序列化 round-trip
  2. learn → 落盘 → 重启恢复 → match 命中（闭环接通）
  3. A24 二阶抽象: coverage 60-80% 可逆推验证（<60% 没学到, >80% 过拟合）
  4. 无 tool 节点 DAG 不学习
"""
from __future__ import annotations

import os
import tempfile
import unittest

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)


def _tool_dag(tool: str = "grep", n_tools: int = 1) -> BlueprintDAG:
    tools = [BlueprintNode(f"tool_{i}", "tool", priority=1,
                           params={"tool": tool})
             for i in range(n_tools)]
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("intent_1", "intent", priority=0),
            *tools,
            BlueprintNode("llm_reply_x", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "intent_1", "route", required=False),
            BlueprintEdge("intent_1", tools[0].node_id, "intent_context"),
        ],
        strategy="TEMPLATE",
        design_rationale="test-dag",
    )


class TestDAGSerialization(unittest.TestCase):
    def test_roundtrip_preserves_all(self):
        dag = _tool_dag(tool="echo", n_tools=2)
        d = dag.to_dict()
        dag2 = BlueprintDAG.from_dict(d)
        self.assertEqual(dag2.node_count, dag.node_count)
        self.assertEqual(len(dag2.edges), len(dag.edges))
        self.assertEqual(dag2.strategy, "TEMPLATE")
        self.assertEqual(dag2.design_rationale, "test-dag")
        tools2 = [n for n in dag2.nodes if n.chain == "tool"]
        self.assertEqual(tools2[0].params["tool"], "echo")


class TestLearnedPersistence(unittest.TestCase):
    def setUp(self):
        from core.agent.blueprint import skill_registry as sr
        self.sr = sr
        self._old_path = os.environ.get("DM_LEARNED_TEMPLATES_PATH", "")
        self._tmp = tempfile.mkdtemp(prefix="dm_learned_")
        self._path = os.path.join(self._tmp, "learned_templates.json")
        os.environ["DM_LEARNED_TEMPLATES_PATH"] = self._path
        self._saved = dict(sr.LEARNED_TEMPLATES)
        sr.LEARNED_TEMPLATES.clear()

    def tearDown(self):
        self.sr.LEARNED_TEMPLATES.clear()
        self.sr.LEARNED_TEMPLATES.update(self._saved)
        if self._old_path:
            os.environ["DM_LEARNED_TEMPLATES_PATH"] = self._old_path
        else:
            os.environ.pop("DM_LEARNED_TEMPLATES_PATH", None)

    def test_learn_persists_and_restore_matches(self):
        reg = self.sr.SkillRegistry()
        dag = _tool_dag(tool="grep")
        self.assertTrue(reg.learn_blueprint("任务规划", dag, source_dag_id="x1"))
        self.assertTrue(os.path.exists(self._path))  # 落盘
        # 模拟重启: 清空 → 从盘恢复
        self.sr.LEARNED_TEMPLATES.clear()
        self.sr._load_learned_templates()
        self.assertIn("任务规划", self.sr.LEARNED_TEMPLATES)
        restored = self.sr.LEARNED_TEMPLATES["任务规划"]
        self.assertEqual(restored.node_count, dag.node_count)
        # 恢复后 match 命中（TEMPLATE 策略, LEARNED 优先）
        strategy, bp = reg.match("任务规划")
        self.assertEqual(strategy, "TEMPLATE")
        self.assertIn("grep", [n.params.get("tool")
                               for n in bp.nodes if n.chain == "tool"])

    def test_no_tool_dag_not_learned(self):
        reg = self.sr.SkillRegistry()
        plain = BlueprintDAG(
            nodes=[
                BlueprintNode("pcr_0", "pcr", priority=0),
                BlueprintNode("llm_reply_x", "llm_reply", priority=2),
            ],
            edges=[], strategy="TEMPLATE")
        self.assertFalse(reg.learn_blueprint("通用对话", plain))
        self.assertFalse(os.path.exists(self._path))


class TestA24Reversible(unittest.TestCase):
    """二阶抽象 = 逆推验证（coverage 60-80%, 100%=过拟合 0%=没学到）。"""

    def _verify(self, pattern_actions, seqs):
        from core.agent.blueprint.learning_bridge import LearningBridge

        class _A:
            def __init__(self, a):
                self.action = a

        class _Cand:
            def __init__(self, actions):
                self.blueprint = type("BP", (), {
                    "action_graph": [_A(a) for a in actions]})()

        class _Tr:
            def __init__(self, seq):
                self.tool_sequence = seq

        cand = _Cand(pattern_actions)
        traces = [_Tr(s) for s in seqs]
        return LearningBridge._a24_verify(cand, traces)

    def test_coverage_in_60_80_passes(self):
        # 5 条轨迹 3 条含 [grep, read] → coverage 0.6 → 达标
        seqs = [["grep", "read"], ["grep", "read"], ["grep", "read"],
                ["other"], ["other"]]
        self.assertTrue(self._verify(["grep", "read"], seqs))

    def test_below_60_not_learned(self):
        seqs = [["grep", "read"], ["other"], ["other"], ["other"], ["other"]]
        self.assertFalse(self._verify(["grep", "read"], seqs))

    def test_above_80_is_overfit(self):
        seqs = [["grep", "read"], ["grep", "read"], ["grep", "read"]]
        self.assertFalse(self._verify(["grep", "read"], seqs))


if __name__ == "__main__":
    unittest.main()
