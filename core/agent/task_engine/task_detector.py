# core/agent/task_engine/task_detector.py
"""任务检测器 —— 从对话中识别任务类型和状态。

检测方式：
1. 规则检测（零成本）：关键词匹配、意图标签映射
2. 小模型检测（低成本）：本地小模型推理，~20ms

输出：
- task_type: 任务类型
- status: started/continued/switched/completed/paused
- confidence: 置信度

使用方式：
    detector = TaskDetector()
    result = detector.detect("帮我写一个快速排序")
    # → ("code", "started", 0.95)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

try:
    from core.agent.coordinator.small_model_client import SmallModelClient, get_small_model_client
    from core.agent.prompts.task_detector import task_detect_prompt, parse_task_result
except ImportError:
    SmallModelClient = None  # type: ignore
    get_small_model_client = None  # type: ignore
    task_detect_prompt = None  # type: ignore
    parse_task_result = None  # type: ignore

logger = logging.getLogger(__name__)


class TaskDetector:
    """任务检测器。"""

    # 任务类型关键词映射
    TASK_TYPE_KEYWORDS = {
        "code": {"写代码", "写一个", "帮我写", "实现", "代码", "函数", "类", "program", "code", "implement", "write a function"},
        "debug": {"bug", "报错", "错误", "排查", "修复", "debug", "fix", "error", "exception", "traceback"},
        "analyze": {"分析", "为什么", "怎么回事", "原理", "机制", "analyze", "why", "how does", "principle"},
        "compare": {"对比", "比较", "区别", "vs", "versus", "compare", "difference", "versus"},
        "search": {"查找", "搜索", "找一下", "在哪里", "search", "find", "look up", "locate"},
        "learn": {"学习", "教程", "怎么学", "入门", "learn", "tutorial", "guide", "how to learn"},
        "plan": {"计划", "规划", "方案", "设计", "plan", "design", "schedule", "roadmap"},
        "review": {"审查", "评估", "review", "audit", "evaluate", "assess"},
        "discuss": {"讨论", "聊聊", "你怎么看", "discuss", "talk about", "what do you think"},
    }

    # 状态信号词
    STATUS_MARKERS = {
        "started": {"开始", "新", "首先", "第一步", "start", "begin", "first"},
        "switched": {"换个", "转而", "改为", "回到", "switch", "change to", "back to", "instead"},
        "completed": {"完成", "结束", "好了", "搞定", "done", "finished", "complete", "that's it"},
        "paused": {"暂停", "先放", "稍后", "待会", "pause", "later", "hold on", "put aside"},
    }

    def __init__(self, small_model_client: Optional[Any] = None):
        self._sm_client = small_model_client

    def detect(self, query: str, intent_label: Optional[str] = None) -> Tuple[str, str, float]:
        """检测任务类型和状态。

        Returns:
            (task_type, status, confidence)
        """
        # 1. 规则检测
        rule_result = self._detect_rules(query, intent_label)

        # 2. 小模型检测
        sm_result = self._detect_with_small_model(query)

        # 3. 融合
        return self._merge_results(rule_result, sm_result)

    def _detect_rules(self, query: str, intent_label: Optional[str] = None) -> Tuple[str, str, float]:
        """规则检测。"""
        query_lower = query.lower()

        # 检测任务类型
        task_type = "none"
        max_score = 0
        for t_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > max_score:
                max_score = score
                task_type = t_type

        # 意图标签映射
        if intent_label:
            intent_map = {
                "code": "code", "debug": "debug", "analyze": "analyze",
                "compare": "compare", "search": "search", "learn": "learn",
                "plan": "plan", "recommend": "discuss", "summarize": "analyze",
                "question": "analyze", "statement": "discuss",
            }
            mapped = intent_map.get(intent_label.lower())
            if mapped and task_type == "none":
                task_type = mapped

        # 检测状态
        status = "continued"
        for st, markers in self.STATUS_MARKERS.items():
            if any(m in query_lower for m in markers):
                status = st
                break

        # 默认：如果检测到明确任务类型，标记为 started
        if status == "continued" and task_type != "none":
            status = "started"

        confidence = 0.5 + (0.1 * max_score) if max_score > 0 else 0.4
        confidence = min(0.9, confidence)

        return task_type, status, confidence

    def _detect_with_small_model(self, query: str) -> Optional[Tuple[str, str, float]]:
        """小模型检测。"""
        if self._sm_client is None:
            if get_small_model_client is not None:
                self._sm_client = get_small_model_client()
            else:
                return None

        if not self._sm_client.is_available:
            return None

        try:
            if task_detect_prompt is None or parse_task_result is None:
                return None
            prompt = task_detect_prompt(query)
            result = self._sm_client.invoke(prompt, max_tokens=100, temperature=0.1)
            if result is None:
                return None
            parsed = parse_task_result(result)
            if parsed is None:
                return None
            return parsed
        except Exception as e:
            logger.warning(f"Small model task detection failed: {e}")
            return None

    def _merge_results(
        self,
        rule: Tuple[str, str, float],
        sm: Optional[Tuple[str, str, float]],
    ) -> Tuple[str, str, float]:
        """融合规则和小模型结果。"""
        if sm is None:
            return rule

        # 小模型优先级更高
        task_type = sm[0] if sm[0] != "none" else rule[0]
        status = sm[1] if sm[1] != "continued" or rule[1] == "continued" else rule[1]
        confidence = max(rule[2], sm[2])
        return task_type, status, confidence
