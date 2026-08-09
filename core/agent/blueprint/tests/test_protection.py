# -*- coding: utf-8 -*-
"""G3 LLM_DRIVEN 四保护测试（FLOW_SELF_GROWTH §三 G3）.

覆盖:
  - PlanGate: checkpoint 节点执行前暂停 → approve/reject/adjust 三态
  - PlanGate: 高风险链（tool）无 resolver 默认 approve（异步日志语义）
  - Budget: 执行期总执行次数上限（RECOVERY 放大后防死循环）
  - LoopDetector: 重访 3 次 → 强制 checkpoint（plan_gate 事件）
  - QualityGate: 评分 + 低分降级 HYBRID 事件
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.decision_event import DecisionEventBus
from core.agent.blueprint.protection import (
    PlanGate, Budget, LoopDetector, QualityGate,
)


def _dag(checkpoint_node: str = "") -> BlueprintDAG:
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("intent_1", "intent", priority=0),
            BlueprintNode("subgraph_2", "subgraph", priority=1,
                          checkpoint=(checkpoint_node == "subgraph_2")),
            BlueprintNode("llm_reply_3", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "intent_1", "route", required=False),
            BlueprintEdge("intent_1", "subgraph_2", "intent_context"),
            BlueprintEdge("subgraph_2", "llm_reply_3", "compiled_subgraph"),
            BlueprintEdge("intent_1", "llm_reply_3", "intent_context"),
        ],
        strategy="TEMPLATE",
    )


class _Exec(BlueprintExecutor):
    """测试替身: 全链 ok."""

    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}

    def _handle_intent(self, node, outputs, text):
        return {"intents": {"segments": ["代码分析"]}, "status": "ok"}

    def _handle_subgraph(self, node, outputs, text):
        return {"compiled_subgraph": "sg", "status": "ok"}

    def _handle_llm_reply(self, node, outputs, text):
        return {"response": "final", "status": "ok"}


# ═══════════════════════════════════════════════════════════════
# PlanGate
# ═══════════════════════════════════════════════════════════════

def test_plan_gate_checkpoint_approve_default():
    """checkpoint 节点无 resolver → 默认 approved, 执行继续, 写 plan_gate 事件."""
    bus = DecisionEventBus()
    ex = _Exec(decision_bus=bus)
    r = ex.execute(_dag(checkpoint_node="subgraph_2"), user_text="分析")
    assert r["chain_outputs"]["subgraph_2"]["status"] == "ok"
    gates = bus.recent(kind="plan_gate")
    assert len(gates) >= 1
    assert gates[0]["dimension"] == "plan.node.subgraph_2"
    assert gates[0]["status"] == "approved"


def test_plan_gate_reject_blocks_node():
    """用户 reject → 节点 error, 不执行."""
    bus = DecisionEventBus()
    ex = _Exec(decision_bus=bus,
               gate_resolver=lambda node, out: {"status": "rejected",
                                                "comment": "不要跑这个"})
    r = ex.execute(_dag(checkpoint_node="subgraph_2"), user_text="分析")
    out = r["chain_outputs"]["subgraph_2"]
    assert out["status"] == "error"
    assert "plan_gate rejected" in out["error"]
    gates = bus.recent(kind="plan_gate")
    assert gates[0]["status"] == "rejected"
    assert gates[0]["actor"] == "user"


def test_plan_gate_adjust_replaces_node():
    """用户 adjust → 替换节点执行（同 RECOVERY 语义）."""
    bus = DecisionEventBus()

    def resolver(node, out):
        return {"status": "adjusted",
                "adjust": [BlueprintNode("subgraph_alt_2", "subgraph", priority=1,
                                         params={"mode": "alt"})]}

    ex = _Exec(decision_bus=bus, gate_resolver=resolver)
    r = ex.execute(_dag(checkpoint_node="subgraph_2"), user_text="分析")
    assert r["chain_outputs"]["subgraph_alt_2"]["status"] == "ok"
    gates = bus.recent(kind="plan_gate")
    assert gates[0]["status"] == "adjusted"
    assert "subgraph_alt_2" in gates[0]["after"]


def test_plan_gate_high_risk_chain():
    """tool 链默认需 gate; 无 resolver → approved（异步日志, 不阻塞）."""
    bus = DecisionEventBus()
    pg = PlanGate(decision_bus=bus)
    tool_node = BlueprintNode("tool_1", "tool", priority=1,
                              params={"tool": "echo", "args": {"message": "hi"}})
    assert pg.requires_gate(tool_node)
    verdict = pg.resolve(tool_node, {})
    assert verdict["status"] == "approved"
    gates = bus.recent(kind="plan_gate")
    assert len(gates) == 1


def test_plan_gate_low_risk_no_gate():
    """pcr 链不需要 gate."""
    pg = PlanGate()
    assert not pg.requires_gate(BlueprintNode("pcr_0", "pcr"))


# ═══════════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════════

def test_budget_node_count():
    b = Budget(max_nodes=7)
    assert b.check_node_count(_dag())
    big = BlueprintDAG(nodes=[BlueprintNode(f"n{i}", "pcr") for i in range(8)])
    assert not b.check_node_count(big)


def test_budget_execution_cap_halts_loop():
    """RECOVERY 反复替换 → 总执行次数超预算 → 停止."""
    bus = DecisionEventBus()
    calls = {"n": 0}

    def hook(node, error, outputs):
        calls["n"] += 1
        return [BlueprintNode(f"subgraph_fb_{calls['n']}", "subgraph", priority=1)]

    class _LoopExec(_Exec):
        def _handle_subgraph(self, node, outputs, text):
            return {"status": "error", "error": "always fails"}

    ex = _LoopExec(recovery_hook=hook, decision_bus=bus,
                   budget=Budget(max_nodes=7, execution_multiplier=2))
    r = ex.execute(_dag(), user_text="分析")
    # 预算内停止: 部分节点 skipped（budget exceeded）
    skipped = [o for o in r["chain_outputs"].values()
               if o.get("status") == "skipped"]
    assert len(skipped) >= 1
    # 不会无限循环（总执行次数受限）
    assert calls["n"] < 20


# ═══════════════════════════════════════════════════════════════
# LoopDetector
# ═══════════════════════════════════════════════════════════════

def test_loop_detector_threshold():
    ld = LoopDetector(threshold=3)
    assert ld.visit("a") == 1
    assert not ld.requires_checkpoint("a")
    assert ld.visit("a") == 2
    assert not ld.requires_checkpoint("a")
    assert ld.visit("a") == 3
    assert ld.requires_checkpoint("a")
    assert ld.visits("a") == 3


def test_loop_detector_reset():
    ld = LoopDetector(threshold=3)
    ld.visit("a")
    ld.visit("a")
    ld.visit("a")
    assert ld.requires_checkpoint("a")
    ld.reset()
    assert not ld.requires_checkpoint("a")
    assert ld.summary() == {}


def test_loop_force_checkpoint_emits_plan_gate():
    """重访节点 3 次 → plan_gate 事件（用户可介入终止）."""
    bus = DecisionEventBus()
    ld = LoopDetector(threshold=3)

    def resolver(node, out):
        return {"status": "rejected", "comment": "循环终止"}

    class _LoopExec(_Exec):
        def _handle_subgraph(self, node, outputs, text):
            return {"status": "error", "error": "boom"}

    # hook 返回同名替换节点 → 同一 node_id 反复重跑, LoopDetector 累计到阈值
    ex = _LoopExec(decision_bus=bus, loop_detector=ld, gate_resolver=resolver,
                   recovery_hook=lambda n, e, o: [
                       BlueprintNode(n.node_id, "subgraph", priority=1)])
    r = ex.execute(_dag(), user_text="分析")
    # LoopDetector 触发 plan_gate（rejected → 该节点 error）
    gates = bus.recent(kind="plan_gate")
    rejected = [g for g in gates if g["status"] == "rejected"]
    assert len(rejected) >= 1
    assert ld.visits("subgraph_2") >= 3


# ═══════════════════════════════════════════════════════════════
# QualityGate
# ═══════════════════════════════════════════════════════════════

def test_quality_score_all_ok():
    dag = _dag()
    outputs = {
        "pcr_0": {"status": "ok"},
        "intent_1": {"status": "ok"},
        "subgraph_2": {"status": "ok"},
        "llm_reply_3": {"status": "ok", "response": "hi"},
    }
    s = QualityGate.score(dag, outputs, llm_reply="hi")
    assert s >= 1.0


def test_quality_score_errors_low():
    dag = _dag()
    outputs = {
        "pcr_0": {"status": "ok"},
        "intent_1": {"status": "error"},
        "subgraph_2": {"status": "error"},
        "llm_reply_3": {"status": "unavailable"},
    }
    s = QualityGate.score(dag, outputs, llm_reply="")
    assert s < 0.4


def test_quality_gate_degrades_and_emits_event():
    bus = DecisionEventBus()
    dag = _dag()
    outputs = {
        "pcr_0": {"status": "ok"},
        "intent_1": {"status": "error"},
        "subgraph_2": {"status": "error"},
        "llm_reply_3": {"status": "unavailable"},
    }
    qg = QualityGate(decision_bus=bus, low_threshold=0.5)
    result = qg.evaluate(dag, outputs, llm_reply="", strategy="LLM_DRIVEN")
    assert result["degraded"] is True
    switches = bus.recent(kind="strategy_switch")
    assert len(switches) == 1
    assert switches[0]["before"] == "LLM_DRIVEN"
    assert switches[0]["after"] == "HYBRID"
    assert "quality" in switches[0]["dimension"]


def test_quality_gate_ok_no_event():
    bus = DecisionEventBus()
    dag = _dag()
    outputs = {n.node_id: {"status": "ok"} for n in dag.nodes}
    qg = QualityGate(decision_bus=bus)
    result = qg.evaluate(dag, outputs, llm_reply="final")
    assert result["degraded"] is False
    assert bus.recent(kind="strategy_switch") == []


def test_executor_result_includes_quality():
    """execute 返回 quality 字段（白盒可读）."""
    ex = _Exec()
    r = ex.execute(_dag(), user_text="分析")
    assert "quality" in r
    assert 0.0 <= r["quality"]["score"] <= 1.0
