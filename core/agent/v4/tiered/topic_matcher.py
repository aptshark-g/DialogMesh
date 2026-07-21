"""Recursive Convergence Topic Matcher — replaces regex Tier0 in IntentParser.

Design: BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md
Multi-source fusion (SVO + BM25 + Profile + Anchor) → kurtosis → converge or recurse.
"""

from __future__ import annotations
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TopicMatchResult:
    """Single topic match candidate."""
    def __init__(self, topic: str, score: float, source: str, 
                 confidence: float = 0.0, depth: int = 0):
        self.topic = topic
        self.score = score
        self.source = source
        self.confidence = confidence
        self.depth = depth  # recursion depth (0=direct, 1/2/3=recursive)

    def __repr__(self):
        return f"TopicMatch({self.topic}, {self.score:.2f}, {self.source})"


class TopicFingerprint:
    """Cached fingerprint for fast future matching."""
    def __init__(self, topic: str, vector_hash: int, weight: float = 0.7,
                 creation_depth: int = 0, hit_count: int = 0):
        self.topic = topic
        self.vector_hash = vector_hash
        self.weight = min(0.95, weight)
        self.creation_depth = creation_depth
        self.hit_count = hit_count

    def reinforce(self):
        """Strengthen on repeated hits."""
        self.hit_count += 1
        self.weight = min(0.95, self.weight + 0.05)


