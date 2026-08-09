"""L4 Temporal Pattern — intent transition prediction + drift detection.

Design: docs/v5/DESIGN_ASSOCIATION_CHAIN_L1_L4.md §L4
Frontier: T-BN (时序贝叶斯), HyperHawkes (超图Hawkes), DZ-TDPO (时序对齐)

Core: P(intent_t+1 | intent_t, intent_t-1, ...) from conversation history.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import logging

logger = logging.getLogger(__name__)


@dataclass
class IntentTransition:
    """One observed intent transition."""
    from_intent: str
    to_intent: str
    turn: int
    confidence: float = 1.0


@dataclass
class DriftEvent:
    """Detected intent drift."""
    turn: int
    from_distribution: Dict[str, float]
    to_distribution: Dict[str, float]
    magnitude: float          # 0-1, how different
    likely_cause: str = ""


class L4TemporalEngine:
    """Temporal intent pattern detection and prediction.

    T-BN: temporal Bayesian network — learns P(next | current) from history.
    Drift: detects when intent distribution shifts significantly.

    Usage:
        l4 = L4TemporalEngine()
        l4.record_transition("诊断", "修复", turn=5)
        next_intent = l4.predict_next("诊断")  # → "修复" with P=0.72
        drift = l4.check_drift(current_distribution)  # → None or DriftEvent
    """

    def __init__(self, window_size: int = 10):
        self.window = window_size
        self._transitions: List[IntentTransition] = []
        self._intent_sequence: List[str] = []
        self._transition_counts: Dict[str, Dict[str, int]] = {}  # from→to→count
        self._intent_distribution: Dict[str, int] = {}           # intent→count
        self._drift_history: List[DriftEvent] = []
        self._total_turns: int = 0

    def record(self, intent: str, confidence: float = 1.0, turn: int = 0):
        """Record an intent observation for this turn."""
        self._total_turns = max(self._total_turns, turn)

        # Record sequence
        if self._intent_sequence:
            prev = self._intent_sequence[-1]
            if prev != intent:
                self._add_transition(prev, intent, turn, confidence)
        self._intent_sequence.append(intent)

        # Keep window
        if len(self._intent_sequence) > self.window * 3:
            self._intent_sequence = self._intent_sequence[-self.window * 2:]

        # Update distribution
        self._intent_distribution[intent] = self._intent_distribution.get(intent, 0) + 1

    def _add_transition(self, from_intent: str, to_intent: str, turn: int, confidence: float):
        """Record a transition with counting."""
        if from_intent not in self._transition_counts:
            self._transition_counts[from_intent] = {}
        self._transition_counts[from_intent][to_intent] = \
            self._transition_counts[from_intent].get(to_intent, 0) + 1
        self._transitions.append(IntentTransition(
            from_intent=from_intent, to_intent=to_intent, turn=turn, confidence=confidence
        ))

    def predict_next(self, current_intent: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """T-BN: predict most likely next intent given current.

        Returns [(intent, probability), ...] sorted by descending probability.
        """
        counts = self._transition_counts.get(current_intent, {})
        total = sum(counts.values())
        if total == 0:
            return []
        
        probs = [(to, cnt / total) for to, cnt in counts.items()]
        probs.sort(key=lambda x: -x[1])
        return probs[:top_k]

    def transition_matrix(self) -> Dict[str, Dict[str, float]]:
        """Full transition probability matrix P(next | current)."""
        matrix = {}
        for from_intent, to_counts in self._transition_counts.items():
            total = sum(to_counts.values())
            matrix[from_intent] = {to: cnt / total for to, cnt in to_counts.items()}
        return matrix

    def check_drift(self, current_distribution: Dict[str, float]) -> Optional[DriftEvent]:
        """Detect if current intent distribution has drifted from historical.

        Uses Jensen-Shannon divergence between current and historical distributions.
        """
        if not self._intent_distribution or not current_distribution:
            return None

        # Normalize historical distribution
        hist_total = sum(self._intent_distribution.values())
        hist_norm = {k: v / max(1, hist_total) for k, v in self._intent_distribution.items()}

        # JS divergence
        jsd = self._jensen_shannon(current_distribution, hist_norm)

        if jsd > 0.3:  # significant drift
            return DriftEvent(
                turn=self._total_turns,
                from_distribution=hist_norm,
                to_distribution=current_distribution,
                magnitude=jsd,
                likely_cause=f"Intent shift detected (JSD={jsd:.2f})"
            )
        return None

    def _jensen_shannon(self, p: Dict[str, float], q: Dict[str, float]) -> float:
        """Jensen-Shannon divergence between two distributions."""
        all_keys = set(p.keys()) | set(q.keys())
        
        def kl_div(a, b):
            return sum(a.get(k, 0.01) * math.log(a.get(k, 0.01) / max(0.001, b.get(k, 0.01)))
                      for k in all_keys)
        
        m = {k: (p.get(k, 0.01) + q.get(k, 0.01)) / 2 for k in all_keys}
        return math.sqrt((kl_div(p, m) + kl_div(q, m)) / 2)

    def detect_sequence_anomaly(self, recent_intents: List[str]) -> float:
        """Check if recent intent sequence is anomalous given history.
        
        Returns: anomaly score 0-1. Higher = more anomalous.
        """
        if len(recent_intents) < 2:
            return 0.0
        
        anomaly_scores = []
        for i in range(len(recent_intents) - 1):
            a, b = recent_intents[i], recent_intents[i + 1]
            preds = self.predict_next(a)
            pred_intents = [p[0] for p in preds] if preds else []
            
            if b in pred_intents:
                idx = pred_intents.index(b)
                anomaly_scores.append(idx / len(pred_intents))  # 0=expected, 1=surprising
            else:
                anomaly_scores.append(1.0)  # completely unexpected
        
        return sum(anomaly_scores) / len(anomaly_scores) if anomaly_scores else 0.0

    # ── LLM collaboration (dual-track) ──

    def explain_drift_with_llm(self, drift: DriftEvent, llm) -> str:
        """LLM explains why intent distribution drifted."""
        if not llm or not drift:
            return "No drift or LLM unavailable"
        
        prompt = f"""Intent distribution shift detected. Explain likely cause.

