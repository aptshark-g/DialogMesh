# core/agent/user_engine/consistency_checker.py
"""一致性校验器 —— 跨轮行为一致性验证，降低对抗性输入的权重。

核心思路：
- 单轮提取：从当前查询提取特征（可能被对抗性输入误导）
- 跨轮校验：比较多轮实际行为 vs 自我描述，采信行为而非声明

适用场景：
- 用户自称 "expert" 但行为是新手 → 采信行为
- 用户自称 "beginner" 但查询很复杂 → 采信行为
- 用户说 "我很耐心" 但频繁催促 → 采信催促行为

使用方式：
    checker = ConsistencyChecker()
    
    # 每轮调用
    turns = [...]  # 最近 N 轮 Turn
    single_features = user_extractor.extract(query)  # 单轮提取
    validated = checker.validate(single_features, turns)
    user_profile.update_from_dict(validated)  # 更新画像
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.context_manager.turn import Turn
from core.agent.coordinator.complexity_evaluator import ComplexityEvaluator

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyScore:
    """一致性校验结果。"""
    tech_level: str = "unknown"
    tech_confidence: float = 0.5
    patience_level: str = "neutral"
    patience_confidence: float = 0.5
    style: str = "unknown"
    style_confidence: float = 0.5
    is_consistent: bool = True  # 是否一致
    notes: List[str] = field(default_factory=list)


class ConsistencyChecker:
    """跨轮行为一致性校验器。"""

    # 复杂度 → 技术水平映射
    COMPLEXITY_TO_LEVEL = {
        0: "beginner",
        1: "beginner",
        2: "beginner",
        3: "intermediate",
        4: "intermediate",
        5: "intermediate",
        6: "expert",
        7: "expert",
        8: "expert",
        9: "expert",
        10: "expert",
    }

    # 自我描述关键词 → 技术水平
    SELF_DESCRIBED_LEVEL = {
        "expert": ["expert", "专家", "精通", "资深", "master", "proficient", "advanced"],
        "intermediate": ["intermediate", "中级", "熟悉", "熟练", "intermediate"],
        "beginner": ["beginner", "新手", "初学", "入门", "starter", "novice"],
    }

    # 耐心关键词
    PATIENCE_KEYWORDS = {
        "impatient": ["快点", "赶紧", "急", " hurry", "asap", "快点", "快点快点"],
        "patient": ["慢慢", "详细", "不急", "take your time", "no rush"],
    }

    def __init__(self, min_history: int = 3, window_size: int = 5):
        self.min_history = min_history  # 最少需要多少轮才能做一致性校验
        self.window_size = window_size  # 校验窗口大小
        self.evaluator = ComplexityEvaluator()

    def validate(self, single_features: Dict[str, Any], turns: List[Turn]) -> Dict[str, Any]:
        """校验单轮特征与历史行为的一致性。

        Args:
            single_features: 单轮提取的特征（如 {"tech_level": "expert", ...}）
            turns: 最近 N 轮 Turn（含 raw_query）

        Returns:
            校验后的特征（修正不一致的部分）
        """
        result = dict(single_features)  # 复制，不修改原始

        if len(turns) < self.min_history:
            # 历史不足，直接采信单轮（但降低置信度）
            result["consistency_checked"] = False
            result["consistency_confidence"] = 0.5
            return result

        # 1. 技术水平一致性校验
        tech_validated = self._check_tech_consistency(single_features, turns)
        result["tech_level"] = tech_validated.tech_level
        result["tech_confidence"] = tech_validated.tech_confidence

        # 2. 耐心一致性校验
        patience_validated = self._check_patience_consistency(single_features, turns)
        result["patience_level"] = patience_validated.patience_level
        result["patience_confidence"] = patience_validated.patience_confidence

        # 3. 风格一致性校验
        style_validated = self._check_style_consistency(single_features, turns)
        result["style"] = style_validated.style
        result["style_confidence"] = style_validated.style_confidence

        result["consistency_checked"] = True
        result["is_consistent"] = tech_validated.is_consistent
        result["consistency_notes"] = tech_validated.notes + patience_validated.notes + style_validated.notes

        return result

    # ── 子校验器 ─────────────────────────────────────────────────

    def _check_tech_consistency(self, single_features: Dict[str, Any], turns: List[Turn]) -> ConsistencyScore:
        """检查技术水平的一致性：自我描述 vs 实际行为。"""
        notes = []

        # 提取自我描述（从单轮特征）
        self_described = single_features.get("tech_level", "unknown")

        # 提取实际行为（从历史查询复杂度）
        actual_levels = []
        for turn in turns:
            complexity = self.evaluator.evaluate(turn.raw_query).total
            level = self.COMPLEXITY_TO_LEVEL.get(complexity, "unknown")
            actual_levels.append(level)

        # 行为统计
        if not actual_levels:
            return ConsistencyScore(tech_level=self_described, tech_confidence=0.5, notes=["无历史数据"])

        behavior_mode = Counter(actual_levels).most_common(1)[0]
        behavior_level = behavior_mode[0]
        behavior_ratio = behavior_mode[1] / len(actual_levels)

        # 一致性判断
        if self_described == "unknown":
            # 无自我描述，采信行为
            return ConsistencyScore(
                tech_level=behavior_level,
                tech_confidence=0.6,
                notes=[f"无自我描述，采信行为推断: {behavior_level}"],
            )

        # 检查自我描述关键词（从 raw_query 提取）
        self_described_from_query = self._extract_self_described_level(turns[-1].raw_query)

        if self_described_from_query and self_described_from_query != behavior_level:
            # 不一致！自我描述 vs 行为
            notes.append(
                f"不一致: 自称 {self_described_from_query} vs 行为 {behavior_level} "
                f"(行为占比 {behavior_ratio:.0%})"
            )
            # 采信行为（更可靠），但保留自我描述信息
            if behavior_ratio >= 0.6:
                return ConsistencyScore(
                    tech_level=behavior_level,
                    tech_confidence=0.7,
                    is_consistent=False,
                    notes=notes,
                )
            else:
                # 行为不够集中，降低置信度，取折中
                return ConsistencyScore(
                    tech_level=behavior_level,
                    tech_confidence=0.5,
                    is_consistent=False,
                    notes=notes + ["行为分散，置信度降低"],
                )

        # 一致
        return ConsistencyScore(
            tech_level=self_described,
            tech_confidence=0.9,
            is_consistent=True,
            notes=notes + [f"一致: {self_described}"],
        )

    def _check_patience_consistency(self, single_features: Dict[str, Any], turns: List[Turn]) -> ConsistencyScore:
        """检查耐心级别的一致性。"""
        notes = []

        self_described = single_features.get("patience_level", "neutral")
        impatient_count = 0

        for turn in turns:
            for keyword in self.PATIENCE_KEYWORDS["impatient"]:
                if keyword in turn.raw_query:
                    impatient_count += 1
                    break

        impatient_ratio = impatient_count / len(turns) if turns else 0

        if impatient_ratio >= 0.4 and self_described != "impatient":
            notes.append(f"不耐烦行为占比 {impatient_ratio:.0%}，覆盖自我描述")
            return ConsistencyScore(
                patience_level="impatient",
                patience_confidence=0.7,
                is_consistent=False,
                notes=notes,
            )

        return ConsistencyScore(
            patience_level=self_described,
            patience_confidence=0.7,
            is_consistent=True,
            notes=notes,
        )

    def _check_style_consistency(self, single_features: Dict[str, Any], turns: List[Turn]) -> ConsistencyScore:
        """检查风格的一致性。"""
        style = single_features.get("style", "unknown")
        return ConsistencyScore(
            style=style,
            style_confidence=0.6,
            is_consistent=True,
        )

    # ── 辅助方法 ─────────────────────────────────────────────────

    def _extract_self_described_level(self, query: str) -> Optional[str]:
        """从查询中提取用户自称的技术水平。"""
        query_lower = query.lower()
        for level, keywords in self.SELF_DESCRIBED_LEVEL.items():
            for kw in keywords:
                if kw in query_lower:
                    return level
        return None

    def _complexity_to_level(self, complexity: int) -> str:
        return self.COMPLEXITY_TO_LEVEL.get(complexity, "unknown")
