# -*- coding: utf-8 -*-

import logging
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus

logger = logging.getLogger(__name__)


class HallucinationDetector:
    """
    HallucinationDetector v3.0 -- 跨轮幻觉检测器（幻觉防御 Layer 2）。

    职责：
      - 分析历史节点的置信度变化模式
      - 检测置信度异常尖峰（可能标志幻觉）
      - 检测高置信度 + 快速被无效化的模式（过度自信幻觉）
    """

    def __init__(self, window_size: int = 10):
        self._window_size = window_size
        self._history: Dict[str, deque] = {}

    def analyze(self, node: CognitiveTreeNode,
                history_nodes: List[CognitiveTreeNode]) -> Tuple[float, List[str]]:
        """
        分析指定节点是否存在幻觉风险。
        Returns (risk_score 0-1, indicators list)。
        """
        risk = 0.0
        indicators: List[str] = []

        if not history_nodes:
            return (0.0, [])

        # 1. 置信度尖峰检测
        same_llm = [n for n in history_nodes if n.source_llm == node.source_llm]
        if same_llm:
            avg_conf = sum(n.confidence for n in same_llm) / len(same_llm)
            if node.confidence > avg_conf + 0.35 and node.confidence > 0.8:
                risk += 0.3
                indicators.append("置信度尖峰: " + str(round(node.confidence, 2)) + " vs 平均 " + str(round(avg_conf, 2)))

        # 2. 高置信度快速失效模式
        recent_invalidated = [
            n for n in history_nodes
            if n.status == CogNodeStatus.INVALIDATED and n.confidence > 0.8
        ]
        if len(recent_invalidated) >= 3:
            risk += 0.3
            indicators.append("最近 " + str(len(recent_invalidated)) + " 个高置信节点被无效化")

        # 3. 连续低质量输出
        recent_nodes = history_nodes[-min(5, len(history_nodes)):]
        failed_ratio = sum(1 for n in recent_nodes if n.status == CogNodeStatus.INVALIDATED) / len(recent_nodes)
        if failed_ratio > 0.6:
            risk += 0.4
            indicators.append("最近输出中 " + str(round(failed_ratio * 100)) + "% 被无效化")

        risk = min(1.0, risk)
        return (round(risk, 3), indicators)

    def get_session_risk(self, session_id: str) -> float:
        """获取指定会话的累积幻觉风险。"""
        hist = self._history.get(session_id)
        if not hist or len(hist) == 0:
            return 0.0
        return round(sum(hist) / len(hist), 3)


__all__ = ["HallucinationDetector"]
