# -*- coding: utf-8 -*-
"""P1-2 三层介入分级测试（META_ARBITER_ASYNC_INTERVENTION §3.3）.

覆盖:
  - RiskClassifier: kind/关键词分级（low/medium/high）
  - RiskClassifier.classify_node: checkpoint/高风险链 → high
  - route: 低风险 → applied; 中风险 → proposed; 高风险 → sync_required
  - approve/reject: 中风险事件回写 + user_correction 评论事件
  - executor RECOVERY 切换走路由（proposed, 不阻塞执行）
  - engine 介入 API 接线
"""
from __future__ import annotations

from core.agent.blueprint.decision_event import DecisionEventBus
from core.agent.blueprint.intervention import (
    InterventionRouter, RiskClassifier, RiskLevel,
)
from core.agent.blueprint.models import BlueprintNode


# ═══════════════════════════════════════════════════════════════
# RiskClassifier
# ═══════════════════════════════════════════════════════════════

def test_classify_kind_levels():
    assert RiskClassifier.classify_kind("plan_gate") == RiskLevel.HIGH
    assert RiskClassifier.classify_kind("strategy_switch") == RiskLevel.MEDIUM
    assert RiskClassifier.classify_kind("meta_advice") == RiskLevel.MEDIUM
    assert RiskClassifier.classify_kind("user_correction") == RiskLevel.LOW
    assert RiskClassifier.classify_kind("whatever") == RiskLevel.LOW


def test_classify_kind_keyword_upgrade():
    """写/删除/花钱类操作 → 高风险."""
    assert RiskClassifier.classify_kind(
        "strategy_switch", dimension="plan", reason="write to file") == RiskLevel.HIGH
    assert RiskClassifier.classify_kind(
        "meta_advice", dimension="plan", reason="删除目录") == RiskLevel.HIGH
    # 普通维度不升级
    assert RiskClassifier.classify_kind(
        "strategy_switch", dimension="plan.strategy", reason="质量低") == RiskLevel.MEDIUM


def test_classify_node():
    ckpt = BlueprintNode("n1", "context", checkpoint=True)
    assert RiskClassifier.classify_node(ckpt) == RiskLevel.HIGH
    tool = BlueprintNode("n2", "tool")
    assert RiskClassifier.classify_node(tool) == RiskLevel.HIGH
    pcr = BlueprintNode("n3", "pcr")
    assert RiskClassifier.classify_node(pcr) == RiskLevel.LOW


# ═══════════════════════════════════════════════════════════════
# route
# ═══════════════════════════════════════════════════════════════

def test_route_low_applied():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    out = r.route(kind="user_correction", dimension="plan.node.x",
                  before="a", after="b", reason="调整顺序")
    assert out["level"] == "low"
    assert out["status"] == "applied"
    assert out["sync_required"] is False
    assert bus.recent(kind="user_correction")[0]["status"] == "applied"


def test_route_medium_proposed():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    out = r.route(kind="strategy_switch", dimension="plan.node.y",
                  before="LLM_DRIVEN", after="HYBRID", reason="质量低")
    assert out["level"] == "medium"
    assert out["status"] == "proposed"
    assert out["sync_required"] is False
    ev = bus.recent(kind="strategy_switch")[0]
    assert ev["status"] == "proposed"


def test_route_high_sync_required():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    out = r.route(kind="strategy_switch", dimension="plan.node.z",
                  before="a", after="b", reason="write file")
    assert out["level"] == "high"
    assert out["status"] == "proposed"
    assert out["sync_required"] is True


def test_route_no_bus_safe():
    r = InterventionRouter(None)
    out = r.route(kind="strategy_switch", dimension="x", reason="y")
    assert out["status"] == "proposed"
    assert out["event"] == {}


# ═══════════════════════════════════════════════════════════════
# approve / reject（PR review 语义）
# ═══════════════════════════════════════════════════════════════

