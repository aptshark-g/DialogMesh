# core/agent/coordinator/mode_router.py
"""模式路由器 —— 根据复杂度自动选择处理层级。

三级架构：
- rule（规则）：复杂度 0-3，本地计算，<1ms，零成本
- small_model（本地小模型）：复杂度 4-7，本地推理，~20-100ms，零API成本
- remote_llm（远程大模型）：复杂度 8-10，云端调用，~200ms-2s，有API成本

路由策略：
1. 先评估复杂度
2. 检查资源可用性（小模型是否在线）
3. 根据用户偏好/成本约束调整
4. 如果选定模式不可用，自动降级

降级链：remote_llm → small_model → rule（总是可降级到规则）
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

try:
    from core.agent.coordinator.complexity_evaluator import (
        ComplexityEvaluator,
        ComplexityScore,
    )
    from core.agent.coordinator.small_model_client import SmallModelClient
except ImportError:
    ComplexityEvaluator = None  # type: ignore
    ComplexityScore = None  # type: ignore
    SmallModelClient = None  # type: ignore

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """处理模式枚举。"""
    RULE = "rule"                  # 纯规则模式
    SMALL_MODEL = "small_model"    # 本地小模型
    REMOTE_LLM = "remote_llm"      # 远程大模型


class ModeRouter:
    """模式路由器：自动选择最优处理层级。"""

    # 复杂度阈值
    RULE_MAX = 3          # 0-3 → 规则
    SMALL_MODEL_MAX = 7   # 4-7 → 小模型
    # 8-10 → 远程大模型

    def __init__(
        self,
        small_model_client: Optional[Any] = None,
        force_mode: Optional[str] = None,        # 强制模式（调试用）
        disable_remote: bool = False,            # 禁用远程LLM（纯本地）
        disable_small_model: bool = False,       # 禁用小模型（纯规则+远程）
        cost_budget: Optional[str] = None,       # 成本预算：free/standard/premium
    ):
        self.evaluator = ComplexityEvaluator() if ComplexityEvaluator else None
        self.small_model_client = small_model_client
        self.force_mode = force_mode
        self.disable_remote = disable_remote
        self.disable_small_model = disable_small_model
        self.cost_budget = cost_budget or "standard"

        # 统计
        self._route_stats: Dict[str, int] = {
            "rule": 0,
            "small_model": 0,
            "remote_llm": 0,
            "fallback": 0,
        }

    def decide(
        self,
        query: str,
        intent_label: Optional[str] = None,
        history_length: int = 0,
        cohesion_score: Optional[float] = None,
        entity_count: Optional[int] = None,
        threshold_profile: Optional[Any] = None,
    ) -> ProcessingMode:
        """决定处理模式。

        Args:
            query: 用户输入
            intent_label: 意图标签
            history_length: 历史轮次
            cohesion_score: 粘合度分数
            entity_count: 实体数量
            threshold_profile: 自适应阈值画像（可选）

        返回的 ProcessingMode 保证可用（如果不可降级，降到 rule）
        """
        # 1. 强制模式
        if self.force_mode:
            return self._resolve_mode(self.force_mode)

        # 2. 评估复杂度（支持自适应阈值）
        if self.evaluator:
            score = self.evaluator.evaluate(
                query, intent_label, history_length, cohesion_score, entity_count,
                threshold_profile=threshold_profile,
            )
        else:
            # 简单 fallback 评估
            score = ComplexityScore(
                total=1 if len(query) < 30 else 3,
                raw_total=1 if len(query) < 30 else 3,
                length_score=0, entity_score=0, intent_score=0,
                history_score=0, cohesion_score=0,
                ambiguity_score=0, task_switch_score=0, multi_intent_score=0,
            )

        complexity = score.total
        raw_complexity = score.raw_total if hasattr(score, 'raw_total') else complexity
        logger.debug(f"Complexity score: raw={raw_complexity} → weighted={complexity} {score.to_dict()}")

        # 3. 成本预算调整
        adjusted_complexity = complexity
        if self.cost_budget == "free":
            # 免费模式：尽量用规则，最多到小模型
            adjusted_complexity = min(complexity, 5)
        elif self.cost_budget == "premium":
            # 高级模式：允许更高复杂度才用远程
            adjusted_complexity = max(0, complexity - 2)

        # 4. 根据复杂度选择模式（支持自适应阈值）
        if threshold_profile is not None and hasattr(threshold_profile, 'get_mode'):
            # 使用自适应阈值判断
            mode_str = threshold_profile.get_mode(adjusted_complexity)
            mode = ProcessingMode(mode_str) if mode_str in ["rule", "small_model", "remote_llm"] else ProcessingMode.RULE
        else:
            # 使用固定阈值
            if adjusted_complexity <= self.RULE_MAX:
                mode = ProcessingMode.RULE
            elif adjusted_complexity <= self.SMALL_MODEL_MAX:
                mode = ProcessingMode.SMALL_MODEL
            else:
                mode = ProcessingMode.REMOTE_LLM

        # 5. 可用性检查与降级
        final_mode = self._check_and_fallback(mode)

        self._route_stats[final_mode.value] += 1
        logger.info(
            f"Mode routed: {mode.value} → {final_mode.value} "
            f"(complexity={complexity}, adjusted={adjusted_complexity}, "
            f"cost_budget={self.cost_budget}, adaptive={threshold_profile is not None})"
        )
        return final_mode

    def _resolve_mode(self, mode_str: str) -> ProcessingMode:
        """解析模式字符串。"""
        mode_map = {
            "rule": ProcessingMode.RULE,
            "small_model": ProcessingMode.SMALL_MODEL,
            "remote_llm": ProcessingMode.REMOTE_LLM,
            "fast": ProcessingMode.RULE,
            "smart": ProcessingMode.SMALL_MODEL,
            "deep": ProcessingMode.REMOTE_LLM,
        }
        mode = mode_map.get(mode_str.lower(), ProcessingMode.RULE)
        return self._check_and_fallback(mode)

    def _check_and_fallback(self, mode: ProcessingMode) -> ProcessingMode:
        """检查模式可用性，必要时降级。"""
        if mode == ProcessingMode.REMOTE_LLM:
            if self.disable_remote:
                mode = ProcessingMode.SMALL_MODEL
                self._route_stats["fallback"] += 1
        if mode == ProcessingMode.SMALL_MODEL:
            if self.disable_small_model:
                mode = ProcessingMode.RULE
                self._route_stats["fallback"] += 1
            elif self.small_model_client and not self.small_model_client.is_available:
                logger.warning("Small model unavailable, falling back to rule")
                mode = ProcessingMode.RULE
                self._route_stats["fallback"] += 1
        # RULE 总是可用
        return mode

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计。"""
        total = sum(self._route_stats.values())
        return {
            "total_routes": total,
            "rule": self._route_stats["rule"],
            "small_model": self._route_stats["small_model"],
            "remote_llm": self._route_stats["remote_llm"],
            "fallbacks": self._route_stats["fallback"],
            "force_mode": self.force_mode,
            "disable_remote": self.disable_remote,
            "disable_small_model": self.disable_small_model,
            "cost_budget": self.cost_budget,
        }
