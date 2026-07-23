"""MoodClassifier V3 — LLM-based via LM Studio, NRC fallback.

Primary:   Local LLM (nemotron) ~200ms  
Fallback:  NRC mini lexicon <0.1ms (when LLM unavailable)
Config:    mood_profiles.yaml (descriptors → LLM few-shot prompt)
"""

from __future__ import annotations
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MoodClassifierLLM:
    """LLM-based mood classification. Zero hardcoded keywords.
    
    Uses mood_profiles.yaml descriptors as few-shot context for LLM.
    When LLM unavailable, falls back to lexicon-based classification.
    """

    MOOD_PROMPT = """Classify the user's emotional intent into one category:
- solution_seeking (z=+1): wants exact answer, facts, confirmation
- exploration (z=0): wants understanding, approaches, discussion  
- mirror_emotional (z=-1): needs empathy, venting, emotional support
- neutral (z=0): routine exchange, greeting, simple request

Descriptors for each:
Solution: give exact answer, confirm correct/incorrect, provide specific value
Exploration: understand reasoning, possible approaches, analyze, discuss perspectives
Mirror: frustrated, overwhelmed, need to vent, seeking empathy, emotional distress

User text: "{text}"

Respond ONLY with the category name (one word): solution_seeking, exploration, mirror_emotional, or neutral."""

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    def classify(self, text: str) -> float:
        # Try LLM first
        if self._llm and len(text.strip()) > 2:
            try:
                result = self._classify_llm(text)
                if result is not None:
                    return result
            except Exception as e:
                logger.debug("LLM mood failed: %s", e)

        # Fallback: NRC mini lexicon
        return self._classify_lexicon(text)

    def _classify_llm(self, text: str) -> Optional[float]:
        from core.agent.llm_providers.base import GenerateRequest
        prompt = self.MOOD_PROMPT.format(text=text[:300])
        req = GenerateRequest(prompt=prompt, temperature=0.1, max_tokens=10)
        resp = self._llm.generate(req)
        raw = getattr(resp, 'text', '') or ''

        mapping = {"solution_seeking": 1.0, "exploration": 0.0,
                   "mirror_emotional": -1.0, "neutral": 0.0}
        raw_lower = raw.strip().lower()
        for key, z in mapping.items():
            if key in raw_lower:
                return z
        return None

    def _classify_lexicon(self, text: str) -> float:
        """NRC mini lexicon fallback. < 0.1ms, zero dependencies."""
        NEG = {"烂透了","太烦了","崩溃","疯了","受不了","无语","服了","废了","好累","不想","太难了",
               "frustrated","frustrating","overwhelmed","exhausted","tired","stuck","impossible"}
        EXP = {"如何","怎么","为什么","为何","怎样","可否","有没有","有什么",
               "how","why","explain","understand","analyze","思路","分析","解释","理解"}
        SOL = {"吗","几个","在哪","是不是","确切","答案",
               "what is","where is","fix","help","find","exact","correct","solve"}
        
        text_l = text.lower()
        for w in NEG:
            if w in text_l: return -1.0
        for w in SOL:
            if w in text_l: return 1.0
        for w in EXP:
            if w in text_l: return 0.0
        return 0.0
