# -*- coding: utf-8 -*-
"""执行树消费端测试（2026-08-14, 吸收 Grok/OpenCode/OpenClaw 实现纪律）。

覆盖: tree_patterns 模式提取（结果词汇化 / doom loop 同输入判定 /
卡 ACTIVE / 纯文本回合 / 深度信号）; 阶段 2/3 消费器测试后续追加。
"""
from __future__ import annotations

import time

from core.agent.execution.tree_manager import (
    AgentTreeNode, ExecutionTree, NodeStatus)


def _task(tree: ExecutionTree, steps=None, status=None):
    """造一个任务节点 + 可选步骤（每步可带 outcome/input）。"""
    t = tree.create_task({"steps": ["目标"], "strategy": "TOOL_LOOP"})
    if status:
        t.status = status
    for i, step in enumerate(steps or []):
        n = tree.spawn_sub_agent(
            t.node_id, task=f"{step['tool']}: 第{i}步",
            context_size=0, pointers=[f"trace:{i}"])
        n.content["outcome"] = step.get("outcome", "success")
        n.content["input"] = step.get("input", "")
    if status == NodeStatus.COMPLETED:
        tree.complete_node(t.node_id, {"status": "ok", "tools": [
            s["tool"] for s in (steps or [])]})
    return t


class TestTreePatterns:
    def test_outcomes_and_sequences(self):
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "write_file", "outcome": "success"},
            {"tool": "run_python", "outcome": "error"},
        ], status=NodeStatus.COMPLETED)
        p = tree.tree_patterns()
        assert p["tasks"] == 1 and p["completed"] == 1
        assert p["tool_outcomes"]["write_file"] == {
            "success": 1, "error": 0, "cancelled": 0}
        assert p["tool_outcomes"]["run_python"] == {
            "success": 0, "error": 1, "cancelled": 0}
        assert p["tool_sequences"] == [["write_file", "run_python"]]
        assert p["avg_steps_per_task"] == 2.0

    def test_doom_loop_same_tool_same_input(self):
        """吸收 O3: 同工具+同输入连续 3 次 = doom loop（输入不变才是死循环）"""
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            {"tool": "run_shell", "input": '{"command": "ping y"}'},
        ], status=NodeStatus.COMPLETED)
        p = tree.tree_patterns()
        assert len(p["doom_loops"]) == 1
        assert p["doom_loops"][0]["tool"] == "run_shell"
        assert 'ping x' in p["doom_loops"][0]["input"]

    def test_same_tool_diff_input_not_doom(self):
        """同工具但输入不同 = 不是死循环（吸收 O3 的关键区别）"""
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "run_shell", "input": '{"command": "a"}'},
            {"tool": "run_shell", "input": '{"command": "b"}'},
            {"tool": "run_shell", "input": '{"command": "c"}'},
        ], status=NodeStatus.COMPLETED)
        assert tree.tree_patterns()["doom_loops"] == []

    def test_failing_tools_and_consecutive_failures(self):
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "grep", "outcome": "error"},
            {"tool": "grep", "outcome": "error"},
            {"tool": "write_file", "outcome": "success"},
            {"tool": "grep", "outcome": "success"},
        ], status=NodeStatus.COMPLETED)
        p = tree.tree_patterns()
        assert "grep" in p["failing_tools"]
        assert p["consecutive_failures"] == [2]

    def test_stuck_active_and_text_only(self):
        tree = ExecutionTree()
        # 卡 ACTIVE: 创建于 10 分钟前仍未完成
        stuck = tree.create_task({"steps": ["旧任务"], "strategy": "TOOL_LOOP"})
        stuck.created_at = time.time() - 600
        # 纯文本回合: 完成但无步骤
        text = tree.create_task({"steps": ["纯文本"], "strategy": "TOOL_LOOP"})
        tree.complete_node(text.node_id, {"status": "ok", "tools": []})
        p = tree.tree_patterns()
        assert p["stuck_active"] == 1
        assert p["text_only"] == 1


