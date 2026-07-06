# -*- coding: utf-8 -*-

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus, CogType

logger = logging.getLogger(__name__)


class TreeHealthAnalyzer:
    """
    TreeHealthAnalyzer v3.0 -- Cognitive Tree 健康度分析器。

    职责：
      - 节点失效比例追踪
      - 分支健康度评估
      - 跨会话偏误检测
    """

    def __init__(self):
        self._session_stats: Dict[str, Dict[str, Any]] = {}

    def analyze(self, nodes: List[CognitiveTreeNode]) -> Dict[str, Any]:
        """分析一组 Cognitive Tree 节点的健康度。"""
        if not nodes:
            return self._empty_report()

        total = len(nodes)
        by_status = Counter(n.status for n in nodes)
        by_type = Counter(n.cog_type for n in nodes)
        by_llm = Counter(n.source_llm for n in nodes)

        active_count = by_status.get(CogNodeStatus.ACTIVE, 0)
        invalidated_count = by_status.get(CogNodeStatus.INVALIDATED, 0)

        # 健康得分: 活跃占比 * 0.7 + 逆向失效占比 * 0.3
        active_ratio = active_count / max(1, total)
        invalidated_ratio = invalidated_count / max(1, total)
        health_score = active_ratio * 0.7 + (1 - invalidated_ratio) * 0.3

        # 每层 LLM 的失效比例
        llm_invalidation: Dict[str, float] = {}
        for llm_name in by_llm:
            llm_nodes = [n for n in nodes if n.source_llm == llm_name]
            inv = sum(1 for n in llm_nodes if n.status == CogNodeStatus.INVALIDATED)
            llm_invalidation[llm_name] = round(inv / max(1, len(llm_nodes)), 3)

        # 偏误检测: 某个 LLM 的失效比例显著高于平均水平
        concerns = []
        avg_inv = invalidated_ratio
        for llm_name, inv_ratio in llm_invalidation.items():
            if inv_ratio > avg_inv + 0.15 and inv_ratio > 0.2:
                concerns.append({
                    "type": "llm_bias",
                    "llm": llm_name,
                    "invalidation_rate": inv_ratio,
                    "message": f"{llm_name} 失效比例 {inv_ratio:.1%} 高于平均 {avg_inv:.1%}",
                })

        return {
            "health_score": round(health_score, 3),
            "total_nodes": total,
            "active_ratio": round(active_ratio, 3),
            "invalidated_ratio": round(invalidated_ratio, 3),
            "by_status": {str(k): v for k, v in by_status.items()},
            "by_type": {str(k): v for k, v in by_type.items()},
            "by_llm": dict(by_llm),
            "llm_invalidation_rates": llm_invalidation,
            "concerns": concerns,
        }

    def _empty_report(self) -> Dict[str, Any]:
        return {"health_score": 0.5, "total_nodes": 0, "active_ratio": 0, "invalidated_ratio": 0, "concerns": []}


__all__ = ["TreeHealthAnalyzer"]
