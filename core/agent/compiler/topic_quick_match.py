"""Topic Quick-Match — BM25 + Kurtosis fallback for LLM summary.

Design: docs/BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md
Pattern: recursive convergence — BM25 search → kurtosis gate → decompose or converge.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re, math, logging

logger = logging.getLogger(__name__)


@dataclass
class TopicMatch:
    topic: str
    score: float
    source: str  # "bm25", "bge", "rule"


class TopicQuickMatcher:
    """BM25 + FTS5 fallback. Recursive convergence when LLM unavailable."""
    
    def __init__(self):
        self._topic_index: Dict[str, dict] = {}  # topic → {doc_freq, total_docs}
        self._documents: List[str] = []
        self._doc_topics: List[List[str]] = []
        self.avg_doc_length: float = 0.0
        self.k1: float = 1.2  # BM25 k1 parameter
        self.b: float = 0.75  # BM25 b parameter
    
    def index(self, topic: str, documents: List[str]):
        """Index documents under a topic. Used for known topics (e.g., reverse engineering domains)."""
        self._topic_index[topic] = {
            "docs": documents,
            "term_freq": self._build_term_freq(documents),
            "doc_count": len(documents),
        }
        self._documents.extend(documents)
        self._doc_topics.extend([[topic]] * len(documents))
        self.avg_doc_length = sum(len(d.split()) for d in self._documents) / max(1, len(self._documents))
    
    def _build_term_freq(self, docs: List[str]) -> Dict[str, int]:
        tf: Dict[str, int] = {}
        for doc in docs:
            for word in set(doc.lower().split()):
                tf[word] = tf.get(word, 0) + 1
        return tf
    
    def _bm25_score(self, query: str, document: str) -> float:
        """BM25 scoring: tf-idf with length normalization."""
        query_terms = query.lower().split()
        doc_terms = document.lower().split()
        doc_len = len(doc_terms)
        
        score = 0.0
        for term in query_terms:
            if term not in doc_terms:
                continue
            tf = doc_terms.count(term)
            df = sum(1 for d in self._documents if term in d.lower().split())
            idf = math.log((len(self._documents) - df + 0.5) / max(1, df + 0.5) + 1.0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(1, self.avg_doc_length))
            score += idf * numerator / max(0.001, denominator)
        
        return score
    
    def _kurtosis(self, scores: List[float]) -> float:
        """Kurtosis — high = peaked distribution (confident match)."""
        if len(scores) < 3:
            return 0.0
        n = len(scores)
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / n
        if variance < 0.001:
            return 10.0  # all same → extreme peaked
        m4 = sum((s - mean) ** 4 for s in scores) / n
        return m4 / (variance ** 2)
    
    def match(self, query: str, top_k: int = 3) -> Tuple[List[TopicMatch], bool]:
        """BM25 search → kurtosis gate.
        
        Returns: (matches, is_convergent)
          is_convergent=True: kurtosis high, single confident topic
          is_convergent=False: kurtosis low, need recursive decomposition
        """
        if not self._documents:
            return [], False
        
        scores = [self._bm25_score(query, doc) for doc in self._documents]
        kurt = self._kurtosis(scores)
        
        # Get top-k documents
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]
        matches = []
        for idx, score in ranked:
            if score > 0:
                topic = self._doc_topics[idx][0] if self._doc_topics[idx] else "unknown"
                matches.append(TopicMatch(topic=topic, score=score, source="bm25"))
        
        is_convergent = kurt > 3.0 and len(matches) > 0  # high kurtosis = confident
        logger.debug("BM25: kurt=%.2f, convergent=%s, matches=%d", kurt, is_convergent, len(matches))
        return matches, is_convergent
    
    def summarize(self, text: str) -> str:
        """Generate a summary without LLM — BM25 + rule-based extraction."""
        # Extract entities and key actions
        entities = re.findall(r'0x[0-9a-fA-F]+|[A-Z]{2,}', text)
        words = text.split()
        key_terms = [w for w in words if len(w) > 3 and w.lower() not in ('that', 'this', 'with', 'from', 'what')]
        
        # BM25 match against known topics
        matches, _ = self.match(text, top_k=1)
        
        summary_parts = []
        if matches:
            summary_parts.append(f"[{matches[0].topic}]")
        if entities:
            summary_parts.append("entities: " + ", ".join(entities[:5]))
        if key_terms:
            summary_parts.append(" ".join(key_terms[:8]))
        
        return " → ".join(summary_parts)[:120]