def test_approve_medium_event():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    r.route(kind="strategy_switch", dimension="plan.node.aa",
            before="X", after="Y", reason="质量低")
    ev = r.approve(dimension="plan.node.aa", comment="可以")
    assert ev is not None
    assert ev["status"] == "applied"
    assert ev["comment"] == "可以"
    # 追加 user_correction 评论事件（回看可追溯）
    corrections = bus.recent(kind="user_correction")
    assert len(corrections) == 1
    assert corrections[0]["actor"] == "user"
    assert "批准" in corrections[0]["reason"]


def test_reject_medium_event():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    r.route(kind="strategy_switch", dimension="plan.node.bb",
            before="X", after="Y", reason="质量低")
    ev = r.reject(dimension="plan.node.bb", comment="不同意")
    assert ev is not None
    assert ev["status"] == "rejected"
    corrections = bus.recent(kind="user_correction")
    assert corrections[0]["actor"] == "user"
    assert "否决" in corrections[0]["reason"]


def test_intervene_no_match_returns_none():
    bus = DecisionEventBus()
    r = InterventionRouter(bus)
    assert r.approve(dimension="no_such_dim") is None
    # 已 applied 的事件不能再介入
    r.route(kind="strategy_switch", dimension="plan.node.cc",
            before="X", after="Y", reason="r")
    ev = r.approve(dimension="plan.node.cc", comment="x")
    assert ev is not None
    assert r.approve(dimension="plan.node.cc") is None


# ═══════════════════════════════════════════════════════════════
# executor RECOVERY 走路由
# ═══════════════════════════════════════════════════════════════

def test_executor_recovery_switch_is_proposed():
    from core.agent.blueprint.executor import BlueprintExecutor
    from core.agent.blueprint.models import BlueprintDAG, BlueprintEdge

    bus = DecisionEventBus()
    from core.agent.blueprint.intervention import InterventionRouter
    router = InterventionRouter(bus)

    def hook(node, error, outputs):
        return [BlueprintNode("subgraph_alt_2", "subgraph", priority=1)]

    class _RecoveryExec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

        def _handle_intent(self, node, outputs, text):
            return {"intents": {"segments": ["代码分析"]}, "status": "ok"}

        def _handle_subgraph(self, node, outputs, text):
            if node.node_id == "subgraph_2":
                return {"status": "error", "error": "boom"}
            return {"compiled_subgraph": "ok", "status": "ok"}

        def _handle_llm_reply(self, node, outputs, text):
            return {"response": "final", "status": "ok"}

    ex = _RecoveryExec(recovery_hook=hook, decision_bus=bus, intervention=router)
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("intent_1", "intent", priority=0),
            BlueprintNode("subgraph_2", "subgraph", priority=1),
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
    r = ex.execute(dag, user_text="分析")
    assert r["chain_outputs"]["subgraph_alt_2"]["status"] == "ok"
    switches = bus.recent(kind="strategy_switch")
    assert len(switches) == 1
    assert switches[0]["status"] == "proposed"  # 中风险待 approve, 不阻塞执行
    # 介入: approve 后状态回写
    ev = router.approve(dimension=switches[0]["dimension"], comment="同意切换")
    assert ev is not None
    assert ev["status"] == "applied"


# ═══════════════════════════════════════════════════════════════
# engine 介入 API
# ═══════════════════════════════════════════════════════════════

def test_engine_intervention_api():
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    from core.agent.blueprint.intervention import InterventionRouter
    eng = CognitiveRuntimeEngine()
    # 手动挂一条中风险事件
    ir = eng._intervention
    assert ir is not None
    ir.route(kind="strategy_switch", dimension="plan.node.test",
             before="A", after="B", reason="r")
    ok = eng.intervention_approve(dimension="plan.node.test", comment="ok")
    assert ok["ok"] is True
    assert ok["event"]["status"] == "applied"
    ok2 = eng.intervention_reject(dimension="plan.node.test")
    assert ok2["ok"] is False  # 已 applied 不可再介入