HISTORICAL: {drift.from_distribution}
CURRENT:    {drift.to_distribution}
MAGNITUDE:  {drift.magnitude:.2f} (Jensen-Shannon divergence)

What caused this shift? Output one sentence explanation."""
        
        try:
            import re
            resp = llm.generate(prompt, max_tokens=100, temperature=0.1)
            return str(resp)[:200]
        except Exception as e:
            return f"LLM unavailable: {e}"

    def verify_transition_with_llm(self, from_intent: str, to_intent: str, 
                                   probability: float, llm) -> dict:
        """LLM verifies if a predicted transition is semantically plausible."""
        if not llm:
            return {"plausible": True, "reason": "no LLM"}

        prompt = f"""Is this intent transition plausible?

FROM: {from_intent}
TO:   {to_intent}
PROB: {probability:.2f} (from historical data)

Output JSON: {{"plausible": true/false, "reason": "brief"}}"""
        
        try:
            import json, re
            resp = llm.generate(prompt, max_tokens=100, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                return json.loads(cleaned[s:e+1])
        except Exception:
            pass
        return {"plausible": True, "reason": "default"}

    def predict_with_llm_review(self, current_intent: str, llm,
                                top_k: int = 3) -> List[Tuple[str, float, str]]:
        """T-BN predicts → LLM reviews each candidate.

        Returns [(intent, probability, llm_verdict), ...]
        """
        preds = self.predict_next(current_intent, top_k)
        if not preds or not llm:
            return [(p[0], p[1], "no review") for p in preds]
        
        reviewed = []
        for intent, prob in preds:
            verdict = self.verify_transition_with_llm(current_intent, intent, prob, llm)
            reviewed.append((intent, prob, verdict.get("reason", "")))
        return reviewed

    def status(self) -> dict:
        """Engine status for monitoring."""
        return {
            "total_transitions": len(self._transitions),
            "unique_intents": len(self._intent_distribution),
            "intent_distribution": self._intent_distribution,
            "transition_matrix": self.transition_matrix(),
            "recent_drifts": len(self._drift_history),
            "window": self.window,
        }

    # ── D-16: L4 三方交汇（关联链 × 行为链 × 工程链）──

    def triparty_reconcile(
        self,
        behavior_sequences: List[tuple],
        engineering_constraints: Dict[str, Any] = None,
    ) -> dict:
        """Reconcile L4 temporal patterns with behavior chains and engineering
        constraints (BUSINESS_CHAIN_06 §2.6 / A14).

        - Behavior chain supplies observed A→B sequences → strengthens the
          matching transition counts (real-world support).
        - Engineering chain supplies constraints (A14: 约束在事实中) → blocks
          transitions that violate resource/rule constraints.

        Data format alignment: all parties speak ``(from_intent, to_intent,
        weight)``; behavior sequences are injected as counted transitions,
        engineering constraints modulate the final matrix.
        """
        engineering_constraints = engineering_constraints or {}
        blocked: List[Dict[str, str]] = []

        # 1) Behavior chain support: each observed A→B increments the count.
        for seq in (behavior_sequences or []):
            if not isinstance(seq, (tuple, list)) or len(seq) < 2:
                continue
            a, b = str(seq[0]), str(seq[1])
            if a == b:
                continue
            self._total_turns += 1
            self._add_transition(a, b, self._total_turns, confidence=0.8)
            self._intent_sequence.extend([a, b])
            if len(self._intent_sequence) > self.window * 3:
                self._intent_sequence = self._intent_sequence[-self.window * 2:]
            self._intent_distribution[a] = self._intent_distribution.get(a, 0) + 1
            self._intent_distribution[b] = self._intent_distribution.get(b, 0) + 1

        # 2) Engineering constraints: penalize/block violating transitions.
        #    resource_constraints: {tool_or_capability: available(bool)}
        #    forbidden_transitions: [["诊断", "吐槽"], ...]
        forbidden = engineering_constraints.get("forbidden_transitions", [])
        resource = engineering_constraints.get("resource_constraints", {})
        matrix = self.transition_matrix()

        for from_intent, to_counts in list(matrix.items()):
            for to_intent in list(to_counts.keys()):
                violates = (
                    any(f == [from_intent, to_intent] for f in forbidden)
                    or (
                        to_intent in resource
                        and resource.get(to_intent) is False
                    )
                )
                if violates:
                    blocked.append({
                        "from": from_intent, "to": to_intent,
                        "reason": "engineering constraint",
                    })
                    del matrix[from_intent][to_intent]

        return {
            "reconciled_matrix": matrix,
            "behavior_supported": len(behavior_sequences or []),
            "blocked_transitions": blocked,
            "parties": ["association", "behavior", "engineering"],
        }
