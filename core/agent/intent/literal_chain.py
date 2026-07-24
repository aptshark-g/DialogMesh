"""Literal Chain Verifier — dependency parsing + LLM coordination.

Algorithm layer: Stanza dependency parse → split points detection
LLM layer: verify whether split is semantically reasonable
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from .models import ChainVote, FilterResult, SubIntent, VerifyContext
from .llm_chain import LLMDrivenChain


class LiteralChainVerifier(LLMDrivenChain):
    """Literal chain: structural markers + LLM verify.

    Uses Stanza for dependency parsing as pre-filter.
    """

    def __init__(self, llm=None):
        super().__init__(llm=llm, name="literal")

    def _algorithm_filter(self, candidate: SubIntent, context: VerifyContext) -> FilterResult:
        """Pre-filter: check dependency structure for split feasibility."""
        text = candidate.text

        # If we're in a multi-intent context (context.literal = full text), fragments are valid
        if context.literal and isinstance(context.literal, str) and len(context.literal) > len(text):
            return FilterResult(outcome="accept",
                              reason=f"Fragment of multi-intent split (original: {len(context.literal)} chars)",
                              hints={"is_fragment": True})

        # Strong split signals → fast accept
        sequential = sum(1 for m in ["先", "然后", "接着", "再", "之后", "最后"] if m in text)
        parallel = sum(1 for m in ["同时", "并且", "另外", "还有", "顺便"] if m in text)
        dependency = sum(1 for m in ["所以", "因此", "于是", "因为"] if m in text)
        total_markers = sequential + parallel + dependency

        # Explicit multi-intent markers → accept immediately
        if total_markers >= 2:
            marker_type = "sequential" if sequential > parallel else "parallel"
            return FilterResult(outcome="accept",
                              reason=f"Explicit {marker_type} markers: {total_markers} found",
                              hints={"marker_type": marker_type, "count": total_markers})

        # Single sentence, short, no markers → reject (not multi-intent)
        if total_markers == 0 and len(text) < 20:
            return FilterResult(outcome="reject",
                              reason="Short text, no split markers")

        # Stanza-based candidate extraction → need LLM to verify
        try:
            segments = self._stanza_segment(text)
            if segments and len(segments) > 1:
                return FilterResult(outcome="pass",
                                  hints={"segments": segments, "count": len(segments)})
        except Exception:
            pass

        # Ambiguous → pass to LLM
        return FilterResult(outcome="pass",
                          hints={"markers": total_markers, "text_len": len(text)})

    def _stanza_segment(self, text: str) -> List[str]:
        """Use Stanza to extract clause boundaries. Returns full clause text ranges."""
        try:
            nlp = self._get_stanza()
            if nlp is None:
                return []
            doc = nlp(text)
            if not doc.sentences:
                return []
            
            sent = doc.sentences[0]
            words = sent.words
            if len(words) < 3:
                return []
            
            # Find coordination splits (conj, advcl, parataxis)
            split_indices = [0]
            for w in words:
                if w.deprel and w.deprel.split(":")[0] in ("conj", "advcl", "parataxis"):
                    split_indices.append(w.id - 1)  # word id is 1-indexed
            
            if len(split_indices) <= 1:
                return []
            
            # Reconstruct clauses from text using split positions
            # Use character offsets from token spans
            split_indices.append(len(words))
            original_chars = list(text)
            
            spans = []
            for w in words:
                # Stanza token start_char is 0-indexed
                spans.append((w.start_char, w.end_char))
            
            segments = []
            for i in range(len(split_indices) - 1):
                start = spans[split_indices[i]][0]
                end = spans[split_indices[i+1] - 1][1] if split_indices[i+1] - 1 >= 0 else len(text)
                seg = text[start:end].strip()
                if seg and len(seg) > 2:
                    segments.append(seg)
            
            return segments if len(segments) > 1 else []
        except Exception:
            return []

    _stanza_nlp = None

    @classmethod
    def _get_stanza(cls):
        if cls._stanza_nlp is not None:
            return cls._stanza_nlp
        try:
            import stanza
            stanza.download('zh', verbose=False)
            cls._stanza_nlp = stanza.Pipeline('zh', processors='tokenize,pos,depparse', verbose=False)
            return cls._stanza_nlp
        except Exception:
            return None

    def _build_llm_prompt(self, candidate: SubIntent, context: VerifyContext, hints: dict) -> str:
        """LLM: verify if dependency-based split is semantically valid."""
        segments = hints.get("segments", [])
        seg_desc = "\n".join(f"  - {s}" for s in segments[:5]) if segments else "(stanza unavailable)"
        history = "\n".join(context.history[-3:]) if context.history else "(no history)"

        return f"""Verify if this text contains multiple independent intents that should be split.

TEXT: "{candidate.text[:200]}"
DEPENDENCY SEGMENTS:
{seg_desc}
RECENT HISTORY:
{history}

The literal chain uses structural markers: sequential (先/然后/接着), parallel (同时/并且/顺便), causal (所以/因为).

Output JSON: {{"decision": "accept" or "reject", "confidence": 0.0-1.0, "reason": "brief explanation"}}"""