class RecursiveConvergenceMatcher:
    """Multi-source topic matcher — kurtosis-driven convergence.

    Usage:
        matcher = RecursiveConvergenceMatcher(jieba_parser, stanza_parser, bm25_index)
        result = matcher.match(text="延迟飙升，没加监控是吗")
        # result.topic, result.confidence, result.depth
    """

    # Source weights (design §5.1)
    W_SVO = 0.30
    W_BM25 = 0.25
    W_ANCHOR = 0.20
    W_PROFILE = 0.15
    W_CONTEXT = 0.10

    # Thresholds (design §7)
    ENTROPY_ALPHA = 0.6      # H < alpha → converge
    KURTOSIS_DIRECT = 1.0     # K > 1.0 → direct match
    MAX_DEPTH = 3             # prevent infinite recursion
    NMI_BETA = 0.03           # delta I ≤ beta → force converge
    FUSION_CONF_GAMMA = 0.7   # FC > gamma → direct return

    def __init__(self, jieba_parser=None, stanza_parser=None, 
                 bm25_index=None, mind=None):
        self._jieba = jieba_parser
        self._stanza = stanza_parser
        self._bm25 = bm25_index
        self._mind = mind
        self._fingerprints: Dict[int, TopicFingerprint] = {}

    # ── public ──────────────────────────────────────────────

    def match(self, text: str, profile_bias: Optional[Dict[str, float]] = None,
              context_topics: Optional[List[str]] = None) -> TopicMatchResult:
        """Main entry — returns best topic match."""

        # Fast path: check fingerprints first
        fp = self._check_fingerprints(text)
        if fp and fp.weight >= 0.85:
            fp.reinforce()
            return TopicMatchResult(fp.topic, fp.weight, "fingerprint", 
                                   fp.weight, 0)

        # Multi-source fusion
        candidates = self._fuse(text, profile_bias, context_topics)

        # Kurtosis check
        k = self._kurtosis([c.score for c in candidates])
        if k > self.KURTOSIS_DIRECT or len(candidates) == 1:
            best = max(candidates, key=lambda c: c.score)
            self._save_fingerprint(text, best.topic, best.score, 0)
            return best

        # Recursive decomposition
        return self._recurse(text, candidates, profile_bias, depth=1)

    # ── internal ────────────────────────────────────────────

    def _fuse(self, text: str, profile_bias: Optional[Dict],
              context_topics: Optional[List]) -> List[TopicMatchResult]:
        """Weighted multi-source fusion."""
        scores: Dict[str, float] = {}

        # SVO extraction (jieba + stanza)
        if self._jieba:
            svos = self._jieba.extract_svo(text)
            for svo in svos:
                topic = self._svo_to_topic(svo)
                scores[topic] = scores.get(topic, 0) + self.W_SVO * 0.8

        # BM25 retrieval
        if self._bm25:
            bm25_results = self._bm25.search(text, topk=5)
            for doc_id, bm25_score in bm25_results:
                topic = self._doc_to_topic(doc_id)
                scores[topic] = scores.get(topic, 0) + self.W_BM25 * min(bm25_score / 10.0, 1.0)

        # Profile bias
        if profile_bias:
            for topic, weight in profile_bias.items():
                scores[topic] = scores.get(topic, 0) + self.W_PROFILE * weight

        # Context topics
        if context_topics:
            for topic in context_topics:
                scores[topic] = scores.get(topic, 0) + self.W_CONTEXT * 0.6

        # Mind anchors
        if self._mind:
            anchors = self._mind.get_anchors(topk=5)
            for anchor in anchors:
                scores[anchor.topic] = scores.get(anchor.topic, 0) + self.W_ANCHOR * anchor.weight

        return [TopicMatchResult(t, s, "fusion", s) 
                for t, s in sorted(scores.items(), key=lambda x: -x[1])[:10]]

    def _kurtosis(self, values: List[float]) -> float:
        """Excess kurtosis — high = peaked distribution (one clear winner)."""
        if len(values) < 2:
            return 3.0  # single candidate = perfect peak
        n = len(values)
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        if var < 1e-10:
            return 10.0  # all same = ultra-peaked
        m4 = sum((v - mean) ** 4 for v in values) / n
        return m4 / (var ** 2) - 3  # excess kurtosis

    def _recurse(self, text: str, candidates: List[TopicMatchResult],
                 profile_bias: Optional[Dict], depth: int) -> TopicMatchResult:
        """Recursive decomposition — split behavior↔object until converge."""
        if depth >= self.MAX_DEPTH:
            best = max(candidates, key=lambda c: c.score)
            self._save_fingerprint(text, best.topic, best.score, depth)
            return best

        # Generate sub-queries from top candidates
        sub_queries = self._decompose(text, candidates[:3])
        if not sub_queries:
            best = max(candidates, key=lambda c: c.score)
            return best

        # Re-fuse with sub-queries
        merged = list(candidates)
        for sq in sub_queries:
            new_candidates = self._fuse(sq, profile_bias, None)
            merged.extend(new_candidates)

        # Re-aggregate
        aggregated: Dict[str, float] = {}
        for c in merged:
            aggregated[c.topic] = aggregated.get(c.topic, 0) + c.score / (depth + 1)

        new_candidates = [TopicMatchResult(t, s, "recursive", s, depth)
                         for t, s in sorted(aggregated.items(), key=lambda x: -x[1])[:10]]

        # Check NMI gain
        k_before = self._kurtosis([c.score for c in candidates])
        k_after = self._kurtosis([c.score for c in new_candidates])
        delta = k_after - k_before

        if delta <= self.NMI_BETA:
            best = max(new_candidates, key=lambda c: c.score)
            self._save_fingerprint(text, best.topic, best.score, depth)
            return best

        return self._recurse(text, new_candidates, profile_bias, depth + 1)

    def _decompose(self, text: str, candidates: List[TopicMatchResult]) -> List[str]:
        """Generate sub-queries by splitting behavior↔object."""
        # Simple: extract key terms from top candidates' topics
        sub_queries = []
        seen = set()
        for c in candidates[:3]:
            terms = c.topic.replace("_", " ").split()
            for t in terms:
                if t not in seen and len(t) > 2:
                    sub_queries.append(t)
                    seen.add(t)
        return sub_queries[:5]

    def _check_fingerprints(self, text: str) -> Optional[TopicFingerprint]:
        text_hash = hash(text.lower())
        fp = self._fingerprints.get(text_hash)
        if fp:
            # Check decay
            fp.weight = fp.weight * math.exp(-0.01 * 0)  # daily decay, 0 days
            if fp.weight < 0.3:
                del self._fingerprints[text_hash]
                return None
            return fp
        return None

    def _save_fingerprint(self, text: str, topic: str, confidence: float, depth: int):
        text_hash = hash(text.lower())
        base_weight = 0.85 if depth > 0 else 0.7  # recursive is more reliable
        self._fingerprints[text_hash] = TopicFingerprint(
            topic=topic, vector_hash=text_hash, 
            weight=base_weight * confidence,
            creation_depth=depth, hit_count=1,
        )
        if self._mind:
            try:
                self._mind.upsert_anchor(topic, weight=base_weight * confidence)
            except: pass

    @staticmethod
    def _svo_to_topic(svo: dict) -> str:
        """Convert SVO triple to topic string."""
        verb = svo.get("verb", "")
        obj = svo.get("obj", "")
        return f"{obj}_{verb}" if obj and verb else "unknown"

    @staticmethod
    def _doc_to_topic(doc_id: str) -> str:
        return doc_id.split("_topic_")[-1] if "_topic_" in doc_id else doc_id
