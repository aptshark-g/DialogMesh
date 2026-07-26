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
# 5 Built-in Blueprint Templates (§十, §0.2)
# ═══════════════════════════════════════════════

BUILTIN_TEMPLATES: Dict[str, BlueprintDAG] = {}

# Template 1: code_analysis — TEMPLATE (确定性)
BUILTIN_TEMPLATES["code_analysis"] = BlueprintDAG(
    nodes=[
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
        _make_node("context_2", "context", priority=1),
        _make_node("subgraph_3", "subgraph", priority=1),
        _make_node("llm_reply_4", "llm_reply", priority=2),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route"),
        _make_edge("intent_1", "context_2", "intent_context"),
        _make_edge("context_2", "subgraph_3", "assembled_context"),
        _make_edge("subgraph_3", "llm_reply_4", "compiled_subgraph"),
        _make_edge("intent_1", "llm_reply_4", "intent_context"),
        _make_edge("pcr_0", "llm_reply_4", "compass"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale="标准代码分析路径: 路由→意图→上下文→子图→回复",
)

# Template 2: general_chat — HYBRID (模板基础 + LLM可覆盖)
BUILTIN_TEMPLATES["general_chat"] = BlueprintDAG(
    nodes=[
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
        _make_node("profile_2", "profile", priority=1),
        _make_node("llm_reply_3", "llm_reply", priority=2),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route"),
        _make_edge("intent_1", "profile_2", "intent_context"),
        _make_edge("profile_2", "llm_reply_3", "profile_text"),
        _make_edge("intent_1", "llm_reply_3", "intent_context"),
    ],
    strategy="HYBRID",
    confidence=0.9,
    design_rationale="通用对话: 路由→意图→画像→回复。LLM可加context/subgraph节点",
)

# Template 3: task_planning — HYBRID
BUILTIN_TEMPLATES["task_planning"] = BlueprintDAG(
    nodes=[
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
        _make_node("context_2", "context", priority=1),
        _make_node("subgraph_3", "subgraph", priority=1),
        _make_node("profile_4", "profile", priority=1),
        _make_node("llm_reply_5", "llm_reply", priority=2),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route"),
        _make_edge("intent_1", "context_2", "intent_context"),
        _make_edge("context_2", "subgraph_3", "assembled_context"),
        _make_edge("intent_1", "profile_4", "intent_context"),
        _make_edge("subgraph_3", "llm_reply_5", "compiled_subgraph"),
        _make_edge("profile_4", "llm_reply_5", "profile_text"),
        _make_edge("intent_1", "llm_reply_5", "intent_context"),
        _make_edge("pcr_0", "llm_reply_5", "compass"),
    ],
    strategy="HYBRID",
    confidence=0.85,
    design_rationale="任务规划: 全链+画像→生成task_graph。LLM可调整节点顺序",
)

# Template 4: data_search — TEMPLATE
BUILTIN_TEMPLATES["data_search"] = BlueprintDAG(
    nodes=[
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
        _make_node("llm_reply_2", "llm_reply", priority=1),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route"),
        _make_edge("pcr_0", "llm_reply_2", "compass"),
        _make_edge("intent_1", "llm_reply_2", "intent_context"),
    ],
    strategy="TEMPLATE",
    confidence=1.0,
    design_rationale="快速搜索: 路由→意图→直接回复(跳过context/subgraph加速)",
)

# Template 5: causal_reasoning — LLM_DRIVEN (LLM 全权构建)
BUILTIN_TEMPLATES["causal_reasoning"] = BlueprintDAG(
    nodes=[
        _make_node("pcr_0", "pcr", priority=0),
        _make_node("intent_1", "intent", priority=0),
    ],
    edges=[
        _make_edge("pcr_0", "intent_1", "route"),
    ],
    strategy="LLM_DRIVEN",
    confidence=0.0,  # No base confidence — LLM fills the rest
    design_rationale="因果推理: LLM 全权构建完整DAG。PlanGate checkpoint 必须审核。",
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

        # Initialize with reasonable defaults
        self._init_defaults()

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

    def match(self, intent: str) -> Tuple[str, BlueprintDAG]:
        """Match intent → best strategy + blueprint template.

        Returns (strategy_name, blueprint_dag).
        Falls back to general_chat HYBRID if no match.
        """
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
        }
        template_name = template_map.get(matched_intent, "general_chat")
        blueprint = BUILTIN_TEMPLATES.get(template_name, BUILTIN_TEMPLATES["general_chat"])

        return best.strategy, blueprint

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
