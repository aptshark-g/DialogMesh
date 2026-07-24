"""Behavior Chain — LLM Collaborative Analysis.

LLM解释行为变化、发现异常模式、建议阈值调整。
Input: BehaviorEdge statistics → LLM reasons → feedback → adjust.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class BehaviorLLMCollaborator:
    """LLM协同行为分析: 解释变化 + 发现模式 + 调参建议。

    Usage:
        collab = BehaviorLLMCollaborator(llm=deepseek)
        explain = collab.explain_drift(edge)
        patterns = collab.discover_patterns(graph)
        new_thresholds = collab.suggest_thresholds(statistics)
    """

    def __init__(self, llm=None):
        self.llm = llm

    def explain_drift(self, edge, llm=None) -> dict:
        """LLM解释为什么某个行为边的成功率/稳定性发生了变化。

        edge: BehaviorEdge with success_rate, correction_count, is_stable
        Returns: {explanation, severity, suggestion}
        """
        llm = llm or self.llm
        if not llm:
            return {"explanation": "no LLM", "severity": 0.0, "suggestion": ""}

        import json
        ctx = {
            "behavior": f"{getattr(edge, 'from_step_id', '')} → {getattr(edge, 'to_step_id', '')}",
            "success_rate": round(getattr(edge, 'success_rate', 0.5), 2),
            "correction_count": getattr(edge, 'correction_count', 0),
            "sample_count": getattr(edge, 'sample_count', 0),
            "is_stable": getattr(edge, 'is_stable', True),
            "activation_count": getattr(edge, 'activation_count', 0),
        }

        prompt = f"""A user behavior pattern has changed. Explain why.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Analyze: why is this behavior {('stable' if ctx['is_stable'] else 'UNSTABLE')}? What caused the change?
Output JSON: {{"explanation": "brief cause", "severity": 0.0-1.0, "suggestion": "what to do"}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=150, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else {}
        except Exception as e:
            logger.debug("Drift explain failed: %s", e)
            return {"explanation": str(e), "severity": 0.0, "suggestion": ""}

    def discover_patterns(self, graph_data: dict, llm=None) -> List[dict]:
        """LLM从行为图中发现异常或新的行为模式。

        graph_data: {"unstable_edges": [...], "correction_chains": [...], "top_edges": [...]}
        Returns: [{"pattern": "...", "confidence": 0.8, "action": "..."}, ...]
        """
        llm = llm or self.llm
        if not llm or not graph_data:
            return []

        import json
        prompt = f"""Analyze this user behavior graph and discover patterns.

GRAPH: {json.dumps(graph_data, ensure_ascii=False)[:1500]}

What patterns do you see? Discover:
1. Unstable edges: behaviors with low success rates
2. Correction chains: sequences where user corrects repeatedly
3. New patterns: behaviors that were rare but increasing

Output JSON array: [{{"pattern": "description", "confidence": 0.0-1.0, "action": "pillar/delete/observe"}}, ...]"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=300, temperature=0.2)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('['); e = cleaned.rfind(']')
            if s >= 0 and e > s:
                return json.loads(cleaned[s:e+1])
        except Exception as e:
            logger.debug("Pattern discovery failed: %s", e)
        return []

    def suggest_thresholds(self, statistics: dict, llm=None) -> dict:
        """LLM suggests threshold adjustments based on error rates."""
        llm = llm or self.llm
        if not llm:
            return statistics

        import json
        prompt = f"""Behavior prediction thresholds need tuning.

STATS: {json.dumps(statistics, ensure_ascii=False)}
More FP → lower success threshold. More FN → raise it.
Output JSON: {{"success_threshold": 0.0-1.0, "instability_threshold": 0.0-1.0, "reason": "brief"}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=100, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else statistics
        except Exception:
            return statistics

    def suggest_and_apply(self, edge, llm=None) -> dict:
        """LLM suggests thresholds → applied to edge → edge learns.

        Full feedback loop: statistics → LLM → suggestions → edge parameters.
        """
        stats = {
            "false_positives": getattr(edge, 'failure_count', 0),
            "false_negatives": getattr(edge, 'correction_count', 0),
            "current_success_threshold": getattr(edge, 'success_threshold', 0.7),
            "current_instability_threshold": getattr(edge, 'instability_threshold', 0.3),
            "sample_count": getattr(edge, 'sample_count', 0),
        }
        
        suggestion = self.suggest_thresholds(stats, llm)
        
        # Apply LLM feedback to edge (70% statistical + 30% LLM)
        if hasattr(edge, 'apply_llm_feedback') and suggestion:
            edge.apply_llm_feedback(suggestion)
            logger.debug("LLM feedback applied to edge %s: thresholds %.2f/%.2f",
                        getattr(edge, 'edge_key', '?'),
                        getattr(edge, 'success_threshold', 0.7),
                        getattr(edge, 'instability_threshold', 0.3))
        
        return suggestion
        """LLM建议调整行为判定阈值。

        statistics: {"false_positives": N, "false_negatives": N, 
                     "current_success_threshold": 0.7, "current_instability_threshold": 0.3}
        Returns: {"success_threshold": 0.65, "instability_threshold": 0.25, "reason": "..."}
        """
        llm = llm or self.llm
        if not llm:
            return statistics

        import json
        prompt = f"""Behavior prediction thresholds need tuning based on observed errors.

STATS: {json.dumps(statistics, ensure_ascii=False)}

Should we adjust thresholds? More FP → lower success threshold. More FN → raise it.
Output JSON: {{"success_threshold": 0.0-1.0, "instability_threshold": 0.0-1.0, "reason": "brief"}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=100, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else statistics
        except Exception:
            return statistics

    def analyze_correction_chain(self, corrections: List[dict], llm=None) -> dict:
        """LLM分析连续修正序列, 发现根因。

        corrections: [{"from": "诊断", "to": "修复", "corrected_to": "探索", "turn": 5}, ...]
        Returns: {"root_cause": "...", "suggested_fix": "...", "confidence": 0.8}
        """
        llm = llm or self.llm
        if not llm or len(corrections) < 2:
            return {"root_cause": "insufficient data", "suggested_fix": "", "confidence": 0.0}

        import json
        prompt = f"""User corrected predicted behavior multiple times. Find root cause.

CORRECTIONS: {json.dumps(corrections, ensure_ascii=False)}

Why is the agent predicting wrong? Is there a systematic issue?
Output JSON: {{"root_cause": "explanation", "suggested_fix": "what to change", "confidence": 0.0-1.0}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=150, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else {}
        except Exception:
            return {"root_cause": "LLM unavailable", "suggested_fix": "", "confidence": 0.0}
