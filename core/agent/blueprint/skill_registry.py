# -*- coding: utf-8 -*-
"""SkillRegistry — intent→strategy matching with 5 built-in Blueprint templates.

§十 三种策略:
  - TEMPLATE: 确定性模板 (code_analysis, data_search)
  - HYBRID: 模板 floor + LLM override (general_chat, task_planning)
  - LLM_DRIVEN: LLM 全权构建 (causal_reasoning)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

logger = logging.getLogger(__name__)


def _make_node(node_id: str, chain: str, priority: int = 0, checkpoint: bool = False, **params) -> BlueprintNode:
    return BlueprintNode(node_id=node_id, chain=chain, priority=priority, checkpoint=checkpoint, params=params)


def _make_edge(from_node: str, to_node: str, data_key: str, required: bool = True) -> BlueprintEdge:
    return BlueprintEdge(from_node=from_node, to_node=to_node, data_key=data_key, required=required)


# ═══════════════════════════════════════════════
# 5 Built-in Blueprint Templates (订阅表语义 §14.3)
# ═══════════════════════════════════════════════
#
# 重构依据: BUSINESS_FLOW_COLLECTION_20260805.md
#   - 模板 = 业务流（技能 × 链 × Tick × 工具 × 安全约束）
#   - 同 Tick 并行（pcr∥intent）→ 跨 Tick 串行（context/subgraph/profile）→ llm_reply
#   - 工具/安全约束进 node.params（DESIGN_BLUEPRINT_SYSTEM §三）
#   - async 段（meta/behavior）发事件广播（DESIGN_BLUEPRINT_ORCHESTRATION §14.3）

BUILTIN_TEMPLATES: Dict[str, BlueprintDAG] = {}
# G2 (FLOW_SELF_GROWTH): 学习沉淀的动态模板区（执行成功 → 沉淀）
# match 顺序: LEARNED 优先（成功经验 > 通用种子）
LEARNED_TEMPLATES: Dict[str, BlueprintDAG] = {}


def _tick0_pair(analysis_rationale: str) -> list:
    """Tick0: pcr ∥ intent (并行，§14.3 订阅表)."""
    return [
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
    ]


def _llm_reply_node(node_id: str, priority: int = 2, reply_mode: str = "llm",
                    **params) -> BlueprintNode:
    return _make_node(node_id, "llm_reply", priority=priority,
                      reply_mode=reply_mode, **params)


# Template 1: code_analysis — TEMPLATE (确定性)
# DESIGN_BLUEPRINT_SYSTEM: analyze/security/bug/vulnerability → read+grep+write
BUILTIN_TEMPLATES["code_analysis"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("标准代码分析路径"),
        _make_node("context_2", "context", priority=1,
                   tools=["read", "grep"],
                   safety={"mode": "read_only"}),
        _make_node("subgraph_3", "subgraph", priority=1,
                   tools=["read", "grep"],
                   safety={"mode": "read_only"}),
        _llm_reply_node("llm_reply_4", priority=2,
                        format="markdown_report"),
        _make_node("meta_audit_5", "meta", priority=9),
        _make_node("behavior_learn_6", "behavior", priority=9),
    ],
    edges=[
        # §14.3: pcr.route 与 intent.split 同 Tick 并行（intent 只读文本）
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("pcr_0", "context_2", "compass"),
        _make_edge("intent_1", "context_2", "intent_context"),
        _make_edge("context_2", "subgraph_3", "assembled_context"),
        _make_edge("intent_1", "subgraph_3", "intent_context"),
        _make_edge("subgraph_3", "llm_reply_4", "compiled_subgraph"),
        _make_edge("intent_1", "llm_reply_4", "intent_context"),
        _make_edge("pcr_0", "llm_reply_4", "compass"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale=(
        "代码分析: Tick0(pcr∥intent) → Tick1(context∥subgraph 并行, 只读工具) "
        "→ Tick2(llm_reply 报告) → async(meta.audit∥behavior.learn)"
    ),
)

# Template 2: general_chat — HYBRID (模板基础 + LLM可覆盖)
BUILTIN_TEMPLATES["general_chat"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("通用对话"),
        _make_node("profile_2", "profile", priority=1,
                   safety={"mode": "read_only"}),
        _llm_reply_node("llm_reply_3", priority=2),
        _make_node("behavior_learn_4", "behavior", priority=9),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("intent_1", "profile_2", "intent_context"),
        _make_edge("profile_2", "llm_reply_3", "profile_text"),
        _make_edge("intent_1", "llm_reply_3", "intent_context"),
        _make_edge("pcr_0", "llm_reply_3", "compass"),
    ],
    strategy="HYBRID",
    confidence=0.9,
    design_rationale=(
        "通用对话: Tick0(pcr∥intent) → Tick1(profile) → Tick2(llm_reply) "
        "→ async(behavior.learn)。LLM可加context/subgraph节点"
    ),
)

# Template 3: task_planning — HYBRID
# DESIGN_BLUEPRINT_SYSTEM: 任务分解 → 子 Agent 分配 → 拓扑执行
BUILTIN_TEMPLATES["task_planning"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("任务规划"),
        _make_node("context_2", "context", priority=1,
                   tools=["read"], safety={"mode": "read_only"}),
        _make_node("subgraph_3", "subgraph", priority=1,
                   tools=["read", "grep"], safety={"mode": "read_only"}),
        _make_node("profile_4", "profile", priority=1,
                   safety={"mode": "read_only"}),
        _llm_reply_node("llm_reply_5", priority=2,
                        format="task_graph"),
        _make_node("meta_audit_6", "meta", priority=9),
        _make_node("behavior_learn_7", "behavior", priority=9),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("pcr_0", "context_2", "compass"),
        _make_edge("intent_1", "context_2", "intent_context"),
        _make_edge("context_2", "subgraph_3", "assembled_context"),
        _make_edge("intent_1", "profile_4", "intent_context"),
        _make_edge("intent_1", "subgraph_3", "intent_context"),
        _make_edge("subgraph_3", "llm_reply_5", "compiled_subgraph"),
        _make_edge("profile_4", "llm_reply_5", "profile_text"),
        _make_edge("intent_1", "llm_reply_5", "intent_context"),
        _make_edge("pcr_0", "llm_reply_5", "compass"),
    ],
    strategy="HYBRID",
    confidence=0.85,
    design_rationale=(
        "任务规划: Tick0(pcr∥intent) → Tick1(context∥subgraph∥profile 并行) "
        "→ Tick2(llm_reply task_graph) → async(meta.audit∥behavior.learn)"
    ),
)

# Template 4: data_search — TEMPLATE
# DESIGN_BLUEPRINT_SYSTEM: search/find/grep → grep+glob+read (read_only)
BUILTIN_TEMPLATES["data_search"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("数据搜索"),
        _llm_reply_node("llm_reply_2", priority=1,
                        tools=["grep", "glob", "read"],
                        safety={"mode": "read_only"}),
        _make_node("behavior_learn_3", "behavior", priority=9),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("pcr_0", "llm_reply_2", "compass"),
        _make_edge("intent_1", "llm_reply_2", "intent_context"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale=(
        "快速搜索: Tick0(pcr∥intent) → Tick1(llm_reply, 只读工具) "
        "→ async(behavior.learn)。跳过 context/subgraph 加速"
    ),
)

# Template 5: causal_reasoning — LLM_DRIVEN (LLM 全权构建)
BUILTIN_TEMPLATES["causal_reasoning"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("因果推理"),
        _make_node("plan_gate_2", "context", priority=1, checkpoint=True,
                   safety={"mode": "read_only"},
                   note="LLM_DRIVEN 建图后 PlanGate 人工审核准入（§十一）"),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("intent_1", "plan_gate_2", "intent_context"),
    ],
    strategy="LLM_DRIVEN",
    confidence=0.0,  # No base confidence — LLM fills the rest
    design_rationale=(
        "因果推理: Tick0(pcr∥intent) → Tick1(PlanGate checkpoint 人工审核准入) "
        "→ LLM 全权构建完整 DAG。四保护齐备前保持特殊模式（§十一）"
    ),
)


# Template 6: recall_pipeline — TEMPLATE（意图→召回→图扩展→回复, 2026-08-11）
# 注册链路（用户拍板）: 意图分析（pcr/intent）→ recall_anchor 工具节点
# （ToolRegistry.recall_decompose）→ subgraph 图扩展 → llm_reply。
# 此前 recall 在 v3_session_api 直调（绕过蓝图）——本模板收进执行路径。
BUILTIN_TEMPLATES["recall_pipeline"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("记忆召回: 意图分析 → 召回锚点 → 图扩展"),
        _make_node("recall_anchor_2", "tool", priority=1,
                   tool="recall_decompose",
                   params={"top_k": 5, "parallel": True},
                   safety={"mode": "read_only"}),
        _make_node("subgraph_3", "subgraph", priority=1,
                   tools=["recall_decompose", "read"],
                   safety={"mode": "read_only"}),
        _llm_reply_node("llm_reply_4", priority=2),
        _make_node("meta_audit_5", "meta", priority=9),
        _make_node("behavior_learn_6", "behavior", priority=9),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("intent_1", "recall_anchor_2", "intent_context"),
        _make_edge("recall_anchor_2", "subgraph_3", "anchors"),
        _make_edge("intent_1", "subgraph_3", "intent_context"),
        _make_edge("subgraph_3", "llm_reply_4", "compiled_subgraph"),
        _make_edge("intent_1", "llm_reply_4", "intent_context"),
        _make_edge("pcr_0", "llm_reply_4", "compass"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale=(
        "记忆召回: Tick0(pcr∥intent 意图分析) → Tick1(recall_anchor 工具"
        "并行分解召回 + subgraph 图扩展) → Tick2(llm_reply) → async(meta.audit"
        "∥behavior.learn)。此前 recall 直调绕过蓝图, 本模板收进执行路径。"
    ),
)


# Template 7: intent_multi_recall — TEMPLATE（多意图 → 多路召回, 2026-08-13）
# 注册链路（用户拍板分层原则）: 流程层模板化 — 能力（RecallService 多路
# 召回/sub_queries）是工具, 入口消费是模板。意图节点输出多意图 segments
# （DualTrack is_multi）→ statemachine 注入 recall_decompose.sub_queries
# → 并行多路召回 → 子图扩展 → 回复。模板选择: v3 API 检测到多意图拆分时
# build(template="intent_multi_recall") 显式指定。
BUILTIN_TEMPLATES["intent_multi_recall"] = BlueprintDAG(
    nodes=[
        * _tick0_pair("多意图: 意图分析 → 多路召回 → 图扩展"),
        _make_node("recall_anchor_2", "tool", priority=1,
                   tool="recall_decompose",
                   params={"top_k": 5},
                   safety={"mode": "read_only"}),
        _make_node("subgraph_3", "subgraph", priority=1,
                   tools=["recall_decompose", "read"],
                   safety={"mode": "read_only"}),
        _llm_reply_node("llm_reply_4", priority=2),
        _make_node("meta_audit_5", "meta", priority=9),
        _make_node("behavior_learn_6", "behavior", priority=9),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route", required=False),
        _make_edge("intent_1", "recall_anchor_2", "intent_context"),
        _make_edge("recall_anchor_2", "subgraph_3", "anchors"),
        _make_edge("intent_1", "subgraph_3", "intent_context"),
        _make_edge("subgraph_3", "llm_reply_4", "compiled_subgraph"),
        _make_edge("intent_1", "llm_reply_4", "intent_context"),
        _make_edge("pcr_0", "llm_reply_4", "compass"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale=(
        "多意图: Tick0(pcr∥intent) → Tick1(recall_anchor 工具节点, "
        "statemachine 把 intent 节点 segments 注入 sub_queries → "
        "并行多路召回) → Tick2(llm_reply) → async(meta.audit∥behavior.learn)。"
        "模板化动机 = 可学习（多意图召回好坏 → MetaFeedback 调权重）可审计。"
    ),
)


# ═══════════════════════════════════════════════
# SkillRegistry — intent → (strategy, blueprint)
# ═══════════════════════════════════════════════

@dataclass
class StrategyWeight:
    """Per-intent strategy weight — adjusted by MetaFeedback learning."""
    strategy: str
    weight: float = 1.0
    success_count: int = 0
    total_count: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.5  # neutral default
        return self.success_count / self.total_count

    def record(self, score: float):
        self.total_count += 1
        if score >= 0.6:
            self.success_count += 1


class SkillRegistry:
    """Matches user intent → Blueprint strategy + template.

    Intent → strategy mapping is learned, not hardcoded.
    Weights adjust via MetaFeedback.update_strategy_weights().
    """

    def __init__(self):
        # intent → list of strategy weights
        self._strategy_weights: Dict[str, List[StrategyWeight]] = {}
        # GAP-D5: 技能生命周期（活性状态机, 可选挂载）
        self._lifecycle = None

        # Initialize with reasonable defaults
        self._init_defaults()

    def set_lifecycle(self, lifecycle) -> None:
        """GAP-D5: 挂载技能生命周期（learn 登记 + match touch）."""
        self._lifecycle = lifecycle

    def _init_defaults(self):
        """Seed initial strategy weights based on template defaults."""
        self._strategy_weights["代码分析"] = [
            StrategyWeight("TEMPLATE", 1.0),
            StrategyWeight("HYBRID", 0.7),
            StrategyWeight("LLM_DRIVEN", 0.2),
        ]
        self._strategy_weights["通用对话"] = [
            StrategyWeight("HYBRID", 1.0),
            StrategyWeight("TEMPLATE", 0.8),
            StrategyWeight("LLM_DRIVEN", 0.1),
        ]
        self._strategy_weights["通用讨论"] = [
            StrategyWeight("HYBRID", 1.0),
            StrategyWeight("TEMPLATE", 0.8),
        ]
        self._strategy_weights["任务规划"] = [
            StrategyWeight("HYBRID", 1.0),
            StrategyWeight("LLM_DRIVEN", 0.5),
            StrategyWeight("TEMPLATE", 0.6),
        ]
        self._strategy_weights["数据搜索"] = [
            StrategyWeight("TEMPLATE", 1.0),
            StrategyWeight("HYBRID", 0.3),
        ]
        self._strategy_weights["因果推理"] = [
            StrategyWeight("LLM_DRIVEN", 1.0),
            StrategyWeight("HYBRID", 0.4),
        ]
        self._strategy_weights["记忆召回"] = [
            StrategyWeight("TEMPLATE", 1.0),
            StrategyWeight("HYBRID", 0.6),
        ]

    def match(self, intent: str) -> Tuple[str, BlueprintDAG]:
        """Match intent → best strategy + blueprint template.

        Returns (strategy_name, blueprint_dag).
        Falls back to general_chat HYBRID if no match.
        G2: LEARNED_TEMPLATES 优先（成功沉淀的经验 > 通用种子）。
        """
        # Empty intent must never substring-match ("" in "代码分析" is True)
        if not intent:
            logger.info("Empty intent → defaulting to general_chat")
            return "HYBRID", BUILTIN_TEMPLATES["general_chat"]

        # 知识类关键词别名（2026-08-13, W1）: DualTrack 单意图返回原文,
        # 自由问句匹配不上已知意图名 → 落 general_chat（无 recall 节点）。
        # 知识/原理/对比类问句路由到"记忆召回"→ recall_pipeline
        # （recall_anchor→subgraph→llm_reply）; casual（你好等）不受影响。
        _knowledge_aliases = (
            "召回", "算法", "原理", "为什么", "解释", "介绍",
            "区别", "怎么实现", "如何实现", "哪些",
        )
        for _kw in _knowledge_aliases:
            if _kw in intent:
                logger.info("Intent '%s' → knowledge alias '%s' → 记忆召回",
                            intent, _kw)
                intent = "记忆召回"
                break

        # G2: 学习模板优先（精确命中）
        if intent in LEARNED_TEMPLATES:
            logger.info("Intent '%s' → LEARNED template (self-grown)", intent)
            if self._lifecycle is not None:
                try:
                    self._lifecycle.touch(intent)
                except Exception as e:
                    logger.debug("lifecycle touch failed: %s", e)
            return "TEMPLATE", LEARNED_TEMPLATES[intent]

        # Normalize intent — try exact match, then partial
        matched_intent = intent
        if intent not in self._strategy_weights:
            for known in self._strategy_weights:
                if known in intent or intent in known:
                    matched_intent = known
                    break

        weights_list = self._strategy_weights.get(matched_intent)
        if not weights_list:
            # Unknown intent → default to general_chat
            logger.info("Unknown intent '%s' → defaulting to general_chat", intent)
            return "HYBRID", BUILTIN_TEMPLATES["general_chat"]

        # Pick best strategy by weight × success_rate
        best = max(weights_list, key=lambda w: w.weight * w.success_rate)
        logger.info("Intent '%s' → strategy=%s (weight=%.2f, success=%.2f)",
                     intent, best.strategy, best.weight, best.success_rate)

        # Map strategy → template name
        template_map = {
            "代码分析": "code_analysis",
            "通用对话": "general_chat",
            "通用讨论": "general_chat",
            "任务规划": "task_planning",
            "数据搜索": "data_search",
            "因果推理": "causal_reasoning",
            "记忆召回": "recall_pipeline",
        }
        template_name = template_map.get(matched_intent, "general_chat")
        blueprint = BUILTIN_TEMPLATES.get(template_name, BUILTIN_TEMPLATES["general_chat"])

        return best.strategy, blueprint

    def learn_blueprint(self, intent: str, dag: BlueprintDAG,
                        source_dag_id: str = "") -> bool:
        """G2: 执行成功的动态 DAG 沉淀为学习模板（业务流自增长核心）。

        - 只沉淀含 tool 节点的 DAG（纯 pcr/intent 链已有内置模板）
        - 覆盖同意图旧学习模板（新经验替代旧经验）
        - 模板带 provenance（from: dynamic_learn）
        """
        if not intent or dag is None or dag.node_count == 0:
            return False
        if not any(n.chain == "tool" for n in dag.nodes):
            logger.debug("learn_blueprint: skip (no tool node, intent=%s)", intent)
            return False
        import copy
        learned = copy.deepcopy(dag)
        learned.design_rationale = (
            f"LEARNED (from: dynamic_learn, source_dag={source_dag_id or '?'})"
        )
        LEARNED_TEMPLATES[intent] = learned
        # GAP-D5: 生命周期登记（活性状态机原料）
        if self._lifecycle is not None:
            try:
                self._lifecycle.register(intent)
            except Exception as e:
                logger.debug("lifecycle register failed: %s", e)
        # 也进意图权重表（可被 MetaFeedback 调整）
        if intent not in self._strategy_weights:
            self._strategy_weights[intent] = [StrategyWeight("TEMPLATE", 1.0)]
        logger.info("LEARNED template registered: intent=%s nodes=%d",
                     intent, dag.node_count)
        return True

    def update_weight(self, intent: str, strategy: str, score: float):
        """Called by MetaFeedback — adjust strategy weight after execution."""
        if intent not in self._strategy_weights:
            self._strategy_weights[intent] = []
        for w in self._strategy_weights[intent]:
            if w.strategy == strategy:
                w.record(score)
                # Weight = base weight × success_rate
                w.weight = max(0.0, min(2.0, 1.0 * w.success_rate))
                return
        # New strategy for this intent
        sw = StrategyWeight(strategy=strategy, weight=1.0)
        sw.record(score)
        self._strategy_weights[intent].append(sw)

    def builtin_template(self, name: str) -> Optional[BlueprintDAG]:
        return BUILTIN_TEMPLATES.get(name)
