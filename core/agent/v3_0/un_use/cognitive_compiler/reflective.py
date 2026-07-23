# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus
from core.agent.v3_0.cognitive_compiler.tree_health import TreeHealthAnalyzer

logger = logging.getLogger(__name__)


class BiasDetector:
    """系统偏见检测器。"""

    def detect(self, nodes: List[CognitiveTreeNode],
              health_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        biases = []
        if not nodes:
            return biases
        llm_inv = health_report.get("llm_invalidation_rates", {})
        for llm_name, rate in llm_inv.items():
            if rate > 0.3:
                biases.append({"type": "systematic_invalidation", "llm": llm_name,
                    "severity": "high" if rate > 0.5 else "medium",
                    "description": f"{llm_name} 输出被持续标记无效 ({rate:.1%})"})
        high_conf_low = sum(1 for n in nodes if n.confidence > 0.8 and n.status == CogNodeStatus.INVALIDATED)
        if high_conf_low > len(nodes) * 0.1:
            biases.append({"type": "confidence_overestimation", "severity": "medium",
                "description": f"{high_conf_low} 个高置信节点被无效化"})
        return biases


class LearningStrategyGenerator:
    """学习策略生成器。"""

    def generate(self, biases: List[Dict[str, Any]],
                 health_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        strategies = []
        for bias in biases:
            if bias["type"] == "systematic_invalidation":
                llm = bias["llm"]
                p = "P0" if bias["severity"] == "high" else "P1"
                strategies.append({"strategy": f"降低 {llm} 置信度门槛", "target_llm": llm, "priority": p})
            elif bias["type"] == "confidence_overestimation":
                strategies.append({"strategy": "全局降低置信度阈值", "target_llm": "all", "priority": "P1"})
        if health_report.get("invalidated_ratio", 0) > 0.3:
            strategies.append({"strategy": "系统失效比例过高，审查配置", "target_llm": "system", "priority": "P0"})
        return strategies


class ReflectiveAnalyzer:
    """跨会话复盘分析器。整合 TreeHealthAnalyzer + BiasDetector + LearningStrategyGenerator。"""

    def __init__(self):
        self.tree_health = TreeHealthAnalyzer()
        self.bias_detector = BiasDetector()
        self.strategy_gen = LearningStrategyGenerator()

    def analyze(self, nodes: List[CognitiveTreeNode]) -> Dict[str, Any]:
        health = self.tree_health.analyze(nodes)
        biases = self.bias_detector.detect(nodes, health)
        strategies = self.strategy_gen.generate(biases, health)
        severity_values = [b["severity"] for b in biases]
        top_severity = "low"
        if "high" in severity_values: top_severity = "high"
        elif "medium" in severity_values: top_severity = "medium"
        return {
            "tree_health": {"health_score": health.get("health_score", 0.5),
                "total_nodes": health.get("total_nodes", 0),
                "invalidated_ratio": health.get("invalidated_ratio", 0),
                "concerns": health.get("concerns", [])},
            "bias_analysis": {"detected_biases": biases, "severity": top_severity},
            "learning_strategies": strategies,
            "confidence": round(max(0.0, 1.0 - len(biases) * 0.2), 3),
        }


__all__ = ["ReflectiveAnalyzer", "BiasDetector", "LearningStrategyGenerator"]
