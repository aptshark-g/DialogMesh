# -*- coding: utf-8 -*-
"""CredibilityEvaluator — 4-dimension source credibility scoring (§五).

Dimensions:
  1. domain_authority — pre-seeded table, learned over time
  2. freshness — exponential decay e^(-days/365)
  3. citations — normalized citation count
  4. consistency — vs known facts (Meta updates)
"""

from __future__ import annotations

import time
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Pre-seeded domain authority table
DOMAIN_AUTHORITY: Dict[str, float] = {
    "arxiv.org": 0.95,
    "github.com": 0.85,
    "semanticscholar.org": 0.90,
    "docs.python.org": 0.95,
    "en.wikipedia.org": 0.80,
    "medium.com": 0.50,
    "dev.to": 0.45,
    "reddit.com": 0.35,
    "stackoverflow.com": 0.70,
    "blog.csdn.net": 0.40,
    "zhihu.com": 0.45,
    "pypi.org": 0.80,
    "readthedocs.io": 0.85,
    "arxiv": 0.95,
    "duckduckgo": 0.55,
    "scholar": 0.90,
    "github": 0.85,
}


class CredibilityEvaluator:
    """4-dimension source credibility scoring.

    Usage:
      eval = CredibilityEvaluator()
      score = eval.evaluate({"url": "https://arxiv.org/abs/...", "timestamp": ..., "citations": 42})
    """

    # Weights for each dimension
    W_AUTHORITY = 0.30
    W_FRESHNESS = 0.25
    W_CITATIONS = 0.20
    W_CONSISTENCY = 0.25

    def evaluate(self, source: dict) -> float:
        """Score a source 0.0-1.0.

        Args:
            source: dict with keys: url, timestamp, citations, consistency(optional)
        Returns:
            credibility score 0.0-1.0
        """
        domain = self._extract_domain(source.get("url", ""))
        authority = self._get_authority(domain)
        freshness = self._calc_freshness(source.get("timestamp", time.time()))
        citations = self._calc_citation_score(source.get("citations", source.get("stars", 0)))
        consistency = source.get("consistency", 0.5)  # default neutral

        score = (
            self.W_AUTHORITY * authority
            + self.W_FRESHNESS * freshness
            + self.W_CITATIONS * citations
            + self.W_CONSISTENCY * consistency
        )
        logger.debug("Credibility: %s → %.2f (auth=%.2f fresh=%.2f cite=%.2f cons=%.2f)",
                      domain, score, authority, freshness, citations, consistency)
        return min(1.0, max(0.0, score))

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return "unknown"
        # Handle "arxiv" / "github" source names
        if url in DOMAIN_AUTHORITY:
            return url
        # Extract domain from full URL
        parts = url.replace("https://", "").replace("http://", "").split("/")[0]
        # Remove www. prefix
        if parts.startswith("www."):
            parts = parts[4:]
        return parts

    def _get_authority(self, domain: str) -> float:
        """Get domain authority (with fuzzy matching)."""
        if domain in DOMAIN_AUTHORITY:
            return DOMAIN_AUTHORITY[domain]
        # Fuzzy: check if any known domain is contained
        for known, score in DOMAIN_AUTHORITY.items():
            if known in domain or domain in known:
                return score
        return 0.50  # default neutral

    @staticmethod
    def _calc_freshness(timestamp: float) -> float:
        """Exponential decay: e^(-days/365)."""
        days_old = (time.time() - timestamp) / 86400
        freshness = 2.71828 ** (-days_old / 365)
        return max(0.05, min(1.0, freshness))

    @staticmethod
    def _calc_citation_score(citations: int) -> float:
        """Normalize citation count → 0-1."""
        if citations == 0:
            return 0.30  # baseline for no citations
        return min(1.0, 0.30 + citations / 50)

    def update_consistency(self, source_url: str, was_correct: bool):
        """Called by Meta after using a source — adjusts consistency."""
        domain = self._extract_domain(source_url)
        # Future: store per-domain consistency scores in EventLog
        # For now: log + update domain authority bias
        if was_correct:
            DOMAIN_AUTHORITY[domain] = min(1.0, DOMAIN_AUTHORITY.get(domain, 0.5) + 0.02)
        else:
            DOMAIN_AUTHORITY[domain] = max(0.1, DOMAIN_AUTHORITY.get(domain, 0.5) - 0.05)
        logger.info("Credibility: domain=%s correct=%s → authority=%.2f", domain, was_correct, DOMAIN_AUTHORITY.get(domain, 0.5))
