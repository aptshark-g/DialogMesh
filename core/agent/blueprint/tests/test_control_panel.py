# -*- coding: utf-8 -*-
"""GAP-P1 控制面板参数化测试（COMPLETENESS_GAP_INVENTORY §D）.

覆盖（DESIGN_DEEP_AUDIT §P2）:
  - build(strictness) 缩放约束: 严格→节点/深度上限收紧, 宽松→放宽
  - build(depth) 覆盖图深度上限
  - build(breadth) 透传 LLM_DRIVEN 发散路径数
  - build(decision_mode) 映射策略（template/hybrid/llm/auto）
"""
from __future__ import annotations

from core.agent.blueprint.engine import BlueprintEngine, ConstraintChecker
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode


def test_strictness_scales_limits():
    ck = ConstraintChecker()
    # 严格 → 上限收紧
    assert ck._scaled_limit(7, 1.0, lo=5, hi=12) == 5
    assert ck._scaled_limit(18, 1.0, lo=12, hi=24) == 12
    # 宽松 → 上限放宽
    assert ck._scaled_limit(7, 0.0, lo=5, hi=12) == 12
    assert ck._scaled_limit(18, 0.0, lo=12, hi=24) == 24
    # 默认
    assert ck._scaled_limit(7, 0.5, lo=5, hi=12) == 8


def test_strict_validate_rejects_bigger_dag():
    ck = ConstraintChecker()
    dag = BlueprintDAG(nodes=[BlueprintNode(f"n{i}", "pcr") for i in range(9)])
    # 宽松: 12 上限 → 通过（结构错误不算）
    ok_loose, _ = ck.validate(dag, strictness=0.0)
    ok_strict, errs = ck.validate(dag, strictness=1.0)
    assert ok_loose is False  # 无 llm_reply/pcr root 结构错误, 但节点数本身 ok
    assert any("Node count" in e for e in errs)
    assert ok_strict is False


def test_build_accepts_control_params():
    eng = BlueprintEngine()
    dag = eng.build("分析代码", intent="代码分析",
                    strictness=0.8, depth=10, breadth=4,
                    decision_mode="template")
    assert dag is not None
    assert dag.node_count > 0
    assert eng.checker.MAX_DEPTH == 10


def test_build_decision_mode_maps_strategy():
    eng = BlueprintEngine()
    # llm 模式强制 LLM_DRIVEN（fallback 到 general_chat 模板也标 LLM_DRIVEN 或 RECOVERY）
    dag = eng.build("帮我研究因果", intent="因果推理", decision_mode="llm")
    assert dag.strategy in ("LLM_DRIVEN", "RECOVERY")
    # template 模式强制 TEMPLATE
    dag2 = eng.build("分析代码", intent="代码分析", decision_mode="template")
    assert dag2.strategy == "TEMPLATE"


def test_build_breadth_passed_to_diverge():
    eng = BlueprintEngine()
    captured = {}
    orig = eng.builder.diverge

    def fake_diverge(text, intent, breadth=3):
        captured["breadth"] = breadth
        return orig(text, intent, breadth=breadth)

    eng.builder.diverge = fake_diverge
    try:
        eng.build("查论文", intent="数据搜索", decision_mode="llm", breadth=5)
        assert captured.get("breadth") == 5
    finally:
        eng.builder.diverge = orig


def test_build_auto_mode_uses_registry():
    eng = BlueprintEngine()
    dag = eng.build("随便聊聊", intent="通用对话", decision_mode="auto")
    assert dag is not None
    assert dag.strategy in ("HYBRID", "TEMPLATE", "LLM_DRIVEN", "RECOVERY")

