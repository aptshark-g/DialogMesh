"""L4 Temporal + LLM Collaboration — dual-track feedback loop.

Algorithm computes → structured context → LLM reasons → corrections → update algorithm.
"""

from __future__ import annotations
from core.agent.llm_config import DEFAULT as _LLM_CFG
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Re-export from l4_temporal
from .l4_temporal import L4TemporalEngine, DriftEvent, IntentTransition


class L4CollaborativeEngine(L4TemporalEngine):
    """L4 with feedback-loop LLM collaboration.

    Algorithm → structured signals → LLM reasons → corrections → algorithm adapts.
    NOT: algorithm → text → LLM → text → discard.
    """

    def __init__(self, window_size: int = 10, llm=None):
        super().__init__(window_size)
        self.llm = llm
        self._drift_threshold = 0.3  # adaptive, LLM can adjust
        self._anomaly_threshold = 0.5

    def collaborative_drift_check(self, intent_dist: Dict[str, float]) -> Optional[DriftEvent]:
        """Algorithm detects drift → LLM confirms/rejects → if confirmed, adjust threshold."""
        drift = self.check_drift(intent_dist)
        if not drift or not self.llm:
            return drift

        # Structured context for LLM — not flat text
        import json
        ctx = {
            "historical_distribution": dict(sorted(self._intent_distribution.items(), 
                                                   key=lambda x: -x[1])[:5]),
            "current_distribution": dict(sorted(intent_dist.items(), key=lambda x: -x[1])),
            "drift_magnitude_jsd": round(drift.magnitude, 3),
            "recent_transitions": [
                {"from": t.from_intent, "to": t.to_intent, "turn": t.turn}
                for t in self._transitions[-5:]
            ],
            "current_threshold": self._drift_threshold,
        }

        prompt = f"""Algorithm detected intent drift (JSD={drift.magnitude:.2f}). Verify.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Should we confirm this drift? Adjust the detection threshold?
Output JSON: {{"confirm": true/false, "new_threshold": 0.0-1.0, "reason": "brief"}}"""

        try:
            import re
            resp = self.llm.generate(prompt, max_tokens=_LLM_CFG.max_tokens, temperature=_LLM_CFG.temperature)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                data = json.loads(cleaned[s:e+1])
                if data.get("confirm"):
                    # LLM feedback → adjust algorithm threshold
                    new_th = data.get("new_threshold", self._drift_threshold)
                    if abs(new_th - self._drift_threshold) > 0.05:
                        logger.info("LLM adjusted drift threshold: %.2f→%.2f",
                                   self._drift_threshold, new_th)
                        self._drift_threshold = new_th
                    drift.likely_cause = data.get("reason", "")
                else:
                    return None  # LLM rejected drift
        except Exception as e:
            logger.debug("LLM drift verify failed: %s", e)

        return drift

    def collaborative_predict(self, current_intent: str, llm=None,
                              top_k: int = 3) -> List[Tuple[str, float, bool]]:
        """T-BN predicts → LLM scores → re-rank by combined score.

        Returns [(intent, probability, llm_approved), ...]
        """
        llm = llm or self.llm
        preds = self.predict_next(current_intent, top_k)
        if not preds or not llm:
            return [(p[0], p[1], False) for p in preds]

        import json
        # Structured context
        matrix_slice = {}
        for from_intent, to_counts in list(self._transition_counts.items())[:3]:
            total = sum(to_counts.values())
            matrix_slice[from_intent] = {k: round(v/total, 2) 
                                        for k, v in sorted(to_counts.items(), 
                                                          key=lambda x: -x[1])[:3]}

        candidates = [{"intent": p[0], "probability": round(p[1], 2)} for p in preds]
        ctx = {
            "current_intent": current_intent,
            "candidates": candidates,
            "transition_subset": matrix_slice,
            "total_transitions": len(self._transitions),
        }

        prompt = f"""Score these intent transition candidates for plausibility.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

For each candidate, output: accepted=true/false, adjusted_probability=0.0-1.0.
Output JSON: [{{"intent": ..., "accepted": ..., "adj_prob": ...}}, ...]"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=_LLM_CFG.max_tokens, temperature=_LLM_CFG.temperature)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('['); e = cleaned.rfind(']')
            if s >= 0 and e > s:
                scores = json.loads(cleaned[s:e+1])
                result = []
                for pred in preds:
                    intent, prob = pred
                    score = next((s for s in scores if s.get("intent") == intent), {})
                    adj = score.get("adj_prob", prob)
                    result.append((intent, adj, score.get("accepted", True)))
                # Re-rank by LLM-adjusted probability
                result.sort(key=lambda x: -x[1])
                return result
        except Exception as e:
            logger.debug("LLM score failed: %s", e)

        return [(p[0], p[1], False) for p in preds]

    def collaborative_anomaly_check(self, recent: List[str], llm=None) -> dict:
        """Algorithm detects anomaly → LLM explains with structured context."""
        llm = llm or self.llm
        anomaly = self.detect_sequence_anomaly(recent)
        
        if anomaly < self._anomaly_threshold or not llm:
            return {"anomaly": anomaly, "explanation": "normal", "suggestion": ""}

        import json
        ctx = {
            "recent_sequence": recent,
            "anomaly_score": round(anomaly, 3),
            "expected_transitions": [
                {"from": k, "to": max(v, key=v.get)}
                for k, v in list(self._transition_counts.items())[:3]
            ],
        }

        prompt = f"""Anomalous intent sequence detected. Explain and suggest.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Output JSON: {{"explanation": "why anomalous", "suggestion": "what to do", 
              "adjust_threshold": 0.0-1.0 or null}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=_LLM_CFG.max_tokens, temperature=_LLM_CFG.temperature)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                data = json.loads(cleaned[s:e+1])
                # LLM feedback → adjust anomaly threshold
                adj = data.get("adjust_threshold")
                if adj and abs(adj - self._anomaly_threshold) > 0.05:
                    self._anomaly_threshold = adj
                return {
                    "anomaly": anomaly,
                    "explanation": data.get("explanation", ""),
                    "suggestion": data.get("suggestion", ""),
                }
        except Exception:
            pass

        return {"anomaly": anomaly, "explanation": "", "suggestion": ""}
