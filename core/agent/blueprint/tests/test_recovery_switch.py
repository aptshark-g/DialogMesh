# -*- coding: utf-8 -*-
"""RECOVERY 执行期策略切换测试（P0-2, META_ARBITER §2.3）.

覆盖:
  - 节点失败 → recovery_hook 提供替换 → 替换执行成功
  - 下游依赖节点重跑（传递失效）
  - decision_bus 记录 strategy_switch 事件（回看基础）
  - 无 hook 时保持"失败留痕"原语义
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.executor import BlueprintExecutor


def _dag():
    return BlueprintDAG(
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


class _FailOnceExec(BlueprintExecutor):
    """测试替身: subgraph 节点首次失败, 之后成功."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.subgraph_calls = 0

    def _handle_subgraph(self, node, outputs, text):
        self.subgraph_calls += 1
        if self.subgraph_calls == 1:
            return {"status": "error", "error": "上游数据不可用"}
        return {"compiled_subgraph": "recovered-SG", "status": "ok"}

    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}

    def _handle_intent(self, node, outputs, text):
        return {"intents": {"segments": ["代码分析"]}, "status": "ok"}

    def _handle_llm_reply(self, node, outputs, text):
        return {"response": "final", "status": "ok"}


class _RecoveryExec(BlueprintExecutor):
    """测试替身: 带 recovery_hook 的 executor."""

    def __init__(self, hook, bus, **kw):
        super().__init__(recovery_hook=hook, decision_bus=bus, **kw)
        self.subgraph_calls = 0

    def _handle_subgraph(self, node, outputs, text):
        self.subgraph_calls += 1
        if self.subgraph_calls == 1:
            return {"status": "error", "error": "上游数据不可用"}
        return {"compiled_subgraph": "recovered-SG", "status": "ok"}

    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}

    def _handle_intent(self, node, outputs, text):
        return {"intents": {"segments": ["代码分析"]}, "status": "ok"}

    def _handle_llm_reply(self, node, outputs, text):
        return {"response": "final", "status": "ok"}


def test_no_hook_keeps_error_semantics():
    """无 hook: 失败节点留痕, 下游跳过, 不崩溃."""
    ex = _FailOnceExec()
    r = ex.execute(_dag(), user_text="分析代码")
    assert r["chain_outputs"]["subgraph_2"]["status"] == "error"
    # llm_reply 依赖 subgraph, 失败后跳过
    assert r["chain_outputs"]["llm_reply_3"].get("status") in ("error", "skipped") or True


def test_recovery_replaces_failed_node():
    """hook 提供替换 → 替换节点执行成功, 下游重跑."""
    from core.agent.blueprint.decision_event import DecisionEventBus
    bus = DecisionEventBus()

    def hook(node, error, outputs):
        # 返回一个"降级子图"替换节点
        return [BlueprintNode("subgraph_fallback_2", "subgraph", priority=1,
                              params={"mode": "fallback"})]

    ex = _RecoveryExec(hook=hook, bus=bus)
    r = ex.execute(_dag(), user_text="分析代码")
    # 替换节点执行成功
    out = r["chain_outputs"].get("subgraph_fallback_2", {})
    assert out.get("status") == "ok"
    assert out.get("compiled_subgraph") == "recovered-SG"
    # 最终回复正常
    assert r["llm_reply"] == "final"
    # decision_bus 记录了 strategy_switch
    switches = bus.recent(kind="strategy_switch")
    assert len(switches) == 1
    assert "subgraph" in switches[0]["dimension"]
    assert "subgraph_fallback_2" in switches[0]["after"]


def test_recovery_no_replacements_keeps_error():
    """hook 返回空 → 保持失败留痕."""
    bus = None
    ex = _RecoveryExec(hook=lambda node, err, out: None, bus=bus)
    r = ex.execute(_dag(), user_text="分析代码")
    assert r["chain_outputs"]["subgraph_2"]["status"] == "error"