class TestMetaTreeConsumer:
    """阶段 2: 元认知消费器 — 检测不介入, audit 事件 schema 化。"""

    def test_doom_loop_emits_audit_event(self):
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "run_shell", "input": '{"command": "x"}'},
            {"tool": "run_shell", "input": '{"command": "x"}'},
            {"tool": "run_shell", "input": '{"command": "x"}'},
        ], status=NodeStatus.COMPLETED)
        from core.agent.execution.tree_consumers import MetaTreeConsumer
        c = MetaTreeConsumer(min_interval=0)
        r = c.consume(tree, session_id="s1", force=True)
        kinds = [e["signal"] for e in r["events"]]
        assert "doom_loop" in kinds
        ev = next(e for e in r["events"] if e["signal"] == "doom_loop")
        assert ev["kind"] == "exec_tree_audit"
        assert ev["dimension"] == "exec_tree.doom_loop"
        assert ev["payload"]["tool"] == "run_shell"

    def test_interval_gate_skips(self):
        from core.agent.execution.tree_consumers import MetaTreeConsumer
        tree = ExecutionTree()
        c = MetaTreeConsumer(min_interval=3600)
        r1 = c.consume(tree, force=True)
        r2 = c.consume(tree)
        assert not r1.get("skipped")
        assert r2.get("skipped") and r2["reason"] == "interval"

    def test_audit_events_via_bus(self):
        """审计事件走决策总线（kind=exec_tree_audit 已入 VALID_KINDS）"""
        from core.agent.blueprint.decision_event import (
            DecisionEventBus, VALID_KINDS)
        assert "exec_tree_audit" in VALID_KINDS
        bus = DecisionEventBus()
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "grep", "outcome": "error", "input": "a"},
            {"tool": "grep", "outcome": "error", "input": "a"},
            {"tool": "grep", "outcome": "error", "input": "a"},
        ], status=NodeStatus.COMPLETED)
        from core.agent.execution.tree_consumers import MetaTreeConsumer
        c = MetaTreeConsumer(bus=bus, min_interval=0)
        r = c.consume(tree, session_id="s1", force=True)
        assert r["events"], "应有 audit 事件"
        mem = [e for e in bus._memory if e.get("kind") == "exec_tree_audit"]
        assert mem, "audit 事件应进总线内存"


class TestExecutionPatternStore:
    """阶段 3: 执行模式沉淀（dream 门控, 不碰 BehaviorBrain 用户模型）"""

    def test_accumulate_and_persist(self, tmp_path):
        from core.agent.execution.tree_consumers import ExecutionPatternStore
        store = ExecutionPatternStore(
            path=str(tmp_path / "patterns.json"), min_interval=0)
        tree = ExecutionTree()
        _task(tree, steps=[
            {"tool": "write_file", "outcome": "success", "input": "a"},
            {"tool": "run_python", "outcome": "success", "input": "b"},
        ], status=NodeStatus.COMPLETED)
        r = store.consume(tree, session_id="s1", force=True)
        assert not r.get("skipped")
        assert r["patterns"]["tasks"] == 1
        assert r["patterns"]["tool_stats"]["write_file"]["uses"] == 1
        assert r["patterns"]["tool_stats"]["run_python"]["uses"] == 1
        # 持久化: 新实例加载同一文件
        store2 = ExecutionPatternStore(
            path=str(tmp_path / "patterns.json"), min_interval=0)
        assert store2.stats()["tasks"] == 1
        assert "write_file" in store2.stats()["tool_stats"]

    def test_interval_gate(self, tmp_path):
        from core.agent.execution.tree_consumers import ExecutionPatternStore
        store = ExecutionPatternStore(
            path=str(tmp_path / "p.json"), min_interval=3600)
        tree = ExecutionTree()
        _task(tree, steps=[{"tool": "grep", "input": "x"}],
              status=NodeStatus.COMPLETED)
        assert store.consume(tree, force=True).get("skipped") is not True
        r2 = store.consume(tree)
        assert r2.get("skipped") and r2["reason"] == "interval"


