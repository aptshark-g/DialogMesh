"""LLM posterior coreference verification + F1 evaluation — Tier 3.

Uses LLM (via Gateway) to verify uncertain coreference pairs from Tiers 1+2.
Produces F1 evaluation metrics: precision, recall, F1 for the hybrid pipeline.

Design: COREFERENCE_HYBRID_DESIGN.md — fusion formula + evaluation metrics.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("dm.llm_coref")


@dataclass
class CorefVerdict:
    """LLM verification result for a coreference pair."""
    mention_a: str
    mention_b: str
    verdict: str  # YES / NO
    confidence: float  # 0-100
    reasoning: str = ""


@dataclass
class CorefMetrics:
    """F1 evaluation metrics for coreference resolution."""
    tp: int = 0  # correctly resolved
    fp: int = 0  # incorrectly resolved
    fn: int = 0  # missed coreferences
    total_pairs: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


class LLMCorefVerifier:
    """LLM posterior — verifies uncertain coref pairs via Gateway.

    Only called when Tier 1+2 fused score is below threshold (< 0.5).
    Reduces LLM calls by ~70% vs LLM-only approach.
    """

    VERIFY_PROMPT = """Analyze whether these two mentions refer to the same entity.

Context: {context}
Mention A: {mention_a}
Mention B: {mention_b}

Do A and B refer to the same entity?
Answer format: {{"verdict": "YES"|"NO", "confidence": 0-100, "reasoning": "...(1 sentence)"}}
JSON:"""

    def __init__(self, gateway=None):
        self._gateway = gateway
        self._cache: Dict[Tuple[str, str], CorefVerdict] = {}
        self.metrics = CorefMetrics()

    def verify(self, mention_a: str, mention_b: str,
               context: str = "") -> CorefVerdict:
        """Verify coreference pair via LLM. Uses cache for identical pairs."""
        cache_key = (mention_a, mention_b)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self._gateway:
            # No gateway — return neutral verdict
            verdict = CorefVerdict(
                mention_a=mention_a, mention_b=mention_b,
                verdict="UNCERTAIN", confidence=50.0,
                reasoning="LLM not available"
            )
        else:
            prompt = self.VERIFY_PROMPT.format(
                context=context, mention_a=mention_a, mention_b=mention_b
            )
            try:
                response = self._gateway.ask(prompt)
                verdict = self._parse_response(response, mention_a, mention_b)
            except Exception as e:
                logger.warning("LLM verification failed: %s", e)
                verdict = CorefVerdict(
                    mention_a=mention_a, mention_b=mention_b,
                    verdict="ERROR", confidence=50.0,
                    reasoning=str(e)[:100]
                )

        self._cache[cache_key] = verdict
        return verdict

    def _parse_response(self, response: str, a: str, b: str) -> CorefVerdict:
        """Parse LLM JSON response."""
        try:
            # Extract JSON block if embedded in markdown
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return CorefVerdict(
                    mention_a=a, mention_b=b,
                    verdict=data.get("verdict", "UNCERTAIN"),
                    confidence=float(data.get("confidence", 50)),
                    reasoning=data.get("reasoning", "")[:200]
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("JSON parse failed: %s", e)

        # Fallback: check for YES/NO in text
        upper = response.upper()
        verdict = "YES" if "YES" in upper and "NO" not in upper else "NO"
        return CorefVerdict(
            mention_a=a, mention_b=b,
            verdict=verdict, confidence=50.0,
            reasoning=response[:200]
        )

    # ── Evaluation ──

    def evaluate(self, pairs: List[Tuple[str, str, bool]],
                 context: str = "") -> CorefMetrics:
        """Evaluate pipeline against labeled pairs.

        Args:
            pairs: [(mention_a, mention_b, is_true_coref), ...]
            context: Shared context for all pairs
        Returns:
            CorefMetrics with precision/recall/F1
        """
        metrics = CorefMetrics(total_pairs=len(pairs))

        for mention_a, mention_b, is_true in pairs:
            verdict = self.verify(mention_a, mention_b, context)
            predicted = verdict.verdict == "YES" and verdict.confidence > 60

            if predicted and is_true:
                metrics.tp += 1
            elif predicted and not is_true:
                metrics.fp += 1
            elif not predicted and is_true:
                metrics.fn += 1
            # else: true negative — correct rejection

        self.metrics = metrics
        return metrics

    def stats(self) -> dict:
        return {
            "precision": f"{self.metrics.precision:.1%}",
            "recall": f"{self.metrics.recall:.1%}",
            "f1": f"{self.metrics.f1:.1%}",
            "total_pairs": self.metrics.total_pairs,
            "cache_hits": len(self._cache),
        }
