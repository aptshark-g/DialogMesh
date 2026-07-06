# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/fusion_engine.py
++++++
DialogMesh v3.0 FusionEngine — 认知双工加权融合引擎。

职责：
  - 将算法引擎输出与 LLM 引擎输出加权融合
  - 提供多种融合策略（置信度优先、加权平均、冲突降级、澄清请求）
  - 冲突检测与自动解决（MLLM-S-01 降级规范）

设计原则：
  - 无状态：每个 fuse() 调用独立，便于测试
  - 确定性：相同输入产生相同融合决策
  - 正交性：融合逻辑不依赖具体 LLM 或算法实现细节

对应工程文档：ENGINEERING_MULTILAYER_LLM.md §6
版本：3.0.0
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 枚举与数据模型
# ============================================================

class FusionSource(str, Enum):
    """融合结果来源 — 认知双工的输出源。"""
    ALGORITHM = "algorithm"
    LLM = "llm"
    FUSED = "fused"
    FALLBACK = "fallback"
    ALGORITHM_CONFLICT_RESOLVED = "algorithm_conflict_resolved"
    LLM_CONFLICT_RESOLVED = "llm_conflict_resolved"


class FusionStrategy(str, Enum):
    """融合策略选择。"""
    CONFIDENCE_WEIGHTED = "confidence_weighted"       # 按置信度加权
    ALGORITHM_PREFERRED = "algorithm_preferred"        # 算法优先（LLM fallback）
    LLM_PREFERRED = "llm_preferred"                    # LLM 优先（算法 fallback）
    CONSERVATIVE = "conservative"                      # 保守降级（请求澄清）
    VOTE = "vote"                                       # 投票融合（当有多个候选）


class FusionResult:
    """融合结果。"""

    def __init__(
        self,
        output: Optional[Dict[str, Any]] = None,
        confidence: float = 0.0,
        source: FusionSource = FusionSource.FALLBACK,
        llm_pending: bool = False,
        clarification_required: bool = False,
        conflict_detected: bool = False,
        resolved_nodes: Optional[List[str]] = None,
        fallback_reason: Optional[str] = None,
    ):
        self.output = output or {}
        self.confidence = confidence
        self.source = source
        self.llm_pending = llm_pending
        self.clarification_required = clarification_required
        self.conflict_detected = conflict_detected
        self.resolved_nodes = resolved_nodes or []
        self.fallback_reason = fallback_reason


# ============================================================
# 冲突检测器
# ============================================================

class ConflictDetector:
    """检测算法结果与 LLM 结果之间的冲突。"""

    def detect(
        self,
        algo_output: Dict[str, Any],
        llm_output: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], float]:
        """检测冲突并返回 (has_conflict, conflict_description, severity)。

        Severity: 0.0 (无冲突) ~ 1.0 (严重冲突)
        """
        conflicts: List[Tuple[str, float]] = []

        # 1. 意图类别冲突
        cat_a = algo_output.get("intent_inference", {}).get("primary_intent")
        cat_b = llm_output.get("intent_inference", {}).get("primary_intent")
        if cat_a and cat_b and cat_a != cat_b:
            conflicts.append((f"intent_category conflict: {cat_a} vs {cat_b}", 0.8))

        # 2. 置信度冲突
        conf_a = algo_output.get("confidence", 0.5)
        conf_b = llm_output.get("confidence", 0.5)
        if abs(conf_a - conf_b) > 0.4:
            conflicts.append((f"confidence gap: {conf_a:.2f} vs {conf_b:.2f}", 0.5))

        # 3. 实体冲突（如果都存在且不一致）
        entities_a = set(algo_output.get("intent_inference", {}).get("implied_entities", []))
        entities_b = set(llm_output.get("intent_inference", {}).get("implied_entities", []))
        if entities_a and entities_b:
            overlap = entities_a & entities_b
            if not overlap and (len(entities_a) > 0 and len(entities_b) > 0):
                conflicts.append((f"entity mismatch: {entities_a} vs {entities_b}", 0.6))
            elif not overlap:
                pass  # 至少一方为空，不视为冲突

        # 4. 期望模式冲突
        exp_a = algo_output.get("expectation_inference", {}).get("primary")
        exp_b = llm_output.get("expectation_inference", {}).get("primary")
        if exp_a and exp_b and exp_a != exp_b:
            conflicts.append((f"expectation mismatch: {exp_a} vs {exp_b}", 0.3))

        if not conflicts:
            return False, None, 0.0

        # 取最严重的冲突
        worst = max(conflicts, key=lambda c: c[1])
        return True, worst[0], worst[1]


