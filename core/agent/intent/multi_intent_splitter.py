"""Multi-Intent Splitter — 5-chain LLM-dominant coordinator.

Agent-native: LLM is the default verifier, algorithms only do pre-filtering.
Divergence→Convergence pattern: literal split → chain verify → fusion → ambiguity resolve.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from .models import (
    SubIntent, MultiIntentResult, ChainVote, ChainVotes,
    VerifyContext, AmbiguityDecision, EngineeringContext,
)
from .literal_chain import LiteralChainVerifier


class MultiIntentSplitter:
    """Multi-intent decomposition with LLM-coordinated chain verification.

    Usage:
        splitter = MultiIntentSplitter(llm=deepseek)
        result = splitter.split(text="先定位再修复",
                               entities=[...],
                               pcr_zone="EXPLORE",
                               history=["上次你说延迟飙升..."])
    """

    def __init__(self, llm=None, profile=None, association=None,
                 discourse=None, engineering=None):
        self.llm = llm

        # Chains (lazy init — full chains added in Phase 2)
        self.literal = LiteralChainVerifier(llm=llm)
        self._profile = profile
        self._association = association
        self._discourse = discourse
        self._engineering = engineering

    def split(self, text: str, entities: List[str] = None,
              pcr_zone: str = "MIXED", history: List[str] = None) -> MultiIntentResult:
        """Main entry: split text into sub-intents with chain verification."""
        entities = entities or []
        history = history or []

        # Stage A: Literal split — dependency parsing → candidate segments
        fragments = self._literal_split(text)
        if len(fragments) <= 1:
            return MultiIntentResult(
                sub_intents=[SubIntent(id="s0", text=text, entities=entities, confidence=1.0)],
                is_multi=False,
                split_confidence=1.0,
                fusion_method="single",
            )

        # Stage B: Build candidates + verify with literal chain
        candidates = []
        for i, seg in enumerate(fragments):
            si = SubIntent(
                id=f"s{i}", text=seg, entities=entities[:3],
                confidence=0.5,
            )
            # Pass original text as context so chain knows this is a split
            ctx = VerifyContext(history=history)
            ctx.literal = text  # full text context for chain
            vote = self.literal.verify(si, ctx)
            si.chain_votes["literal"] = vote.confidence
            si.confidence = vote.confidence
            candidates.append(si)
        # Stage C: Fusion (simple for Phase 1 — literal-only vote)
        # Phase 2 adds: profile/association/discourse chains + weighted/LLM fusion
        accepted = [c for c in candidates if c.confidence > 0.3]  # lower bar for split fragments

        # Stage D: Ambiguity gate (basic)
        ambiguities = []
        for c in accepted:
            if c.confidence < 0.4:
                ambiguities.append(AmbiguityDecision(
                    trigger="low_confidence",
                    score=1 - c.confidence,
                    action="ask_user" if not self.llm else "llm_resolve",
                ))

        return MultiIntentResult(
            sub_intents=accepted,
            is_multi=len(accepted) > 1,
            split_confidence=sum(c.confidence for c in accepted) / max(1, len(accepted)),
            fusion_method="literal_only",
            ambiguities=ambiguities,
            trace={"fragments": fragments, "candidates": len(candidates), "accepted": len(accepted)},
        )

    def _literal_split(self, text: str) -> List[str]:
        """Stage A: Split text using dependency parse + markers.

        If Stanza unavailable, fall back to marker-based split.
        """
        # Try Stanza segments first
        segments = self.literal._stanza_segment(text)
        if segments:
            return segments

        # Fallback: marker-based split (structural, not semantic)
        markers = ["然后", "接着", "并且", "同时", "另外", "顺便", "还有", "所以", "因此", "于是"]
        parts = [text]
        for m in markers:
            new_parts = []
            for p in parts:
                if m in p:
                    splits = p.split(m, 1)
                    new_parts.extend(s for s in splits if s.strip())
                else:
                    new_parts.append(p)
            parts = new_parts

        # If no split found, return as single
        if len(parts) <= 1:
            return [text]

        return [p.strip() for p in parts if p.strip()]
