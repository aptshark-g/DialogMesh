"""Literal Chain Verifier — LLM-first, zero hardcoded keyword lists.

Agent-native: LLM is the decision-maker. Algorithms only provide optional
structural hints (SVO/dependency parse) as context — never as pre-filters.
"""

from __future__ import annotations
from typing import List, Optional
from .models import ChainVote, FilterResult, SubIntent, VerifyContext
from .llm_chain import LLMDrivenChain


class LiteralChainVerifier(LLMDrivenChain):
    """Literal chain: LLM decides, structural parse provides optional hints."""

    def __init__(self, llm=None):
        super().__init__(llm=llm, name="literal")

    def verify(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """LLM-first: no algorithm filter, LLM makes all decisions."""
        if not self.llm:
            return ChainVote(chain=self.name, confidence=0.5, decision="pass",
                           reason="literal: LLM unavailable")

        # Gather structural hints (optional — LLM can ignore)
        structural = self._structural_hints(candidate.text)

        prompt = self._build_llm_prompt(candidate, context, structural)
        try:
            response = self.llm.generate(prompt, max_tokens=200, temperature=0.1)
            return self._parse_llm_response(response)
        except Exception as e:
            return ChainVote(chain=self.name, confidence=0.4, decision="pass",
                           reason=f"literal: {e}")

    def _structural_hints(self, text: str) -> dict:
        """Optional structural hints — LLM can use or ignore."""
        hints = {"len": len(text), "has_question": "?" in text or "？" in text}

        try:
            nlp = self._get_stanza()
            if nlp:
                doc = nlp(text)
                if doc.sentences:
                    words = doc.sentences[0].words
                    hints["verbs"] = [w.text for w in words if w.upos == "VERB"][:3]
                    hints["nouns"] = [w.text for w in words if w.upos == "NOUN"][:5]
                    # Dependency relations as hints — LLM interprets meaning
                    hints["deprel"] = [
                        f"{w.text}:{w.deprel.split(':')[0]}" 
                        for w in words if w.deprel
                    ][:8]
        except Exception:
            pass

        return hints

    def _build_llm_prompt(self, candidate: SubIntent, context: VerifyContext,
                          hints: dict) -> str:
        """LLM decides: is this a multi-intent text that should be split?"""
        import json as _json
        hints_str = _json.dumps(hints, ensure_ascii=False, indent=2) if hints else "{}"
        hist = "\n".join(f"  {h}" for h in (context.history or [])[-3:])
        is_fragment = bool(context.literal and isinstance(context.literal, str)
                          and len(context.literal) > len(candidate.text))

        if is_fragment:
            return f"""You are verifying a fragment from a multi-intent split.

ORIGINAL: "{context.literal[:200]}"
FRAGMENT: "{candidate.text[:200]}"
STRUCTURAL HINTS: {hints_str}
HISTORY: {hist or '(none)'}

Is this fragment a valid, self-contained intent? Output JSON:
{{"decision": "accept" or "reject", "confidence": 0.0-1.0, "reason": "brief"}}"""

        return f"""Does this text contain multiple independent intents that should be split?

TEXT: "{candidate.text[:300]}"
STRUCTURAL HINTS: {hints_str}
HISTORY: {hist or '(none)'}

Consider: conjunctions ("然后"/"接着"), parallelism ("同时"/"顺便"), causality ("所以"/"因此"), and sentence structure (multiple SVOs, different entities per clause).

Output JSON: {{"decision": "accept" or "reject", "confidence": 0.0-1.0, "segments": ["sub-intent 1", "sub-intent 2"], "reason": "brief"}}"""

    def _stanza_segment(self, text: str) -> List[str]:
        """Structural clause boundary detection — LLM hint, not decision."""
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

            split_at = []
            for w in words:
                if w.deprel and w.deprel.split(":")[0] in ("conj", "advcl", "parataxis"):
                    split_at.append(w.id - 1)

            if not split_at:
                return []

            spans = [(w.start_char, w.end_char) for w in words]
            segs = []
            prev = 0
            for idx in split_at:
                if idx > 0 and idx < len(spans):
                    end = spans[idx - 1][1] if idx > 0 else spans[0][1]
                    seg = text[prev:end].strip()
                    if seg and len(seg) > 2:
                        segs.append(seg)
                    prev = spans[idx][0]
            final = text[prev:].strip()
            if final and len(final) > 2:
                segs.append(final)
            return segs if len(segs) > 1 else []
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
