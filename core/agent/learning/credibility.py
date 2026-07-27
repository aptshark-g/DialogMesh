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

    # Weights for each dimension (4 → now 3; consistency is SelfCheck)
    W_AUTHORITY = 0.25
    W_FRESHNESS = 0.20
    W_CITATIONS = 0.15
    W_SELFCHECK = 0.40  # SelfCheckGPT-style — LLM validates its own source

    def evaluate(self, source: dict) -> float:
        """Score a source 0.0-1.0 using 4-dimension credibility.

        L1: domain_authority (fast, cached)
        L2: freshness + citations (computed)
        L3: SelfCheck (LLM — checks internal consistency of the source content)
        """
        domain = self._extract_domain(source.get("url", ""))
        authority = self._get_authority(domain)
        freshness = self._calc_freshness(source.get("timestamp", time.time()))
        citations = self._calc_citation_score(source.get("citations", source.get("stars", 0)))
        selfcheck = self._selfcheck(source)

        score = (
            self.W_AUTHORITY * authority
            + self.W_FRESHNESS * freshness
            + self.W_CITATIONS * citations
            + self.W_SELFCHECK * selfcheck
        )
        logger.debug("Credibility: %s → %.2f (auth=%.2f fresh=%.2f cite=%.2f sc=%.2f)",
                      domain, score, authority, freshness, citations, selfcheck)
        return min(1.0, max(0.0, score))

    def _selfcheck(self, source: dict) -> float:
        """SelfCheckGPT-style: LLM checks if the content is internally consistent.

        Generates 3 facts from the content, then asks LLM if they're consistent.
        Returns 0.0-1.0 (1.0 = fully self-consistent).
        """
        content = source.get("content", source.get("snippet", ""))
        if not content or len(content) < 100:
            return 0.5  # neutral for short content

        try:
            prompt = (
                f"阅读以下内容，判断其内部是否一致、可靠。\n\n"
                f"内容: {content[:1500]}\n\n"
                f"请回答:\n"
                f"1. 该内容是否有明显矛盾? (是/否)\n"
                f"2. 其数据或引用是否可信? (是/否/不确定)\n"
                f"3. 整体可靠性 0-10 分\n\n"
                f"只输出: 一致性=是/否; 引用可信=是/否/不确定; 评分=0-10"
            )

            import urllib.request, json
            body = json.dumps({
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "messages": [
                    {"role": "system", "content": "你是可靠性评估器。严格但公正地评估内容。"},
                    {"role": "user", "content": prompt},
                ],
            }).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=body,
                headers={"Authorization": "Bearer dm-client", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse: 一致性=是; 引用可信=是; 评分=8
            import re
            score_match = re.search(r'评分\s*[:=]\s*(\d+)', reply)
            score = int(score_match.group(1)) / 10.0 if score_match else 0.5

            # Boost if consistent + credible
            if "一致性=是" in reply or "一致性：是" in reply:
                score = max(0.5, score)
            if "否" in reply.split("一致性")[1].split(";")[0] if "一致性" in reply else False:
                score = min(0.4, score)

            return min(1.0, score)
        except Exception as e:
            logger.debug("SelfCheck failed: %s — using 0.5 default", e)
            return 0.5  # Default neutral when LLM unavailable

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
