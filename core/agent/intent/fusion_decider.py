"""FusionDecider — auto-select fusion strategy from chain vote spread (D-11).

Design: ENGINEERING_MULTI_INTENT_SPLIT (三策略自动选)
  - vote_consensus  : std < 0.3  → majority vote, 0ms
          - weighted_mix    : 0.3 ≤ std ≤ 0.45 → confidence-weighted blend, 0ms
          - llm_adjudicate  : std > 0.45 → LLM arbitrates, 100-300ms

Note: confidences are 0..1, so pstdev's theoretical maximum is 0.5 (half
0s / half 1s). The original "std > 0.5" trigger was unreachable; 0.45 is the
honest high-divergence threshold.

PCR regulation (D-14): complexity > 0.8 forces LLM adjudication; noise > 0.7
weights literal ×1.5 and discourse ×0.7.
"""

from __future__ import annotations
import statistics
from typing import Dict, List, Optional

from .models import ChainVotes, ChainVote, SubIntent, MultiIntentResult, AmbiguityDecision


class FusionDecider:
    """Chooses and runs the fusion strategy for chain verification votes."""

    def __init__(self, llm=None):
        self.llm = llm

    def decide(
        self,
        candidate: SubIntent,
        votes: ChainVotes,
        pcr_complexity: float = 0.0,
        pcr_noise: float = 0.0,
    ) -> MultiIntentResult:
        """Fuse per-chain votes into a decision for one candidate sub-intent."""
        confidences = [v.confidence for v in votes.votes.values()]
        if not confidences:
            return MultiIntentResult(
                sub_intents=[candidate],
                is_multi=False,
                split_confidence=0.5,
                fusion_method="vote_consensus",
            )

        # PCR force: high complexity → LLM arbitration regardless of spread.
        if pcr_complexity > 0.8 and self.llm:
            method = "llm_adjudicate"
        else:
            std = statistics.pstdev(confidences) if len(confidences) > 1 else 0.0
            method = (
                "vote_consensus" if std < 0.3
                else "weighted_mix" if std <= 0.45
                else "llm_adjudicate"
            )

        accept = votes.accept_count
        reject = votes.reject_count
        n = votes.active_count

        if method == "vote_consensus":
            outcome = accept > reject
            confidence = votes.consensus_level
        elif method == "weighted_mix":
            # Confidence-weighted: accept votes pull up, reject votes pull down.
            # PCR noise: boost literal signal (×1.5), damp discourse (×0.7).
            # Applied locally — never mutates the caller's ChainVote objects.
            adj = {
                name: (
                    min(1.0, v.confidence * 1.5) if name == "literal"
                    else v.confidence * 0.7 if name == "discourse"
                    else v.confidence
                )
                for name, v in votes.votes.items()
            } if pcr_noise > 0.7 else {
                name: v.confidence for name, v in votes.votes.items()
            }
            score = sum(
                adj[name] if v.decision == "accept" else -adj[name]
                for name, v in votes.votes.items()
            )
            outcome = score > 0
            confidence = min(1.0, abs(score) / max(1, n))
        else:  # llm_adjudicate
            outcome, confidence = self._llm_adjudicate(candidate, votes)

        candidate.chain_votes = {k: v.confidence for k, v in votes.votes.items()}
        candidate.confidence = confidence

        return MultiIntentResult(
            sub_intents=[candidate] if outcome else [],
            is_multi=False,
            split_confidence=confidence,
            fusion_method=method,
            trace={"accept": accept, "reject": reject, "total": n, "method": method},
        )

    def _llm_adjudicate(self, candidate: SubIntent, votes: ChainVotes) -> tuple:
        if not self.llm:
            return votes.accept_count > votes.reject_count, votes.consensus_level
        lines = "\n".join(
            f"  {v.chain}: {v.decision} ({v.confidence:.2f}) — {v.reason}"
            for v in votes.votes.values()
        )
        prompt = (
            f"Intent sub-task: \"{candidate.text[:200]}\"\n"
            f"Chain votes:\n{lines}\n\n"
            'Decide if this sub-intent is valid. Return JSON: {"accept": true/false, "confidence": 0-1, "reason": "..."}'
        )
        try:
            import json, re
            resp = self.llm.generate(prompt, max_tokens=120, temperature=0.1)
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", str(resp))
            data = json.loads(cleaned.strip())
            return bool(data.get("accept", True)), float(data.get("confidence", 0.6))
        except Exception:
            return votes.accept_count > votes.reject_count, votes.consensus_level