# ============================================================
# 融合引擎主类
# ============================================================

class FusionEngine:
    """融合引擎 — 将算法结果和 LLM 结果加权融合。

    调度策略（参照工程文档 §6）：
    1. LLM 完全失败 → 强制选择算法输出（MLLM-S-01 降级）
    2. 算法高置信 + LLM 低置信 → 算法输出（快速通道）
    3. 算法低置信 + LLM 高置信 → LLM 输出
    4. 两者接近 → 加权融合（同时检测冲突）
    5. 两者都低 → 保守降级（请求澄清）
    """

    def __init__(
        self,
        high_threshold: float = 0.85,
        low_threshold: float = 0.60,
        llm_weight: float = 0.5,
        default_strategy: FusionStrategy = FusionStrategy.CONFIDENCE_WEIGHTED,
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.llm_weight = llm_weight
        self.conflict_detector = ConflictDetector()
        self.default_strategy = default_strategy

    def fuse(
        self,
        algo_result: Optional[Dict[str, Any]],
        llm_result: Optional[Dict[str, Any]],
        llm_confidence: float = 0.0,
        context_data: Optional[Dict[str, Any]] = None,
        strategy: Optional[FusionStrategy] = None,
    ) -> FusionResult:
        """融合算法结果与 LLM 结果。"""
        strategy = strategy or self.default_strategy

        # 情景 1: LLM 完全失败 — 强制选择算法
        if llm_result is None and algo_result is not None:
            return self._fallback_to_algorithm(algo_result, "llm_failed")

        # 情景 2: 两者均失败
        if llm_result is None and algo_result is None:
            return FusionResult(
                output=None,
                confidence=0.0,
                source=FusionSource.FALLBACK,
                clarification_required=True,
                fallback_reason="both_failed",
            )

        # 情景 3: 仅算法不可用
        if algo_result is None and llm_result is not None:
            return FusionResult(
                output=llm_result,
                confidence=llm_confidence,
                source=FusionSource.LLM,
            )

        # 双方都有结果
        algo = algo_result or {}
        llm = llm_result or {}
        c_a = algo.get("confidence", 0.0)
        c_b = llm_confidence if llm_confidence > 0 else llm.get("confidence", 0.0)

        # 检测冲突
        has_conflict, conflict_desc, severity = self.conflict_detector.detect(algo, llm)

        # 按策略融合
        if strategy == FusionStrategy.ALGORITHM_PREFERRED:
            return self._fuse_algorithm_preferred(algo, llm, c_a, c_b, has_conflict, severity)
        elif strategy == FusionStrategy.LLM_PREFERRED:
            return self._fuse_llm_preferred(algo, llm, c_a, c_b, has_conflict, severity)
        elif strategy == FusionStrategy.CONSERVATIVE:
            return self._fuse_conservative(algo, llm, c_a, c_b)
        else:
            return self._fuse_confidence_weighted(algo, llm, c_a, c_b, has_conflict, severity, conflict_desc)

    def _fallback_to_algorithm(self, algo_result: Dict[str, Any], reason: str) -> FusionResult:
        """MLLM-S-01: LLM 故障时回退到算法输出。"""
        confidence = algo_result.get("confidence", 0.5)
        return FusionResult(
            output=algo_result,
            confidence=confidence,
            source=FusionSource.ALGORITHM,
            fallback_reason=reason,
        )

    def _fuse_confidence_weighted(
        self,
        algo: Dict[str, Any],
        llm: Dict[str, Any],
        c_a: float,
        c_b: float,
        has_conflict: bool,
        severity: float,
        conflict_desc: str = "",
    ) -> FusionResult:
        """置信度加权融合（默认策略）。"""
        # 算法高置信 + LLM 低置信 → 算法输出
        if c_a > self.high_threshold and c_b < self.low_threshold:
            return FusionResult(
                output=algo,
                confidence=c_a,
                source=FusionSource.ALGORITHM,
            )

        # 算法低置信 + LLM 高置信 → LLM 输出
        if c_a < self.low_threshold and c_b > self.high_threshold:
            return FusionResult(
                output=llm,
                confidence=c_b,
                source=FusionSource.LLM,
            )

        # 两者都高或中等 → 加权融合
        if c_a >= self.low_threshold or c_b >= self.low_threshold:
            if has_conflict:
                # 冲突存在：选择置信度较高者，但降低置信度
                if c_a > c_b:
                    source = FusionSource.ALGORITHM_CONFLICT_RESOLVED
                    return FusionResult(
                        output=algo,
                        confidence=c_a * 0.8,
                        source=source,
                        conflict_detected=True,
                        fallback_reason=conflict_desc or "unknown conflict",
                    )
                else:
                    source = FusionSource.LLM_CONFLICT_RESOLVED
                    return FusionResult(
                        output=llm,
                        confidence=c_b * 0.8,
                        source=source,
                        conflict_detected=True,
                        fallback_reason=conflict_desc or "unknown conflict",
                    )

            # 无冲突，加权融合
            weight_a = c_a * (1 - self.llm_weight)
            weight_b = c_b * self.llm_weight
            total_weight = weight_a + weight_b
            if total_weight == 0:
                fused_confidence = 0.0
            else:
                fused_confidence = (c_a * weight_a + c_b * weight_b) / total_weight

            # 合并输出（LLM 优先覆盖）
            fused_output = dict(algo)
            for k, v in llm.items():
                if isinstance(v, dict) and k in fused_output and isinstance(fused_output[k], dict):
                    fused_output[k].update(v)
                else:
                    fused_output[k] = v

            return FusionResult(
                output=fused_output,
                confidence=fused_confidence,
                source=FusionSource.FUSED,
            )

        # 两者都低 → 保守降级
        return self._fuse_conservative(algo, llm, c_a, c_b)

    def _fuse_algorithm_preferred(
        self,
        algo: Dict[str, Any],
        llm: Dict[str, Any],
        c_a: float,
        c_b: float,
        has_conflict: bool,
        severity: float,
    ) -> FusionResult:
        """算法优先策略。"""
        if has_conflict:
            return FusionResult(
                output=algo,
                confidence=c_a * self.low_threshold,
                source=FusionSource.ALGORITHM_CONFLICT_RESOLVED,
                conflict_detected=True,
            )
        weighted = self._merge_dicts(algo, llm, algo_weight=0.7, llm_weight=0.3)
        return FusionResult(
            output=weighted,
            confidence=c_a * 0.7 + c_b * 0.3,
            source=FusionSource.FUSED,
        )

    def _fuse_llm_preferred(
        self,
        algo: Dict[str, Any],
        llm: Dict[str, Any],
        c_a: float,
        c_b: float,
        has_conflict: bool,
        severity: float,
    ) -> FusionResult:
        """LLM 优先策略。"""
        if has_conflict:
            return FusionResult(
                output=llm,
                confidence=c_b * self.low_threshold,
                source=FusionSource.LLM_CONFLICT_RESOLVED,
                conflict_detected=True,
            )
        weighted = self._merge_dicts(algo, llm, algo_weight=0.3, llm_weight=0.7)
        return FusionResult(
            output=weighted,
            confidence=c_a * 0.3 + c_b * 0.7,
            source=FusionSource.FUSED,
        )

    def _fuse_conservative(
        self,
        algo: Dict[str, Any],
        llm: Dict[str, Any],
        c_a: float,
        c_b: float,
    ) -> FusionResult:
        """保守降级：两者都低置信时请求澄清。"""
        return FusionResult(
            output=algo if c_a >= c_b else llm,
            confidence=max(c_a, c_b) * 0.5,
            source=FusionSource.FALLBACK,
            clarification_required=True,
            fallback_reason="low_confidence_both",
        )

    def _merge_dicts(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any],
        algo_weight: float = 0.5,
        llm_weight: float = 0.5,
    ) -> Dict[str, Any]:
        """递归合并两个字典，LLM 侧覆盖算法侧。"""
        result = {}
        all_keys = set(base.keys()) | set(override.keys())
        for key in all_keys:
            v_a = base.get(key)
            v_b = override.get(key)
            if isinstance(v_a, dict) and isinstance(v_b, dict):
                result[key] = self._merge_dicts(v_a, v_b, algo_weight, llm_weight)
            elif isinstance(v_a, (int, float)) and isinstance(v_b, (int, float)):
                result[key] = algo_weight * v_a + llm_weight * v_b
            else:
                result[key] = v_b if v_b is not None else v_a
        return result


__all__ = [
    "FusionEngine",
    "FusionResult",
    "FusionSource",
    "FusionStrategy",
    "ConflictDetector",
]
