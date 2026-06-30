# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/scorer.py
────────────────────────────────────
Cohesion scorer: 4-dimension weighted scoring.

维度：
  1. causal 因果强度（动作→目标连续性）
  2. entity_overlap 实体重叠（共同实体数量）
  3. subject_continuity 主语连续性
  4. weak_link 弱关联（时间/位置接近性）
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional


class CohesionScorer:
    """
    粘合度评分器。
    基于 4 维度规则计算当前输入与历史的粘合度。
    """

    # 权重
    WEIGHTS = {
        "causal": 0.50,              # 因果强度是最重要的信号
        "entity_overlap": 0.25,
        "subject_continuity": 0.15,
        "weak_link": 0.10,
    }

    # 因果关键词（动作→目标连续性）
    CAUSAL_CONTINUATION = {
        "然后", "接着", "之后", "再", "并", "并且", "所以", "因此",
        "then", "and", "after", "so", "therefore", "thus", "also",
        "读取", "修改", "写入", "patch", "change", "update", "fix",
    }

    # 话题切换关键词（低粘合度信号）
    TOPIC_SWITCH = {
        "另外", "换个话题", "话说回来", "对了", "顺便",
        "by the way", "speaking of", "anyway", "however",
        "学习", "tutorial", "guide", "how to", "什么是",
    }

    def calculate(
        self,
        query: str,
        session_history: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """
        计算粘合度分数 (0-1)。
        """
        session_history = session_history or []
        if not session_history:
            return 0.0  # 无历史，无粘合度

        # 取最近 3 轮历史
        recent_history = session_history[-3:]
        recent_text = " ".join(
            h.get("content", "") for h in recent_history
        )

        scores = {
            "causal": self._score_causal(query, recent_text),
            "entity_overlap": self._score_entity_overlap(query, recent_text),
            "subject_continuity": self._score_subject_continuity(query, recent_text),
            "weak_link": self._score_weak_link(query, recent_history),
        }

        # 加权求和
        total = sum(
            scores[k] * self.WEIGHTS[k] for k in self.WEIGHTS
        )
        return round(min(1.0, max(0.0, total)), 3)

    # ── 维度评分 ───────────────────────────────────────────

    def _score_causal(self, query: str, recent_text: str) -> float:
        """因果强度评分。"""
        # 检查是否包含因果延续词
        for word in self.CAUSAL_CONTINUATION:
            if word in query.lower():
                return 1.0

        # 检查动作连续性（当前 query 是否延续上一动作的目标）
        # 简单策略：如果 query 包含上一轮的实体值，认为有因果关联
        return 0.5

    def _score_entity_overlap(self, query: str, recent_text: str) -> float:
        """实体重叠评分。"""
        # 提取 query 中的实体
        query_entities = self._extract_entities(query)
        history_entities = self._extract_entities(recent_text)

        if not query_entities or not history_entities:
            return 0.0

        overlap = len(query_entities & history_entities)
        total = len(query_entities | history_entities)
        return overlap / total if total > 0 else 0.0

    def _score_subject_continuity(self, query: str, recent_text: str) -> float:
        """主语连续性评分。"""
        # 简单策略：提取前几个词作为主语，检查是否匹配
        query_start = query.strip()[:10].lower()
        history_start = recent_text.strip()[:10].lower()

        # 如果 query 以代词开头（"这个", "那个", "it"），认为主语延续
        pronouns = {"这个", "那个", "它", "这", "那", "it", "this", "that", "the"}
        for pronoun in pronouns:
            if query.lower().startswith(pronoun):
                return 0.8

        # 如果开头词重叠，高连续性
        if query_start in history_start or history_start in query_start:
            return 0.7

        return 0.2

    def _score_weak_link(self, query: str, recent_history: List[Dict[str, Any]]) -> float:
        """弱关联评分（时间/位置接近性）。"""
        # 时间接近性：如果与上一轮间隔很短，高弱关联
        if len(recent_history) >= 1:
            last_time = recent_history[-1].get("timestamp", 0)
            if last_time > 0:
                time_gap = abs(time.time() - last_time)
                if time_gap < 60:  # 1 分钟内
                    return 0.9
                elif time_gap < 300:  # 5 分钟内
                    return 0.5
                else:
                    return 0.2
        return 0.5

    # ── 工具方法 ───────────────────────────────────────────

    def _extract_entities(self, text: str) -> set:
        """提取文本中的实体值（简单正则）。"""
        entities = set()
        # 内存地址
        for match in re.finditer(r'0x[0-9a-fA-F]+', text):
            entities.add(match.group())
        # 数值
        for match in re.finditer(r'\b\d+\b', text):
            entities.add(match.group())
        # 进程名
        for match in re.finditer(r'\b\w+\.exe\b', text, re.IGNORECASE):
            entities.add(match.group().lower())
        return entities