class TestExecutionSummary:
    """阶段 4: 执行摘要三策略（mechanical/llm/hybrid）+ 只读验证。"""

    def _tree_with_task(self):
        tree = ExecutionTree()
        t = _task(tree, steps=[
            {"tool": "write_file", "outcome": "success",
             "input": '{"path": "hello.py"}'},
            {"tool": "run_python", "outcome": "success",
             "input": '{"command": "python hello.py"}'},
        ], status=NodeStatus.COMPLETED)
        return tree, t

    def test_mechanical_template(self):
        from core.agent.execution.tree_consumers import (
            render_execution_summary)
        tree, t = self._tree_with_task()
        r = render_execution_summary(tree, t.node_id)
        assert r["ok"] and r["strategy"] == "mechanical"
        assert "## Goal" in r["summary"]
        assert "write_file" in r["summary"]
        assert "hello.py" in r["summary"]  # 机械提取文件（纸面限制内）
        assert "## Verdict" in r["summary"]

    def test_mechanical_is_pure_function(self):
        """只改出站视图（W3）: 渲染前后树不变。"""
        from core.agent.execution.tree_consumers import (
            render_execution_summary)
        tree, t = self._tree_with_task()
        before = (t.content.get("result"), len(t.children))
        render_execution_summary(tree, t.node_id)
        after = (t.content.get("result"), len(t.children))
        assert before == after

    def test_llm_strategy_with_callback(self):
        from core.agent.execution.tree_consumers import (
            render_execution_summary)
        tree, t = self._tree_with_task()
        r = render_execution_summary(
            tree, t.node_id, strategy="llm",
            llm_callback=lambda p: "已写完 hello.py 并运行验证通过。")
        assert r["strategy"] == "llm"
        assert "hello.py" in r["summary"]

    def test_llm_empty_falls_back_mechanical(self):
        from core.agent.execution.tree_consumers import (
            render_execution_summary)
        tree, t = self._tree_with_task()
        r = render_execution_summary(
            tree, t.node_id, strategy="llm", llm_callback=lambda p: "")
        assert r["strategy"] == "mechanical"
        assert r.get("note") and "降级" in r["note"]

    def test_hybrid_appends_discoveries(self):
        from core.agent.execution.tree_consumers import (
            render_execution_summary)
        tree, t = self._tree_with_task()
        r = render_execution_summary(
            tree, t.node_id, strategy="hybrid",
            llm_callback=lambda p: "后续建议: 补测试用例")
        assert r["strategy"] == "hybrid"
        assert "## Discoveries / Next" in r["summary"]
        assert "补测试用例" in r["summary"]


class TestAuditFeedbackLoop:
    """阶段 5 补: 审计事件 → 回流闭环（检测→学习层回流, 不直接介入）。"""

    def _event(self, signal, ts=None):
        return {"kind": "exec_tree_audit", "signal": signal,
                "dimension": f"exec_tree.{signal}",
                "reason": f"{signal} 信号", "ts": ts or time.time(),
                "payload": {"tool": "run_shell"}}

    def test_doom_loop_threshold_triggers_reflux(self):
        from core.agent.execution.tree_consumers import AuditFeedbackLoop
        from core.agent.blueprint.decision_event import DecisionEventBus
        consumed = []

        class _FakeMF:
            def consume(self, audit):
                consumed.append(audit)

        bus = DecisionEventBus()
        loop = AuditFeedbackLoop(meta_feedback=_FakeMF(), decision_bus=bus)
        r1 = loop.consume_event(self._event("doom_loop"))
        assert r1["actions"] == []
        r2 = loop.consume_event(self._event("doom_loop"))
        assert len(r2["actions"]) == 1
        assert r2["actions"][0]["signal"] == "doom_loop"
        # 回流: MetaFeedback 收到低分审计 + 决策总线留痕
        assert consumed and consumed[0].dag_quality_score == 0.2
        switch = [e for e in bus._memory if e.get("kind") == "strategy_switch"]
        assert switch, "回流应有 strategy_switch 事件可回看"

    def test_below_threshold_no_action(self):
        from core.agent.execution.tree_consumers import AuditFeedbackLoop
        loop = AuditFeedbackLoop()
        r = loop.consume_event(self._event("failing_tool"))
        assert r["actions"] == []

    def test_window_expiry_drops_old_events(self):
        from core.agent.execution.tree_consumers import AuditFeedbackLoop
        loop = AuditFeedbackLoop()
        old = time.time() - 7200  # 超出 1h 窗口
        loop.consume_event(self._event("doom_loop", ts=old))
        r = loop.consume_event(self._event("doom_loop"))  # 新事件, 旧已过期
        assert r["actions"] == []  # 窗口内只有 1 条 → 不触发

    def test_non_audit_ignored(self):
        from core.agent.execution.tree_consumers import AuditFeedbackLoop
        loop = AuditFeedbackLoop()
        r = loop.consume_event({"kind": "meta_advice", "signal": "x"})
        assert not r["ok"] and r["reason"] == "not_audit"
