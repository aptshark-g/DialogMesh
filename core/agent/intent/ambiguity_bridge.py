"""Intent-Ambiguity Bridge — flows multi-perspective deadlock into L2.5 belief.

Pattern: deadlock → Bayesian evidence → temporal resolution → consensus.
"""

from __future__ import annotations
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from .multi_perspective import MultiPerspectiveAnalyzer, PerspectiveAnalysis, MultiPerspectiveResult


@dataclass
class AmbiguityResolution:
    """Resolution of an ambiguous multi-intent analysis."""
    resolved: bool                    # whether ambiguity was resolved
    is_multi: bool
    segments: List[str] = field(default_factory=list)
    confidence: float = 0.0
    method: str = ""                  # "consensus" | "bayesian" | "pending"
    pending_reason: str = ""


@dataclass
class BeliefEvidence:
    """Evidence packet for L2.5 belief accumulator."""
    intent: str                       # "multi_intent_split" | "single_intent"
    confidence: float
    perspectives: Dict[str, str] = field(default_factory=dict)  # {literal: accept, ...}
    turn: int = 0


class IntentAmbiguityResolver:
    """Multi-perspective → deadlock → belief accumulator bridge.

    Usage:
        bridge = IntentAmbiguityResolver(llm=deepseek, belief_acc=l2_5_accumulator)
        result = bridge.resolve("先定位延迟然后修复",
                               profile=..., association=..., history=...)
        if result.resolved:
            # consensus reached
        else:
            # evidence pending — belief accumulator will resolve over time
    """

    def __init__(self, llm=None, belief_acc=None):
        self.analyzer = MultiPerspectiveAnalyzer(llm=llm)
        self.belief = belief_acc
        self._turn = 0

    def resolve(self, text: str, profile: dict = None,
                association: dict = None, history: List[str] = None) -> AmbiguityResolution:
        """Multi-perspective analysis → consensus or belief pipeline."""
        self._turn += 1
        result = self.analyzer.analyze(text, profile, association, history)

        # Check consensus
        accepts = sum(1 for a in result.analyses if a.decision == "accept")
        rejects = sum(1 for a in result.analyses if a.decision == "reject")
        total = len(result.analyses)

        # Strong consensus → resolved immediately
        if accepts >= total * 0.75 or rejects >= total * 0.75:
            return AmbiguityResolution(
                resolved=True,
                is_multi=accepts > rejects,
                segments=result.segments,
                confidence=result.confidence,
                method="consensus",
            )

        # Deadlock or weak signal → feed into belief accumulator
        evidence = BeliefEvidence(
            intent="multi_intent_split" if accepts > rejects else "single_intent",
            confidence=accepts / max(1, total) if accepts > rejects else rejects / max(1, total),
            perspectives={a.perspective: a.decision for a in result.analyses},
            turn=self._turn,
        )

        if self.belief:
            # Feed evidence → Bayesian accumulator tracks over time
            self.belief.ingest_ambiguity_evidence(evidence)

            # Check if belief has crystallized
            belief_state = self.belief.get_ambiguity_belief()
            if belief_state and belief_state.get("locked"):
                return AmbiguityResolution(
                    resolved=True,
                    is_multi=belief_state.get("is_multi", False),
                    confidence=belief_state.get("confidence", 0.5),
                    method="bayesian",
                )

        # Still pending — need more evidence from future turns
        return AmbiguityResolution(
            resolved=False,
            is_multi=accepts > rejects,
            confidence=result.confidence,
            method="pending",
            pending_reason=f"Deadlock: {accepts} accept, {rejects} reject out of {total}. Evidence queued for belief accumulation.",
        )
