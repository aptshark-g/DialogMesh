# -*- coding: utf-8 -*-
"""E2E test — Blueprint orchestration full pipeline."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.blueprint import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
    SkillRegistry, BlueprintEngine, ConstraintChecker,
    MetaFeedback, BlueprintExecutor,
)


def test_models():
    """Phase 0.1: Dataclass round-trip."""
    nodes = [BlueprintNode("pcr_0", "pcr"), BlueprintNode("llm_1", "llm_reply", priority=1)]
    edges = [BlueprintEdge("pcr_0", "llm_1", "route")]
    dag = BlueprintDAG(nodes=nodes, edges=edges, strategy="TEMPLATE", confidence=1.0)
    assert dag.node_count == 2
    assert dag.roots() == [nodes[0]]
    assert dag.validate() == []
    print("  ✅ models round-trip")


def test_skill_registry():
    """Phase 0.2: Intent matching."""
    sr = SkillRegistry()
    strategy, bp = sr.match("代码分析")
    assert strategy == "TEMPLATE"
    assert bp.node_count == 5
    assert bp.strategy == "TEMPLATE"
    print("  ✅ skill_registry match")


def test_engine_template():
    """Phase 1: TEMPLATE strategy."""
    engine = BlueprintEngine()
    dag = engine.build("分析代码", intent="代码分析", strategy="TEMPLATE")
    assert dag.strategy == "TEMPLATE"
    assert dag.node_count == 5
    assert dag.validate() == []
    print("  ✅ engine TEMPLATE")


def test_engine_hybrid():
    """Phase 1: HYBRID strategy."""
    engine = BlueprintEngine()
    dag = engine.build("你好", intent="通用对话", strategy="HYBRID")
    assert dag.strategy == "HYBRID"
    assert dag.node_count >= 3
    assert dag.validate() == []
    print("  ✅ engine HYBRID")


def test_constraint_checker():
    """Phase 2: Constraint validation."""
    checker = ConstraintChecker()
    valid_dag = BlueprintDAG(
        nodes=[BlueprintNode("pcr_0", "pcr"), BlueprintNode("llm_1", "llm_reply", priority=1)],
        edges=[BlueprintEdge("pcr_0", "llm_1", "route")],
        strategy="TEMPLATE", confidence=1.0,
    )
    valid, errs = checker.validate(valid_dag)
    assert valid, f"Valid DAG should pass: {errs}"

    # Too many nodes
    big_dag = BlueprintDAG(
        nodes=[BlueprintNode(f"n_{i}", "context") for i in range(10)],
        edges=[],
        strategy="TEMPLATE", confidence=1.0,
    )
    valid2, _ = checker.validate(big_dag)
    assert not valid2, "10 nodes should fail"
    print("  ✅ constraint checker")


def test_meta_feedback():
    """Phase 3: MetaFeedback degradation logic."""
    from core.agent.blueprint.models import ExecutionAudit
    fb = MetaFeedback()
    for _ in range(3):
        fb.consume(ExecutionAudit("r1", "b1", "LLM_DRIVEN", dag_quality_score=0.3))
    actions = fb.check_degradations()
    assert len(actions) == 1
    assert actions[0]["action"] == "degrade"
    assert actions[0]["next"] == "HYBRID"
    print("  ✅ meta feedback degradation")


def test_executor():
    """Phase 2: BlueprintExecutor bridge."""
    executor = BlueprintExecutor()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("pcr_0", "pcr"), BlueprintNode("llm_1", "llm_reply", priority=1)],
        edges=[BlueprintEdge("pcr_0", "llm_1", "route")],
        strategy="TEMPLATE", confidence=1.0,
    )
    result = executor.execute(dag, user_text="测试")
    assert "chain_outputs" in result
    assert "latency_ms" in result
    print("  ✅ executor bridge")


def test_full_pipeline():
    """E2E: text → BlueprintEngine → task_graph → validate."""
    engine = BlueprintEngine()

    for intent in ["代码分析", "通用对话", "任务规划", "数据搜索", "因果推理"]:
        dag = engine.build(f"测试{intent}", intent=intent)
        valid, errs = ConstraintChecker().validate(dag)
        if not valid:
            print(f"  ⚠️ {intent}: {errs}")
        else:
            print(f"  ✅ {intent}: {dag.node_count} nodes, strategy={dag.strategy}")

    # Test fallback for unknown intent
    dag2 = engine.build("随机内容", intent="未知")
    assert dag2.node_count > 0
    print("  ✅ unknown intent fallback")


if __name__ == "__main__":
    print("Blueprint E2E Tests\n" + "=" * 50)
    test_models()
    test_skill_registry()
    test_engine_template()
    test_engine_hybrid()
    test_constraint_checker()
    test_meta_feedback()
    test_executor()
    test_full_pipeline()
    print("\n🎉 All E2E tests passed")
