# -*- coding: utf-8 -*-
"""执行树生产接线测试（2026-08-15, P0 修复）。

背景: v3_session_api / statemachine 此前从 ``_discourse_tree._trees[sid]``
取 ``execution`` 属性 —— DiscourseBlockTreeManager 无该属性, 生产路径
执行树恒 None, 落树与消费从未生效（只有直接构造 AgentTreeManager 的
单元测试是绿的）。修复: engine 新增 per-session 七树容器
``get_agent_tree()``, 本测试钉死生产接线闭环:

  engine.get_agent_tree(sid).execution
    → TaskRunner(execution_tree=...) 落树（create_task/spawn/complete）
    → engine._consume_execution_tree(sid) 消费（不再 no_exec_tree）
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm.task_runner import TaskRunner, TaskConstraint
from core.agent.execution.tree_manager import AgentTreeManager


class FakeLLMLoop:
    """tool_loop 替身: 一次工具调用 + 最终回答（结构对齐真实返回）。"""

    def __init__(self, steps=1):
        self._steps = steps
        self._called = 0
        self._step_hooks = []

    def __call__(self, messages, model="", max_rounds=6,
                 allowed_tools=None, system_inject="", on_step=None,
                 timeout_s=120.0, symbol_interval=0, symbol_keep_last=2):
        self._called += 1
        if on_step is not None:
            on_step({
                "round": 0, "tool": "run_shell", "ok": True,
                "args": "echo hello", "input": "echo hello",
                "summary": "run echo", "latency_ms": 1.0,
            })
        return {
            "content": "任务完成",
            "tool_calls": [{"name": "run_shell", "ok": True}],
            "trace": [{"round": 0, "tool": "run_shell", "ok": True}],
            "rounds": 1,
            "error": "",
        }


class _IsolatedTreesMixin:
    """七树落盘隔离: 每测试用临时目录, 防跨测试/跨运行恢复污染。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="dm_agent_trees_")
        self._old_env = os.environ.get("DM_AGENT_TREES_DIR")
        os.environ["DM_AGENT_TREES_DIR"] = self._tmp

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("DM_AGENT_TREES_DIR", None)
        else:
            os.environ["DM_AGENT_TREES_DIR"] = self._old_env
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestExecutionTreeProductionWiring(_IsolatedTreesMixin, unittest.TestCase):
    """生产接线: engine 七树容器 → TaskRunner 落树 → 元认知消费。"""

    def test_get_agent_tree_lazy_per_session(self):
        eng = CognitiveRuntimeEngine()
        a = eng.get_agent_tree("s1")
        b = eng.get_agent_tree("s1")
        c = eng.get_agent_tree("s2")
        self.assertIs(a, b)          # 同会话同实例
        self.assertIsNot(a, c)       # 跨会话隔离
        self.assertIsNotNone(a.execution)
        self.assertIsNotNone(a.behavior)
        self.assertIsNotNone(a.meta)
        # 生产取树路径（v3_session_api 同款写法）不再恒 None
        exec_tree = getattr(eng.get_agent_tree("s1"), "execution", None)
        self.assertIsNotNone(exec_tree)

    def test_task_runner_lands_execution_tree(self):
        eng = CognitiveRuntimeEngine()
        exec_tree = eng.get_agent_tree("s1").execution
        runner = TaskRunner(
            decision_bus=None,
            execution_tree=exec_tree,
            llm_loop=FakeLLMLoop(),
        )
        result = runner.run(
            goal="测试任务",
            constraint=TaskConstraint(goal="测试任务"),
            node_id="n1", session_id="s1",
        )
        self.assertEqual(result.status, "ok")
        nodes = list(exec_tree._nodes.values())
        # create_task(1) + spawn(1) + complete 后仍在节点表中
        self.assertGreaterEqual(len(nodes), 2)
        # 收尾: 根任务节点已 COMPLETED, 含结果摘要
        roots = [n for n in nodes if not n.parent_id]
        self.assertEqual(len(roots), 1)
        root = roots[0]
        self.assertEqual(root.status.value, "completed")
        result = root.content.get("result") or {}
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("tools"), ["run_shell"])

    def test_consume_execution_tree_production_path(self):
        eng = CognitiveRuntimeEngine()
        runner = TaskRunner(
            decision_bus=None,
            execution_tree=eng.get_agent_tree("s1").execution,
            llm_loop=FakeLLMLoop(),
        )
        runner.run(
            goal="测试任务",
            constraint=TaskConstraint(goal="测试任务"),
            node_id="n1", session_id="s1",
        )
        out = eng._consume_execution_tree("s1", force=True)
        self.assertTrue(out.get("consumed"), out)
        self.assertNotEqual(out.get("reason"), "no_exec_tree")
        self.assertIn("audit_events", out)
        self.assertIn("patterns", out)

    def test_empty_tree_consume_is_noop(self):
        eng = CognitiveRuntimeEngine()
        out = eng._consume_execution_tree("empty_sid", force=True)
        # 空树也走真消费器（不因取树失败返回 no_exec_tree）
        self.assertTrue(out.get("consumed"), out)
        self.assertEqual(out.get("audit_events"), 0)


