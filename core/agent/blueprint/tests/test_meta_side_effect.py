# -*- coding: utf-8 -*-
"""check_degradations 副作用化测试（P0-3, META_ARBITER §2.2/§3.2）.

覆盖:
  - 连续3次低分 → degrade → SkillRegistry 权重真实下降
  - degrade 写 decision_bus strategy_switch 事件（可回看）
  - 连续5次高分 → promote → 权重恢复
  - 无 decision_bus 时安全降级（不崩）
"""
from __future__ import annotations

from core.agent.blueprint.meta_feedback import MetaFeedback
from core.agent.blueprint.skill_registry import SkillRegistry
from core.agent.blueprint.models import ExecutionAudit
from core.agent.blueprint.decision_event import DecisionEventBus


def _audit(strategy: str, score: float) -> ExecutionAudit:
    return ExecutionAudit(
        request_id="r1", blueprint_id="b1", strategy=strategy,
        dag_quality_score=score,
    )


def test_degrade_side_effect_on_weights():
    """连续3次低分 → 权重真实下降 + 事件记录."""
    registry = SkillRegistry()
    bus = DecisionEventBus()
    fb = MetaFeedback(registry=registry, decision_bus=bus)
    # 3 次低分 (LLM_DRIVEN)
    for _ in range(3):
        fb.consume(_audit("LLM_DRIVEN", 0.2))
    before = registry._strategy_weights["因果推理"][0].weight
    actions = fb.check_degradations()
    assert any(a["action"] == "degrade" and a["strategy"] == "LLM_DRIVEN"
               for a in actions)
    # 权重被压低（副作用生效）
    after = registry._strategy_weights["因果推理"][0].weight
    assert after <= before, f"degrade 后权重应下降: {before} -> {after}"
    # decision_bus 有 strategy_switch 事件
    switches = bus.recent(kind="strategy_switch")
    assert len(switches) >= 1
    assert "LLM_DRIVEN" in switches[0]["dimension"]
    assert switches[0]["actor"] == "meta"


def test_promote_restores_weight():
    """连续5次高分 → promote → 权重恢复."""
    registry = SkillRegistry()
    fb = MetaFeedback(registry=registry)
    # 先降级
    for _ in range(3):
        fb.consume(_audit("LLM_DRIVEN", 0.2))
    fb.check_degradations()
    degraded = registry._strategy_weights["因果推理"][0].weight
    # 5 次高分
    for _ in range(5):
        fb.consume(_audit("LLM_DRIVEN", 0.9))
    actions = fb.check_degradations()
    assert any(a["action"] == "promote" for a in actions)
    promoted = registry._strategy_weights["因果推理"][0].weight
    assert promoted > degraded, f"promote 后权重应恢复: {degraded} -> {promoted}"


def test_no_bus_safe():
    """无 decision_bus → 副作用仍生效, 不崩."""
    registry = SkillRegistry()
    fb = MetaFeedback(registry=registry)
    for _ in range(3):
        fb.consume(_audit("LLM_DRIVEN", 0.1))
    actions = fb.check_degradations()
    assert any(a["action"] == "degrade" for a in actions)
