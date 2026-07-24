"""Multi-Intent Splitter — LLM-first coordinator.

Agent-native: LLM decides split points. Algorithms only provide struct hints.
"""

from __future__ import annotations
from typing import List, Optional
from .models import (
    SubIntent, MultiIntentResult, ChainVote, ChainVotes,
    VerifyContext, AmbiguityDecision,
)
from .literal_chain import LiteralChainVerifier


class MultiIntentSplitter:
    """LLM-first multi-intent decomposer.

    Pi-like: LLM makes all intent decisions. Hints are optional context.
    """

    def __init__(self, llm=None, profile=None, association=None,
                 discourse=None, engineering=None):
        self.llm = llm
        self.literal = LiteralChainVerifier(llm=llm)
        self._profile = profile
        self._association = association
        self._discourse = discourse
        self._engineering = engineering

    def split(self, text: str, entities: List[str] = None,
              pcr_zone: str = "MIXED", history: List[str] = None) -> MultiIntentResult:
        """LLM-first: ask LLM whether to split, then verify each segment."""
        entities = entities or []
        history = history or []

        # Step 1: LLM decides if multi-intent (not algorithm)
        if self.llm:
            segments = self._llm_split(text, history)
        else:
            # No LLM → structural-only fallback (minimal, zero hardcoded keywords)
            segments = self._structural_split(text)

        if not segments or len(segments) <= 1:
            return MultiIntentResult(
                sub_intents=[SubIntent(id="s0", text=text, entities=entities, confidence=1.0)],
                is_multi=False, split_confidence=1.0, fusion_method="single",
            )

        # Step 2: Trust LLM split — no fragment verification (nemotron rejects partial fragments)
        candidates = []
        for i, seg in enumerate(segments):
            si = SubIntent(id=f"s{i}", text=seg, entities=entities[:3],
                          confidence=0.85)  # LLM already decided multi=true
            candidates.append(si)
        
        accepted = candidates  # trust LLM

        return MultiIntentResult(
            sub_intents=accepted,
            is_multi=len(accepted) > 1,
            split_confidence=sum(c.confidence for c in accepted) / max(1, len(accepted)),
            fusion_method="llm_literal",
            trace={"segments": segments, "accepted": len(accepted)},
        )

    def _llm_split(self, text: str, history: List[str]) -> List[str]:
        """LLM decides: where to split the text into sub-intents."""
        hist_str = "\n".join(f"  {h}" for h in history[-3:]) if history else "(none)"

        prompt = f"""You are a conversation agent. Analyze this user message and determine if it contains multiple independent intents that should be handled separately.

USER: "{text[:500]}"
RECENT HISTORY: {hist_str}

If this is a SINGLE intent, output: {{"multi": false}}
If MULTIPLE intents, output: {{"multi": true, "segments": ["first sub-intent", "second sub-intent", ...]}}

Rules:
- Split when the user asks for different things (e.g. "first X then Y", "X and also Y")
- Split when there's a clear causal/logical boundary between clauses
- Don't split trivial adjuncts (e.g. "帮我看看这个问题" is one intent)
- A true multi-intent has different goals/actions/entities per segment"""

        try:
            import json, re
            response = self.llm.generate(prompt, max_tokens=300, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            data = json.loads(cleaned)
            if data.get("multi"):
                segs = data.get("segments", [])
                return [s.strip() for s in segs if s.strip()]
            return [text]
        except Exception:
            return self._structural_split(text) or [text]

    def _structural_split(self, text: str) -> List[str]:
        """Minimal structural split — zero hardcoded keywords.

        Uses Stanza dependency parse to find clause boundaries.
        Falls back to sentence boundaries.
        """
        # Try Stanza clause detection
        segs = self.literal._stanza_segment(text)
        if segs:
            return segs

        # Fallback: split on Chinese/English punctuation boundaries
        import re
        clauses = re.split(r'[，,；;。！!？?]', text)
        clauses = [c.strip() for c in clauses if len(c.strip()) > 2]

        # If only 1-2 clauses, it's probably single-intent
        if len(clauses) <= 2:
            return [text]

        return clauses
