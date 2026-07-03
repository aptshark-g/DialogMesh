# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus

logger = logging.getLogger(__name__)


class FactualChecker:
    """事实性校验器 -- 检查节点内容的事实性。"""

    def check(self, node: CognitiveTreeNode, context=None) -> Tuple[float, List[str]]:
        issues = []
        content = node.content.lower() if node.content else ""
        conf = node.confidence
        if conf > 0.9 and len(content) < 50:
            issues.append("高置信度但内容过短，可能缺乏支撑")
        absolutes = ["always", "never", "everyone", "nobody"]
        hits = sum(1 for a in absolutes if a in content)
        if hits > 0:
            issues.append("包含 " + str(hits) + " 个绝对化表述")
        score = max(0.0, 1.0 - len(issues) * 0.3)
        return (round(score, 3), issues)


class ConsistencyChecker:
    """一致性校验器 -- 检查节点与历史节点的一致性。"""

    def check(self, node: CognitiveTreeNode, history_nodes: List[CognitiveTreeNode]) -> Tuple[float, List[str]]:
        if not history_nodes:
            return (1.0, [])
        inconsistencies = []
        same_llm = [n for n in history_nodes if n.source_llm == node.source_llm]
        if same_llm:
            avg_conf = sum(n.confidence for n in same_llm) / len(same_llm)
            if abs(node.confidence - avg_conf) > 0.4:
                inconsistencies.append("置信度突变: " + str(round(avg_conf,2)) + " -> " + str(round(node.confidence,2)))
        score = max(0.0, 1.0 - len(inconsistencies) * 0.4)
        return (round(score, 3), inconsistencies)


class ReasonablenessChecker:
    """合理性校验器 -- 检查推理链的合理性与证据支撑。"""

    def check(self, node: CognitiveTreeNode, evidence_nodes: List[CognitiveTreeNode]) -> Tuple[float, List[str]]:
        concerns = []
        if not evidence_nodes:
            concerns.append("没有引用的证据节点")
        score = max(0.0, 1.0 - len(concerns) * 0.3)
        return (round(score, 3), concerns)


class HallucinationDetector:
    """幻觉风险检测器。"""

    def detect(self, factual_score: float, consistency_score: float,
              reasonableness_score: float, node: CognitiveTreeNode) -> Tuple[float, str]:
        avg_score = (factual_score + consistency_score + reasonableness_score) / 3
        risk = round(1.0 - avg_score, 3)
        if risk > 0.6:
            return (risk, "invalid")
        elif risk > 0.3:
            return (risk, "needs_revision")
        return (risk, "valid")


class MetaCognitiveValidator:
    """
    MetaCognitiveValidator -- 元认知三层验证器。
    整合 FactualChecker + ConsistencyChecker + ReasonablenessChecker + HallucinationDetector。
    """

    def __init__(self):
        self.factual = FactualChecker()
        self.consistency = ConsistencyChecker()
        self.reasonableness = ReasonablenessChecker()
        self.hallucination = HallucinationDetector()

    def validate(self, node: CognitiveTreeNode, history_nodes: List[CognitiveTreeNode],
                 evidence_nodes: List[CognitiveTreeNode], context=None) -> Dict[str, Any]:
        factual_score, factual_issues = self.factual.check(node, context)
        cons_score, inconsistencies = self.consistency.check(node, history_nodes)
        reason_score, concerns = self.reasonableness.check(node, evidence_nodes)
        risk, recommendation = self.hallucination.detect(factual_score, cons_score, reason_score, node)
        return {
            "factual_check": {"score": factual_score, "issues": factual_issues},
            "consistency_check": {"score": cons_score, "inconsistencies": inconsistencies},
            "reasonableness_check": {"score": reason_score, "concerns": concerns},
            "hallucination_risk": risk,
            "overall_validation": recommendation,
            "confidence": round((factual_score + cons_score + reason_score) / 3, 3),
        }


__all__ = ["MetaCognitiveValidator", "FactualChecker", "ConsistencyChecker", "ReasonablenessChecker", "HallucinationDetector"]