class TestSevenTreePersistenceAndConsumption(
        _IsolatedTreesMixin, unittest.TestCase):
    """七树持久化 + 消费接线（2026-08-15 后端闭环）。"""

    def _run_task(self, eng, sid="sx"):
        runner = TaskRunner(
            decision_bus=None,
            execution_tree=eng.get_agent_tree(sid).execution,
            llm_loop=FakeLLMLoop(),
        )
        return runner.run(
            goal="测试任务",
            constraint=TaskConstraint(goal="测试任务"),
            node_id="n1", session_id=sid,
        )

    def test_manager_roundtrip(self):
        path = os.path.join(self._tmp, "mgr.json")
        mgr = AgentTreeManager()
        t = mgr.execution.create_task(
            {"steps": ["s"], "strategy": "TOOL_LOOP"})
        mgr.execution.spawn_sub_agent(t.node_id, "run_shell: x",
                                      context_size=0)
        mgr.execution.complete_node(t.node_id, {"status": "ok"})
        mgr.behavior.record_pattern("run_shell", approved=True, risk="low")
        mgr.meta.record_decision("audit", {}, "pass", "ok")
        self.assertTrue(mgr.save(path))
        restored = AgentTreeManager.load(path)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.execution.node_count(), 2)
        self.assertEqual(restored.behavior.node_count(), 1)
        self.assertEqual(restored.meta.node_count(), 1)
        root = [n for n in restored.execution._nodes.values()
                if not n.parent_id][0]
        self.assertEqual(root.status.value, "completed")
        self.assertEqual(root.content["result"]["status"], "ok")

    def test_engine_persist_and_restore(self):
        eng1 = CognitiveRuntimeEngine()
        self._run_task(eng1, sid="persist_sid")
        self.assertTrue(eng1._persist_agent_tree("persist_sid", force=True))
        path = eng1._agent_tree_path("persist_sid")
        self.assertTrue(os.path.exists(path))
        # 新引擎实例（模拟重启）→ Warm→Hot 恢复
        eng2 = CognitiveRuntimeEngine()
        restored = eng2.get_agent_tree("persist_sid").execution
        self.assertEqual(restored.node_count(), 2)
        self.assertGreaterEqual(
            len(eng2.query_agent_trees("run_shell", "persist_sid")), 1)

    def test_consume_writes_seven_trees_and_persists(self):
        eng = CognitiveRuntimeEngine()
        mgr = eng.get_agent_tree("consume_sid")
        # 造 doom loop 树（同工具同输入连续 3 次失败 → 偏差事件）
        tree = mgr.execution
        t = tree.create_task(
            {"steps": ["x"], "strategy": "TOOL_LOOP"})
        for i in range(3):
            n = tree.spawn_sub_agent(
                t.node_id, f"run_shell: 第{i}步", context_size=0)
            n.content["outcome"] = "error"
            n.content["input"] = '{"command": "ping x"}'
        tree.complete_node(t.node_id, {"status": "error"})
        out = eng._consume_execution_tree("consume_sid", force=True)
        self.assertTrue(out.get("consumed"), out)
        self.assertGreaterEqual(out.get("audit_events"), 1)
        self.assertGreater(out.get("tree_writes", {}).get("meta", 0), 0)
        self.assertGreater(out.get("tree_writes", {}).get("behavior", 0), 0)
        # audit 事件（text_only 等）→ meta 树
        self.assertGreater(mgr.meta.node_count(), 0)
        # 执行任务 → 关联树映射
        self.assertGreater(mgr.association.node_count(), 0)
        # 消费后立即落盘
        self.assertTrue(os.path.exists(
            eng._agent_tree_path("consume_sid")))
        # 联邦查询跨树命中（meta 节点含 exec_tree_audit 关键字）
        hits = eng.query_agent_trees("exec_tree_audit", "consume_sid")
        self.assertGreaterEqual(len(hits), 1)

    def test_task_runner_steps_land_in_tree_and_inject(self):
        eng = CognitiveRuntimeEngine()
        exec_tree = eng.get_agent_tree("steps_sid").execution
        runner = TaskRunner(
            decision_bus=None, execution_tree=exec_tree,
            llm_loop=FakeLLMLoop(),
        )
        steps = ["读取需求", "编写代码", "运行测试"]
        constraint = TaskConstraint(goal="实现功能", steps=steps)
        inject = TaskRunner.build_inject(constraint)
        self.assertIn("任务步骤地图", inject)
        self.assertIn("1. 读取需求", inject)
        self.assertIn("3. 运行测试", inject)
        result = runner.run(
            goal="实现功能", constraint=constraint,
            node_id="n1", session_id="steps_sid",
        )
        self.assertEqual(result.status, "ok")
        root = [n for n in exec_tree._nodes.values()
                if not n.parent_id][0]
        self.assertEqual(root.content["steps"], steps)

    def test_cross_session_federation_query(self):
        eng = CognitiveRuntimeEngine()
        # 两个会话各落不同内容
        for sid, goal in (("agg_a", "任务甲"), ("agg_b", "任务乙")):
            runner = TaskRunner(
                decision_bus=None,
                execution_tree=eng.get_agent_tree(sid).execution,
                llm_loop=FakeLLMLoop(),
            )
            runner.run(
                goal=goal,
                constraint=TaskConstraint(goal=goal),
                node_id="n1", session_id=sid,
            )
            eng._persist_agent_tree(sid, force=True)
        # 聚合统计: 两会话都在
        sessions = eng.agent_tree_sessions()
        self.assertEqual(len(sessions), 2)
        # 跨会话联邦查询命中
        hits = eng.query_all_agent_trees("run_shell")
        self.assertGreaterEqual(len(hits), 2)
        sids = {h["session_id"] for h in hits}
        self.assertTrue({"agg_a", "agg_b"} <= sids)

    def test_federation_scans_disk_only_sessions(self):
        eng1 = CognitiveRuntimeEngine()
        runner = TaskRunner(
            decision_bus=None,
            execution_tree=eng1.get_agent_tree("disk_only").execution,
            llm_loop=FakeLLMLoop(),
        )
        runner.run(
            goal="盘上会话任务",
            constraint=TaskConstraint(goal="盘上会话任务"),
            node_id="n1", session_id="disk_only",
        )
        self.assertTrue(eng1._persist_agent_tree("disk_only", force=True))
        # 新引擎（模拟重启, 未加载该会话）→ 只扫盘
        eng2 = CognitiveRuntimeEngine()
        hits = eng2.query_all_agent_trees("run_shell")
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["session_id"], "disk_only")
        sessions = eng2.agent_tree_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertFalse(sessions[0]["loaded"])


if __name__ == "__main__":
    unittest.main()
