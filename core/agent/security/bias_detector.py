# -*- coding: utf-8 -*-

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus

logger = logging.getLogger(__name__)


class BiasDetector:
    """
    BiasDetector v3.0 -- 系统性偏误检测器（幻觉防御 Layer 3）。

    职责：
      - 跨会话分析 LLM 的特定偏见模式
      - 检测特定类型的系统性输出失真
      - 生成偏见报告供 Reflective 层消费
    """

    def __init__(self):
        self._session_records: Dict[str, List[Dict[str, Any]]] = {}

    def analyze(self, nodes: List[CognitiveTreeNode], session_id: str) -> Dict[str, Any]:
        """
        分析一组节点中是否存在系统性偏见。
        """
        biases: List[Dict[str, Any]] = []
        if not nodes:
            return {"detected_biases": [], "severity": "low", "confidence": 0.5}

        # 1. 置信度膨胀检测
        high_conf_count = sum(1 for n in nodes if n.confidence > 0.9)
        high_conf_invalidated = sum(1 for n in nodes if n.confidence > 0.9 and n.status == CogNodeStatus.INVALIDATED)
        if high_conf_count > 3 and high_conf_invalidated > high_conf_count * 0.3:
            biases.append({"type": "confidence_inflation", "severity": "high",
                "description": "置信度膨胀: " + str(high_conf_invalidated) + "/" + str(high_conf_count) + " 高置信节点被无效化"})

        # 2. 特定 LLM 偏见检测
        by_llm = defaultdict(list)
        for n in nodes:
            by_llm[n.source_llm].append(n)
        for llm_name, llm_nodes in by_llm.items():
            inv = sum(1 for n in llm_nodes if n.status == CogNodeStatus.INVALIDATED)
            if len(llm_nodes) >= 3 and inv / len(llm_nodes) > 0.4:
                biases.append({"type": "llm_systematic_bias", "severity": "medium",
                    "llm": llm_name, "description": llm_name + " 失效比例 " + str(round(inv/len(llm_nodes)*100)) + "%"})

        # 3. 记录会话
        record = {"biases": len(biases), "severity": "high" if any(b["severity"] == "high" for b in biases) else "low"}
        if session_id not in self._session_records:
            self._session_records[session_id] = []
        self._session_records[session_id].append(record)

        severity = "low"
        if any(b["severity"] == "high" for b in biases):
            severity = "high"
        elif any(b["severity"] == "medium" for b in biases):
            severity = "medium"

        return {"detected_biases": biases, "severity": severity,
                "confidence": round(max(0.0, 1.0 - len(biases) * 0.2), 3)}


__all__ = ["BiasDetector"]
