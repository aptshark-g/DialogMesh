# core/agent/coordinator/complexity_evaluator.py
"""复杂度评估器 —— 判断输入应该走规则、小模型还是大模型。

评估维度：
1. 输入长度（>50字=+2分，>100字=+3分）
2. 实体密度（>3个实体=+2分）
3. 意图复杂度（analyze/compare/contrast=+2分，简单statement=0分）
4. 历史深度（>5轮=+2分，>10轮=+3分）
5. 粘合度灰色区域（0.45-0.65=+2分）
6. 歧义信号（多主语、嵌套从句、转折词=+1-2分）
7. 任务切换（"换个话题"、"顺便问"=+2分）

总分：0-10
- 0-3：规则（rule）
- 4-7：本地小模型（small_model）
- 8-10：远程大模型（remote_llm）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    jieba = None  # type: ignore
    JIEBA_AVAILABLE = False

    # 从自适应阈值模块导入（可选）
    try:
        from core.agent.coordinator.adaptive_threshold import ThresholdProfile
    except ImportError:
        ThresholdProfile = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class ComplexityScore:
    """复杂度评分结果。"""
    total: int              # 总分 0-10（应用权重后）
    raw_total: int          # 原始总分（未应用权重）
    length_score: int       # 长度维度
    entity_score: int       # 实体密度
    intent_score: int       # 意图复杂度
    history_score: int      # 历史深度
    cohesion_score: int     # 粘合度灰色区域
    ambiguity_score: int    # 歧义信号
    task_switch_score: int  # 任务切换
    multi_intent_score: int  # 多意图信号（新增）
    applied_weights: bool = False  # 是否应用了自适应权重

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "raw_total": self.raw_total,
            "length": self.length_score,
            "entity": self.entity_score,
            "intent": self.intent_score,
            "history": self.history_score,
            "cohesion": self.cohesion_score,
            "ambiguity": self.ambiguity_score,
            "task_switch": self.task_switch_score,
            "multi_intent": self.multi_intent_score,
            "applied_weights": self.applied_weights,
        }


class ComplexityEvaluator:
    """输入复杂度评估器。"""

    # 意图复杂度映射
    INTENT_COMPLEXITY = {
        "statement": 0,
        "chat": 0,
        "greeting": 0,
        "question": 1,
        "analyze": 2,
        "compare": 2,
        "contrast": 2,
        "evaluate": 2,
        "recommend": 2,
        "plan": 2,
        "explain": 1,
        "summarize": 1,
        "debug": 2,
        "refactor": 2,
        "design": 2,
    }

    # 歧义信号词
    AMBIGUITY_MARKERS = {
        "和", "与", "或", "但", "如果", "虽然", "因为", "但是", "不过", "然而",
        "and", "or", "but", "if", "although", "because", "however", "though",
        "而且", "并且", "另外", "同时", "另一方面",
        "不仅", "不但", "即使", "尽管", "除非",
    }

    # 多意图信号词（检测到多意图时提升复杂度，触发 remote_llm）
    MULTI_INTENT_MARKERS = {
        "然后", "顺便", "另外", "还有", "以及", "同时", "另外", "再",
        "and then", "also", "additionally", "furthermore", "moreover",
        "另外问", "再问一下", "顺便问", "再帮我", "然后帮我",
    }

    # 任务切换信号词
    TASK_SWITCH_MARKERS = {
        "换个话题", "顺便", "另外问", "再问一下", "回到",
        "先不管", "先放下", "先不说", "另外说",
        "by the way", "switching to", "moving on", "back to",
    }

    def evaluate(
        self,
        query: str,
        intent_label: Optional[str] = None,
        history_length: int = 0,
        cohesion_score: Optional[float] = None,
        entity_count: Optional[int] = None,
        threshold_profile: Optional[Any] = None,
    ) -> ComplexityScore:
        """评估输入复杂度。

        Args:
            query: 用户输入文本
            intent_label: 意图标签（如 "analyze"）
            history_length: 历史轮次数量
            cohesion_score: 粘合度分数（0-1），None 表示无粘合度信息
            entity_count: 实体数量，None 表示自动计算
            threshold_profile: 自适应阈值画像（可选），用于动态调整评分

        Returns:
            ComplexityScore（包含原始分数和加权分数）
        """
        # 1. 长度评分
        length_score = self._score_length(query)

        # 2. 实体密度
        if entity_count is None:
            entity_count = self._count_entities(query)
        entity_score = 2 if entity_count >= 3 else (1 if entity_count >= 2 else 0)

        # 3. 意图复杂度
        intent_score = self._score_intent(intent_label)

        # 4. 历史深度
        history_score = 0
        if history_length > 10:
            history_score = 3
        elif history_length > 5:
            history_score = 2
        elif history_length > 2:
            history_score = 1

        # 5. 粘合度灰色区域
        cohesion_score_val = 0
        if cohesion_score is not None:
            if 0.45 <= cohesion_score <= 0.65:
                cohesion_score_val = 2
            elif 0.35 <= cohesion_score < 0.45 or 0.65 < cohesion_score <= 0.75:
                cohesion_score_val = 1

        # 6. 歧义信号
        ambiguity_score = self._score_ambiguity(query)

        # 7. 任务切换
        task_switch_score = self._score_task_switch(query)

        # 8. 多意图检测（新增：多意图直接提升复杂度到 remote_llm 级别）
        multi_intent_score = self._score_multi_intent(query)

        # 计算原始总分（未加权）
        raw_total = sum([
            length_score, entity_score, intent_score, history_score,
            cohesion_score_val, ambiguity_score, task_switch_score,
            multi_intent_score,
        ])
        raw_total = min(raw_total, 10)  # 封顶 10

        # 应用自适应阈值权重（如果提供）
        applied_weights = False
        total = raw_total
        if threshold_profile is not None and hasattr(threshold_profile, 'apply_weights'):
            raw_scores = {
                "length": length_score,
                "entity": entity_score,
                "intent": intent_score,
                "history": history_score,
                "cohesion": cohesion_score_val,
                "ambiguity": ambiguity_score,
                "task_switch": task_switch_score,
                "multi_intent": multi_intent_score,
            }
            total = threshold_profile.apply_weights(raw_scores)
            applied_weights = True
            logger.debug(
                f"Adaptive weights applied: raw={raw_total} → weighted={total}, "
                f"base_offset={threshold_profile.base_offset}"
            )

        return ComplexityScore(
            total=total,
            raw_total=raw_total,
            length_score=length_score,
            entity_score=entity_score,
            intent_score=intent_score,
            history_score=history_score,
            cohesion_score=cohesion_score_val,
            ambiguity_score=ambiguity_score,
            task_switch_score=task_switch_score,
            multi_intent_score=multi_intent_score,
            applied_weights=applied_weights,
        )

    def _score_length(self, query: str) -> int:
        """根据输入长度评分。"""
        char_count = len(query.strip())
        if char_count > 100:
            return 3
        elif char_count > 50:
            return 2
        elif char_count > 20:
            return 1
        return 0

    def _count_entities(self, query: str) -> int:
        """统计实体数量（使用 jieba 词性标注）。"""
        if not JIEBA_AVAILABLE:
            return 0
        try:
            words = jieba.lcut(query)
            # 简单统计：长度 >= 2 的词视为潜在实体
            entities = [w for w in words if len(w) >= 2 and not w.isdigit()]
            return len(entities)
        except Exception:
            return 0

    def _score_intent(self, intent_label: Optional[str]) -> int:
        """根据意图标签评分。"""
        if intent_label is None:
            return 1  # 未知意图 = 中等复杂度
        return self.INTENT_COMPLEXITY.get(intent_label.lower(), 1)

    def _score_ambiguity(self, query: str) -> int:
        """根据歧义信号词评分。"""
        query_lower = query.lower()
        count = sum(1 for marker in self.AMBIGUITY_MARKERS if marker in query_lower)
        if count >= 3:
            return 2
        elif count >= 1:
            return 1
        return 0

    def _score_multi_intent(self, query: str) -> int:
        """根据多意图信号词评分。
        
        多意图是小模型（4B）的明确弱点：只能捕捉第一个意图，忽略后续意图。
        因此多意图信号直接给高分，确保触发 remote_llm 或由大模型拆分处理。
        """
        query_lower = query.lower()
        count = sum(1 for marker in self.MULTI_INTENT_MARKERS if marker in query_lower)
        if count >= 2:
            return 4  # 明确多意图，直接触发 remote_llm（配合其他维度轻易封顶10）
        elif count >= 1:
            return 3  # 可能多意图，显著提升
        return 0

    def _score_task_switch(self, query: str) -> int:
        """根据任务切换信号评分。"""
        query_lower = query.lower()
        for marker in self.TASK_SWITCH_MARKERS:
            if marker in query_lower:
                return 2
        return 0
