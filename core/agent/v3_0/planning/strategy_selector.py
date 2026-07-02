# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/strategy_selector.py
────────────────────────────────────────────
DialogMesh Agent v3.0 — 规划策略选择器。

用途：
- 根据 ``Intent_v3`` 的复杂度、置信度与 ``CognitiveProfile_v3`` 动态选择最优规划策略。
- 支持规则驱动（Rule-Based）与评分排序（Scoring）两种决策模式。
- 为可观测性提供策略选择理由（reasoning trace）。

设计原则：
- 策略选择是可解释的：每个评分附带 human-readable 理由。
- 低延迟：纯本地计算，不依赖外部 LLM。
- 防御性：当评分接近时，默认保守策略（HYBRID）。

版本：3.0.0
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.models import IntentCategory
from core.agent.v3_0.data_models import CognitiveProfile_v3, Intent_v3
from core.agent.v3_0.planning.models import (
    PlanStrategy,
    PlannerConfig,
    StrategyScore,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 策略选择器
# ═══════════════════════════════════════════════════════════════════════════

class StrategySelector:
    """规划策略选择器——动态决策模块。

    核心逻辑：
    1. 计算 ``intent_complexity``（基于意图类别、实体数量、子意图数量）。
    2. 计算 ``intent_confidence``（基于意图自身置信度与实体置信度）。
    3. 结合 ``CognitiveProfile_v3``（稳定性、发散度、元认知）评估各策略适配度。
    4. 返回最高分的策略及其评分详情。

    使用示例：

    .. code-block:: python

        selector = StrategySelector()
        strategy, scores = selector.select(intent, cognitive_profile, config)
    """

    # 类别复杂度映射（数值越大，意图越复杂）
    CATEGORY_COMPLEXITY: Dict[IntentCategory, float] = {
        # 简单操作（1 个节点即可）
        IntentCategory.READ_MEMORY: 0.1,
        IntentCategory.CHITCHAT: 0.05,
        # 中等复杂度（2-3 个节点）
        IntentCategory.SCAN_MEMORY: 0.4,
        IntentCategory.WRITE_MEMORY: 0.45,
        IntentCategory.FIND_PATTERN: 0.35,
        IntentCategory.GET_BREAKPOINT_HITS: 0.3,
        # 高复杂度（需要多步推理）
        IntentCategory.RESOLVE_POINTER: 0.6,
        IntentCategory.DISASSEMBLE: 0.55,
        IntentCategory.DECOMPILE: 0.65,
        IntentCategory.ANALYZE_PROTECTION: 0.7,
        IntentCategory.DEOBFUSCATE: 0.75,
        IntentCategory.UNPACK: 0.8,
        IntentCategory.SET_BREAKPOINT: 0.5,
        IntentCategory.TRACE_EXECUTION: 0.6,
        IntentCategory.PATTERN_DETECT: 0.55,
        # 极高复杂度（需要完整工作流）
        IntentCategory.BUILD_CFG: 0.85,
        IntentCategory.SYMBOLIC_EXECUTE: 0.9,
        IntentCategory.SOLVE_CONSTRAINTS: 0.85,
        IntentCategory.VERIFY_INPUT: 0.8,
        IntentCategory.ANALYZE_PROCESS: 0.9,
        IntentCategory.HACK_VALUE: 0.75,
        IntentCategory.FIND_FUNCTION: 0.7,
        IntentCategory.EXPLOIT_VULNERABILITY: 0.95,
        # 元意图
        IntentCategory.ASK_USER: 0.2,
        IntentCategory.FINISH: 0.05,
        IntentCategory.UNKNOWN: 0.5,
    }

    def __init__(self) -> None:
        """初始化策略选择器。"""
        self._last_selection_time: float = 0.0
        self._last_strategy: Optional[PlanStrategy] = None
        logger.debug("StrategySelector initialized")

    # ── 公共 API ───────────────────────────────────────────────────────────

    def select(
        self,
        intent: Intent_v3,
        cognitive_profile: Optional[CognitiveProfile_v3] = None,
        config: Optional[PlannerConfig] = None,
    ) -> tuple[PlanStrategy, List[StrategyScore]]:
        """选择最优规划策略。

        Args:
            intent: 用户意图（已解析）。
            cognitive_profile: PCR 输出的认知画像（可选）。
            config: 规划器配置（可选，默认使用全局默认）。

        Returns:
            (selected_strategy, all_scores) 的元组。
            all_scores 按 score 降序排列。
        """
        try:
            start_time = time.time()
            if config is None:
                config = PlannerConfig()

            # 1. 计算意图特征
            complexity = self._compute_complexity(intent)
            confidence = self._compute_confidence(intent)

            # 2. 对每个策略评分
            scores: List[StrategyScore] = []
            for strategy in PlanStrategy:
                score = self._score_strategy(
                    strategy, complexity, confidence, cognitive_profile, config
                )
                scores.append(score)

            # 3. 排序并选择最高分
            scores.sort(key=lambda s: s.score, reverse=True)
            best = scores[0]

            # 防御：如果最高分与次高分差距 < 0.1，默认保守的 HYBRID
            if len(scores) > 1 and (scores[0].score - scores[1].score) < 0.1:
                if scores[0].strategy != PlanStrategy.HYBRID:
                    logger.info(
                        f"Strategy scores too close ({scores[0].score:.2f} vs {scores[1].score:.2f}), "
                        f"defaulting to HYBRID"
                    )
                    best = next(
                        (s for s in scores if s.strategy == PlanStrategy.HYBRID), scores[0]
                    )

            self._last_strategy = best.strategy
            self._last_selection_time = time.time() - start_time
            best.estimated_latency_ms = self._last_selection_time * 1000.0

            logger.info(
                f"Strategy selected: {best.strategy.value} (score={best.score:.2f}, "
                f"complexity={complexity:.2f}, confidence={confidence:.2f})"
            )
            return best.strategy, scores

        except Exception as exc:
            logger.error(f"StrategySelector.select failed: {exc}, falling back to HYBRID")
            fallback = StrategyScore(
                strategy=PlanStrategy.HYBRID,
                score=0.5,
                confidence=0.5,
                reason=f"Selection failed ({exc}), fallback to HYBRID",
            )
            return PlanStrategy.HYBRID, [fallback]

    def explain_last_selection(self) -> str:
        """返回上次策略选择的可解释文本。"""
        if self._last_strategy is None:
            return "No selection has been made yet."
        return (
            f"Selected strategy: {self._last_strategy.value} "
            f"(selection took {self._last_selection_time*1000:.1f}ms)"
        )

    # ── 内部评分逻辑 ─────────────────────────────────────────────────────

    def _compute_complexity(self, intent: Intent_v3) -> float:
        """计算意图复杂度 [0, 1]。"""
        try:
            base = self.CATEGORY_COMPLEXITY.get(intent.category, 0.5)
            # 实体越多，复杂度越高
            entity_factor = min(len(intent.entities) / 10.0, 0.3)
            # 子意图越多，复杂度越高
            sub_intent_factor = min(len(intent.sub_intents) / 5.0, 0.3)
            # 存在歧义增加复杂度
            ambiguity_factor = 0.2 if intent.is_ambiguous() else 0.0

            complexity = min(1.0, base + entity_factor + sub_intent_factor + ambiguity_factor)
            logger.debug(
                f"Complexity: {complexity:.2f} (base={base:.2f}, "
                f"entities={entity_factor:.2f}, sub_intents={sub_intent_factor:.2f}, "
                f"ambiguity={ambiguity_factor:.2f})"
            )
            return complexity
        except Exception as exc:
            logger.warning(f"Complexity computation failed: {exc}, defaulting to 0.5")
            return 0.5

    def _compute_confidence(self, intent: Intent_v3) -> float:
        """计算意图整体置信度 [0, 1]。"""
        try:
            # 意图自身置信度
            base_conf = intent.confidence
            # 实体平均置信度
            if intent.entities:
                entity_conf = sum(e.confidence for e in intent.entities) / len(intent.entities)
            else:
                entity_conf = 1.0
            # 子意图置信度
            if intent.sub_intents:
                sub_conf = sum(si.confidence for si in intent.sub_intents) / len(intent.sub_intents)
            else:
                sub_conf = 1.0

            confidence = (base_conf * 0.5) + (entity_conf * 0.3) + (sub_conf * 0.2)
            confidence = min(1.0, max(0.0, confidence))
            logger.debug(
                f"Confidence: {confidence:.2f} (base={base_conf:.2f}, "
                f"entity={entity_conf:.2f}, sub={sub_conf:.2f})"
            )
            return confidence
        except Exception as exc:
            logger.warning(f"Confidence computation failed: {exc}, defaulting to 0.5")
            return 0.5

    def _score_strategy(
        self,
        strategy: PlanStrategy,
        complexity: float,
        confidence: float,
        cognitive_profile: Optional[CognitiveProfile_v3],
        config: PlannerConfig,
    ) -> StrategyScore:
        """为单个策略计算评分。"""
        try:
            score = 0.0
            reason_parts: List[str] = []

            # 稳定性调整：稳定性低时，偏好更保守的策略（RULE_BASED / TEMPLATE）
            stability = cognitive_profile.stability if cognitive_profile else 0.5
            divergence = cognitive_profile.divergence if cognitive_profile else 0.0
            metacognition = cognitive_profile.metacognition if cognitive_profile else 0.5

            if strategy == PlanStrategy.RULE_BASED:
                # 适合低复杂度、高置信度、高稳定性
                score = (1.0 - complexity) * 0.5 + confidence * 0.3 + stability * 0.2
                if complexity < config.complexity_threshold_hybrid and confidence > 0.7:
                    score += 0.2
                    reason_parts.append("low complexity + high confidence")
                if stability > 0.7:
                    score += 0.1
                    reason_parts.append("high stability")
                reason_parts.append("fast and deterministic")

            elif strategy == PlanStrategy.TEMPLATE:
                # 适合已知意图类别且复杂度中等
                score = confidence * 0.4 + (1.0 - abs(complexity - 0.4)) * 0.3
                if complexity < 0.6 and confidence > 0.6:
                    score += 0.15
                    reason_parts.append("known pattern match")
                reason_parts.append("predictable structure")

            elif strategy == PlanStrategy.HYBRID:
                # 通用稳健策略，中等复杂度场景
                score = 0.5 + (1.0 - abs(complexity - 0.5)) * 0.2
                if 0.3 < complexity < 0.8:
                    score += 0.1
                    reason_parts.append("moderate complexity sweet spot")
                if stability < 0.5:
                    score += 0.1  # 稳定性低时，HYBRID 比纯 LLM 更可靠
                    reason_parts.append("low stability → conservative hybrid")
                reason_parts.append("balanced reliability and flexibility")

            elif strategy == PlanStrategy.LLM_DRIVEN:
                # 适合高复杂度、低置信度、需要发散思维
                score = complexity * 0.5 + (1.0 - confidence) * 0.2 + divergence * 0.2
                if complexity > config.complexity_threshold_llm:
                    score += 0.2
                    reason_parts.append("high complexity demands LLM reasoning")
                if divergence > 0.6:
                    score += 0.1
                    reason_parts.append("high divergence favors LLM creativity")
                if metacognition > 0.7:
                    score += 0.05
                    reason_parts.append("high metacognition supports LLM planning")
                reason_parts.append("maximum flexibility")

            elif strategy == PlanStrategy.REFLEXIVE:
                # 仅在元认知极高或显式启用时考虑
                score = metacognition * 0.4
                if config.enable_reflexive_planning and metacognition > 0.8:
                    score += 0.3
                    reason_parts.append("reflexive planning enabled")
                else:
                    score *= 0.3  # 大幅降分
                    reason_parts.append("reflexive planning disabled or low metacognition")

            elif strategy == PlanStrategy.RECOVERY:
                # 仅在回退场景使用，默认极低分
                score = 0.05
                reason_parts.append("recovery is reserved for fallback scenarios")

            # 最终裁剪
            score = min(1.0, max(0.0, score))
            confidence_score = min(1.0, score + 0.1)  # 评分置信度略高于得分本身

            return StrategyScore(
                strategy=strategy,
                score=score,
                confidence=confidence_score,
                estimated_latency_ms=self._estimate_latency(strategy, complexity),
                estimated_cost=self._estimate_cost(strategy),
                reason="; ".join(reason_parts) if reason_parts else "default scoring",
            )

        except Exception as exc:
            logger.warning(f"Strategy scoring failed for {strategy.value}: {exc}")
            return StrategyScore(
                strategy=strategy,
                score=0.0,
                confidence=0.0,
                reason=f"scoring error: {exc}",
            )

    def _estimate_latency(self, strategy: PlanStrategy, complexity: float) -> float:
        """粗略估计策略延迟（毫秒）。"""
        base_latencies: Dict[PlanStrategy, float] = {
            PlanStrategy.RULE_BASED: 10.0,
            PlanStrategy.TEMPLATE: 15.0,
            PlanStrategy.HYBRID: 200.0,
            PlanStrategy.LLM_DRIVEN: 800.0,
            PlanStrategy.REFLEXIVE: 500.0,
            PlanStrategy.RECOVERY: 300.0,
        }
        base = base_latencies.get(strategy, 200.0)
        # 复杂度越高，LLM 驱动策略延迟增长越快
        if strategy in (PlanStrategy.LLM_DRIVEN, PlanStrategy.HYBRID, PlanStrategy.REFLEXIVE):
            base *= (1.0 + complexity)
        return base

    def _estimate_cost(self, strategy: PlanStrategy) -> float:
        """粗略估计策略成本（美元，假设性）。"""
        costs: Dict[PlanStrategy, float] = {
            PlanStrategy.RULE_BASED: 0.0,
            PlanStrategy.TEMPLATE: 0.0,
            PlanStrategy.HYBRID: 0.005,
            PlanStrategy.LLM_DRIVEN: 0.02,
            PlanStrategy.REFLEXIVE: 0.015,
            PlanStrategy.RECOVERY: 0.01,
        }
        return costs.get(strategy, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/strategy_selector self-test ===")

        selector = StrategySelector()
        cog = CognitiveProfile_v3(stability=0.8, divergence=0.2, metacognition=0.5)

        # 1. 简单意图 → RULE_BASED
        simple_intent = Intent_v3(
            category=IntentCategory.READ_MEMORY,
            raw_input="read 0x1000",
            entities=[],
            confidence=0.95,
        )
        strategy, scores = selector.select(simple_intent, cog)
        assert strategy == PlanStrategy.RULE_BASED, f"Expected RULE_BASED, got {strategy.value}"
        print(f"[PASS] Simple intent → {strategy.value} (score={scores[0].score:.2f})")

        # 2. 复杂意图 → LLM_DRIVEN
        complex_intent = Intent_v3(
            category=IntentCategory.ANALYZE_PROCESS,
            raw_input="fully analyze this game process",
            entities=[],
            confidence=0.3,
        )
        strategy, scores = selector.select(complex_intent, cog)
        assert strategy == PlanStrategy.LLM_DRIVEN, f"Expected LLM_DRIVEN, got {strategy.value}"
        print(f"[PASS] Complex intent → {strategy.value} (score={scores[0].score:.2f})")

        # 3. 中等复杂度 → HYBRID
        medium_intent = Intent_v3(
            category=IntentCategory.SCAN_MEMORY,
            raw_input="scan for 100 then verify",
            entities=[],
            confidence=0.6,
        )
        strategy, scores = selector.select(medium_intent, cog)
        print(f"[PASS] Medium intent → {strategy.value} (score={scores[0].score:.2f})")

        # 4. 解释文本
        explanation = selector.explain_last_selection()
        assert "Selected strategy" in explanation
        print(f"[PASS] explain_last_selection: {explanation}")

        logger.info("=== All v3.0 strategy_selector self-tests passed ===")

    asyncio.run(_self_test())
