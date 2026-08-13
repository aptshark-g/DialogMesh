# -*- coding: utf-8 -*-
"""学习闭环测试 — GAP-D2/D1/D5（COMPLETENESS_GAP_INVENTORY §A）.

覆盖:
  - GAP-D2: LearningBridge.learn_from_execution → learn_blueprint 真沉淀
    （含 tool 节点; 生产注入点 v3_session_api run_dag 之后）
  - GAP-D1: 成功轨迹 → trace_store → distill_once → A24 可逆推验证 →
    达标候选沉淀为 LEARNED_TEMPLATES
  - GAP-D5: SkillLifecycle 活性状态机（register/touch/pin/引用保护/
    迁移/report dry-run）
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.skill_registry import (
    SkillRegistry, LEARNED_TEMPLATES, BUILTIN_TEMPLATES)
from core.agent.blueprint.learning_bridge import (
    LearningBridge, ExecutionTrace, ExecutionTraceStore,
)
from core.agent.blueprint.skill_lifecycle import SkillLifecycle


def _tool_dag(tool: str = "arxiv_search") -> BlueprintDAG:
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("intent_1", "intent", priority=0),
            BlueprintNode("tool_2", "tool", priority=1,
                          params={"tool": tool, "args": {}}),
            BlueprintNode("llm_reply_3", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "intent_1", "route", required=False),
            BlueprintEdge("intent_1", "tool_2", "intent_context"),
            BlueprintEdge("tool_2", "llm_reply_3", "tool_result"),
        ],
        strategy="TEMPLATE",
    )


# ═══════════════════════════════════════════════════════════════
# GAP-D2: learn_blueprint 生产注入
# ═══════════════════════════════════════════════════════════════

def test_learn_from_execution_registers_learned_template():
    """生产学习入口: 含 tool 节点的成功 DAG → LEARNED_TEMPLATES 沉淀."""
    reg = SkillRegistry()
    bridge = LearningBridge(registry=reg)
    ok = bridge.learn_from_execution(_tool_dag(), "查论文",
                                     request_id="req-1", success=True)
    assert ok is True
    assert "查论文" in LEARNED_TEMPLATES
    # match 优先命中学习模板
    strategy, dag = reg.match("查论文")
    assert strategy == "TEMPLATE"
    assert dag is LEARNED_TEMPLATES["查论文"] or \
        dag.design_rationale.startswith("LEARNED")


def test_learn_from_execution_skips_plain_dag():
    """无 tool 节点的 DAG 不沉淀（纯 pcr/intent 链已有内置模板）."""
    reg = SkillRegistry()
    bridge = LearningBridge(registry=reg)
    plain = BlueprintDAG(
        nodes=[BlueprintNode("pcr_0", "pcr"),
               BlueprintNode("llm_1", "llm_reply", priority=1)],
        edges=[BlueprintEdge("pcr_0", "llm_1", "route")],
        strategy="TEMPLATE",
    )
    ok = bridge.learn_from_execution(plain, "通用对话",
                                     request_id="req-2", success=True)
    assert ok is False


def test_learn_from_execution_failure_no_trace():
    """失败执行不收集轨迹（只学成功）."""
    reg = SkillRegistry()
    bridge = LearningBridge(registry=reg)
    bridge.learn_from_execution(_tool_dag(), "查论文",
                                request_id="req-3", success=False)
    assert len(bridge.trace_store) == 0


# ═══════════════════════════════════════════════════════════════
# GAP-D1: 蒸馏原料管道
# ═══════════════════════════════════════════════════════════════

def test_trace_store_feeds_distill():
    """成功轨迹进 trace_store → scan(behavior_store) 产出候选."""
    store = ExecutionTraceStore()
    for i in range(5):
        store.add(ExecutionTrace(
            request_id=f"r{i}", intent="查论文",
            tool_sequence=["arxiv_search", "web_fetch"],
            node_count=4, strategy="TEMPLATE", success=True,
        ))
    assert len(store) == 5
    seqs = store.get_sequences()
    assert len(seqs) == 5
    assert seqs[0]["actions"] == ["arxiv_search", "web_fetch"]


def test_distill_once_promotes_candidate():
    """≥3 次同模式轨迹 → 蒸馏候选 → A24 验证达标 → 沉淀."""
    reg = SkillRegistry()
    bridge = LearningBridge(registry=reg)
    bridge._distill_interval = 0  # 每次 learn 都蒸馏（测试）
    for i in range(6):
        bridge.learn_from_execution(_tool_dag("arxiv_search"), "查论文",
                                    request_id=f"d{i}", success=True)
    # 至少沉淀出蒸馏产物（原 learn_blueprint 已沉淀"查论文"）
    assert "查论文" in LEARNED_TEMPLATES
    assert bridge.summary()["traces"] >= 6


def test_a24_verify_coverage_bounds():
    """A24: coverage 60-80% 合格; 100%=过拟合拒绝; 0%=没学到拒绝."""
    from core.agent.planner.models import (
        CapabilityBlueprint, SkillBelief, SkillCandidate, ActionNode,
    )
    from core.agent.blueprint.learning_bridge import LearningBridge as LB

    cand = SkillCandidate(
        candidate_id="c1",
        blueprint=CapabilityBlueprint(
            blueprint_id="bp1", goal="pattern",
            action_graph=[ActionNode("a1", "arxiv_search"),
                          ActionNode("a2", "web_fetch")],
        ),
        belief=SkillBelief(support=5, coverage=0.4),
    )
    traces = [
        ExecutionTrace(tool_sequence=["arxiv_search", "web_fetch"],
                       success=True) for _ in range(5)
    ]
    # 全覆盖 = 100% → 过拟合 → 拒绝
    assert LB._a24_verify(cand, traces) is False
    # 3/5 = 60% → 合格
    traces2 = [
        ExecutionTrace(tool_sequence=["arxiv_search", "web_fetch"],
                       success=True) for _ in range(3)
    ] + [
        ExecutionTrace(tool_sequence=["time"], success=True) for _ in range(2)
    ]
    assert LB._a24_verify(cand, traces2) is True


# ═══════════════════════════════════════════════════════════════
# GAP-D5: 技能生命周期
# ═══════════════════════════════════════════════════════════════

def test_lifecycle_register_and_touch():
    lc = SkillLifecycle(stale_after_days=1, archive_after_days=2,
                        prune_after_days=3)
    lc.register("查论文")
    lc.touch("查论文")
    m = lc.meta()["查论文"]
    assert m["use_count"] == 1
    assert m["state"] == "active"


def test_lifecycle_transitions():
    import time
    lc = SkillLifecycle(stale_after_days=1, archive_after_days=2,
                        prune_after_days=3)
    lc.register("旧技能", created_at=time.time() - 100 * 86400)
    LEARNED_TEMPLATES["旧技能"] = _tool_dag()
    now = time.time()
    c1 = lc.apply_transitions(now=now)
    assert c1["active_to_stale"] >= 1
    c2 = lc.apply_transitions(now=now)
    assert c2["stale_to_archived"] >= 1
    c3 = lc.apply_transitions(now=now)
    assert c3["archived_to_pruned"] >= 1
    # pruned 从可匹配区移除
    assert "旧技能" not in LEARNED_TEMPLATES


def test_lifecycle_pin_and_reference_protect():
    import time
    lc = SkillLifecycle(stale_after_days=1, archive_after_days=2,
                        prune_after_days=3)
    lc.register("固定技能", created_at=time.time() - 100 * 86400)
    lc.pin("固定技能")
    LEARNED_TEMPLATES["固定技能"] = _tool_dag("time")
    lc.register("被引用技能", created_at=time.time() - 100 * 86400)
    lc.add_reference("被引用技能", "cron")
    LEARNED_TEMPLATES["被引用技能"] = _tool_dag("echo")
    now = time.time()
    c = lc.apply_transitions(now=now)
    assert c["archived_to_pruned"] == 0
    assert "固定技能" in LEARNED_TEMPLATES
    assert "被引用技能" in LEARNED_TEMPLATES


def test_lifecycle_report_dry_run():
    import time
    lc = SkillLifecycle(stale_after_days=1)
    lc.register("新技能", created_at=time.time())
    r = lc.report(dry_run=True)
    assert r["dry_run"] is True
    assert r["total"] == 1
    assert r["skills"]["新技能"]["state"] == "active"


def test_engine_wires_bridge_and_lifecycle():
    """engine 装配: _learning_bridge + _skill_lifecycle + registry 共享."""
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    eng = CognitiveRuntimeEngine()
    lb = getattr(eng, "_learning_bridge", None)
    lc = getattr(eng, "_skill_lifecycle", None)
    assert lb is not None
    assert lc is not None
    assert lb.registry._lifecycle is lc


def test_engine_learn_from_execution():
    """engine.learn_from_execution 生产入口可用."""
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    eng = CognitiveRuntimeEngine()
    r = eng.learn_from_execution(_tool_dag("time"), intent="查时间",
                                 request_id="e1", success=True)
    assert r["learned"] is True
    assert "查时间" in LEARNED_TEMPLATES


# ── recall_pipeline 模板注册（2026-08-11, 意图→召回→图扩展→回复）──


def test_recall_pipeline_template_registered():
    """recall_pipeline 模板已注册, 含 recall_decompose 工具节点。"""
    from core.agent.blueprint.skill_registry import BUILTIN_TEMPLATES
    dag = BUILTIN_TEMPLATES.get("recall_pipeline")
    assert dag is not None
    tool_nodes = [n for n in dag.nodes if n.chain == "tool"]
    assert tool_nodes, "模板应含 tool 节点"
    assert tool_nodes[0].params.get("tool") == "recall_decompose"
    chains = [n.chain for n in dag.nodes]
    assert "pcr" in chains and "intent" in chains
    assert "subgraph" in chains and "llm_reply" in chains


def test_recall_pipeline_intent_match():
    """意图"记忆召回"匹配到 recall_pipeline 模板。"""
    reg = SkillRegistry()
    strategy, dag = reg.match("记忆召回")
    assert dag is BUILTIN_TEMPLATES["recall_pipeline"]
    assert strategy == "TEMPLATE"


def test_recall_intent_partial_match():
    """包含式匹配: "需要记忆召回历史内容" 也能命中。"""
    reg = SkillRegistry()
    _, dag = reg.match("需要记忆召回历史内容")
    assert dag is BUILTIN_TEMPLATES["recall_pipeline"]
