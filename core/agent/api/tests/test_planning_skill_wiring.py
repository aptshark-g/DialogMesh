# -*- coding: utf-8 -*-
"""PlanningSkill 第二规划通道接线测试（2026-08-16）。

覆盖:
  1. TaskGraph_v3 → 拓扑步骤 / 前端图转换（纯函数）
  2. 规则骨架（forced RULE_BASED, 零 LLM）产出通用任务步骤
  3. _plan_with_skill 全链路（mock PlanningSkill.plan, 不碰网关）
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from core.agent.api.v3_session_api import (
    _plan_with_skill,
    _taskgraph_to_frontend,
    _taskgraph_topological_steps,
)
from core.agent.v3_legacy.data_models import (
    Intent_v3,
    TaskEdge_v3,
    TaskGraph_v3,
    TaskNode_v3,
)
from core.agent.v3_common.models import DependencyType, IntentCategory
from core.agent.planner.models import PlanResult, PlanStrategy


def _graph_with_edges() -> TaskGraph_v3:
    tg = TaskGraph_v3()
    a = TaskNode_v3(name="alpha", goal="第一步")
    b = TaskNode_v3(name="beta", goal="第二步")
    c = TaskNode_v3(name="gamma", goal="第三步")
    for n in (a, b, c):
        tg.add_node(n)
    tg.add_edge(TaskEdge_v3(
        source_id=a.id, target_id=b.id,
        dep_type=DependencyType.SEQUENTIAL))
    tg.add_edge(TaskEdge_v3(
        source_id=b.id, target_id=c.id,
        dep_type=DependencyType.SEQUENTIAL))
    return tg


class TestTaskGraphConversions(unittest.TestCase):
    """纯函数: TaskGraph_v3 → 步骤/前端图。"""

    def test_topological_steps_respect_dependencies(self):
        tg = _graph_with_edges()
        steps = _taskgraph_topological_steps(tg)
        self.assertEqual(steps, ["alpha", "beta", "gamma"])

    def test_cycle_does_not_hang(self):
        tg = TaskGraph_v3()
        a = TaskNode_v3(name="a")
        b = TaskNode_v3(name="b")
        for n in (a, b):
            tg.add_node(n)
        tg.add_edge(TaskEdge_v3(
            source_id=a.id, target_id=b.id,
            dep_type=DependencyType.SEQUENTIAL))
        tg.add_edge(TaskEdge_v3(
            source_id=b.id, target_id=a.id,
            dep_type=DependencyType.SEQUENTIAL))
        steps = _taskgraph_topological_steps(tg)
        self.assertEqual(sorted(steps), ["a", "b"])

    def test_frontend_format(self):
        tg = _graph_with_edges()
        front = _taskgraph_to_frontend(tg)
        self.assertEqual(len(front), 3)
        by_name = {f["name"]: f for f in front}
        self.assertEqual(by_name["alpha"]["dependencies"], [])
        self.assertEqual(by_name["beta"]["dependencies"],
                         [next(n.id for n in tg.nodes.values()
                               if n.name == "alpha")])
        self.assertEqual(by_name["gamma"]["type"], "plan")


class TestPlanningSkillRuleSkeleton(unittest.TestCase):
    """规则骨架（零 LLM）: 通用任务模板产出真实步骤。"""

    def test_task_planning_skeleton(self):
        from core.agent.planner.planner import PlanningSkill
        intent = Intent_v3(
            raw_input="做一个五子棋游戏",
            category=IntentCategory.UNKNOWN,
            metadata={"intent_label": "task_planning"},
        )
        planner = PlanningSkill(llm_provider=None)
        result = asyncio.run(planner.plan(
            intent, forced_strategy=PlanStrategy.RULE_BASED))
        self.assertTrue(result.success)
        steps = _taskgraph_topological_steps(result.task_graph)
        self.assertIn("read_input", steps)
        self.assertIn("design_plan", steps)
        self.assertIn("implement", steps)
        self.assertIn("verify", steps)
        self.assertIn("report", steps)
        # 依赖序: implement 在 design_plan 之后
        self.assertLess(steps.index("design_plan"),
                        steps.index("implement"))

    def test_recall_skeleton(self):
        from core.agent.planner.planner import PlanningSkill
        intent = Intent_v3(
            raw_input="查一下上次聊的架构",
            category=IntentCategory.UNKNOWN,
            metadata={"intent_label": "recall"},
        )
        planner = PlanningSkill(llm_provider=None)
        result = asyncio.run(planner.plan(
            intent, forced_strategy=PlanStrategy.RULE_BASED))
        self.assertTrue(result.success)
        steps = _taskgraph_topological_steps(result.task_graph)
        self.assertEqual(steps[0], "recall")
        self.assertEqual(steps[1], "expand")
        self.assertEqual(steps[2], "report")


class TestPlanWithSkill(unittest.TestCase):
    """_plan_with_skill 全链路（mock PlanningSkill.plan, 不碰网关）。"""

    def test_returns_steps_and_frontend(self):
        tg = _graph_with_edges()
        fake_result = PlanResult(intent_id="x")
        fake_result.success = True
        fake_result.task_graph = tg
        with mock.patch(
                "core.agent.planner.planner.PlanningSkill.plan",
                new=mock.AsyncMock(return_value=fake_result)):
            steps, front = asyncio.run(
                _plan_with_skill("做个东西", "task_planning"))
        self.assertEqual(steps, ["alpha", "beta", "gamma"])
        self.assertEqual(len(front), 3)

    def test_failure_returns_none_none(self):
        fake_result = PlanResult(intent_id="x")
        fake_result.success = False
        fake_result.error = "boom"
        with mock.patch(
                "core.agent.planner.planner.PlanningSkill.plan",
                new=mock.AsyncMock(return_value=fake_result)):
            steps, front = asyncio.run(
                _plan_with_skill("做个东西", "task_planning"))
        self.assertIsNone(steps)
        self.assertIsNone(front)

    def test_exception_returns_none_none(self):
        with mock.patch(
                "core.agent.planner.planner.PlanningSkill.plan",
                new=mock.AsyncMock(side_effect=RuntimeError("no gateway"))):
            steps, front = asyncio.run(
                _plan_with_skill("做个东西", "task_planning"))
        self.assertIsNone(steps)
        self.assertIsNone(front)


if __name__ == "__main__":
    unittest.main()
