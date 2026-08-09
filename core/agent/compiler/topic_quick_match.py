"""Topic Quick-Match — BM25 + Kurtosis fallback for LLM summary.

Design: docs/BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md
Pattern: recursive convergence — BM25 search → kurtosis gate → decompose or converge.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from core.agent.llm_config import DEFAULT as _LLM_CFG
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
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text — whitespace for English, jieba for Chinese."""
        # Try jieba for Chinese segmentation
        try:
            import jieba
            return [t for t in jieba.cut(text) if len(t.strip()) > 1]
        except ImportError:
            pass
        # Fallback: character n-grams for Chinese + whitespace for English
        tokens = []
        for word in text.lower().split():
            if any('\u4e00' <= c <= '\u9fff' for c in word):
                # Chinese word → 2-char n-grams
                tokens.extend(word[i:i+2] for i in range(len(word)-1))
            else:
                tokens.append(word)
        return tokens

    def _build_term_freq(self, docs: List[str]) -> Dict[str, int]:
        tf: Dict[str, int] = {}
        for doc in docs:
            for word in set(self._tokenize(doc)):
                tf[word] = tf.get(word, 0) + 1
        return tf
    
    def _bm25_score(self, query: str, document: str) -> float:
        """BM25 scoring: tf-idf with length normalization."""
        query_terms = self._tokenize(query)
        doc_terms = self._tokenize(document)
        doc_len = len(doc_terms)
        
        score = 0.0
        for term in query_terms:
            if term not in doc_terms:
                continue
            tf = doc_terms.count(term)
            df = sum(1 for d in self._documents if term in self._tokenize(d))
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
            summary_parts.append("terms: " + ", ".join(key_terms[:5]))
        return " | ".join(summary_parts)

    def verify_with_llm(self, query: str, matches: List[TopicMatch], llm) -> Optional[str]:
        """BM25 fast match → LLM slow verification. LLM makes final decision.

        Returns: confirmed topic name, or None if LLM rejects all BM25 matches.
        """
        if not llm or not matches:
            return matches[0].topic if matches else None
        
        import json
        match_desc = "\n".join(
            f"  {i+1}. {m.topic} (BM25 score={m.score:.2f})"
            for i, m in enumerate(matches[:5])
        )
        
        prompt = f"""BM25 matched these topics for a user message. Verify which is correct.

QUERY: "{query[:200]}"
BM25 MATCHES:
{match_desc}

Output JSON: {{"decision": "accept" or "reject", "best_topic": "topic_name", "confidence": 0.0-1.0, "reason": "brief"}}"""
        
        try:
            import re
            response = llm.generate(prompt, max_tokens=_LLM_CFG.max_tokens, temperature=_LLM_CFG.temperature)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            cleaned = cleaned.replace("\\'", "'")
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                cleaned = cleaned[s:e+1]
            data = json.loads(cleaned)
            if data.get("decision") == "accept" and data.get("best_topic"):
                return data["best_topic"]
        except Exception:
            pass
        return matches[0].topic if matches else None
    def dual_track_match(self, query: str, llm) -> dict:
        matches, _ = self.match(query, top_k=3)
        bm25_topic = matches[0].topic if matches else None
        bm25_score = matches[0].score if matches else 0.0
        llm_topic = self.verify_with_llm(query, matches, llm) if llm else bm25_topic
        if not bm25_topic and not llm_topic:
            return {'topic': None, 'drift': False, 'confidence': 0.0}
        drifted = bm25_topic and llm_topic and bm25_topic != llm_topic and bm25_score > 0
        if drifted:
            self._record_drift(query, bm25_topic, llm_topic)
        return {'topic': llm_topic or bm25_topic, 'drift': drifted,
                'confidence': bm25_score if bm25_topic == llm_topic else 0.5}
    
    def _record_drift(self, query, from_topic, to_topic):
        if not hasattr(self, '_drift_log'):
            self._drift_log = {}
        key = f'{from_topic}->{to_topic}'
        self._drift_log.setdefault(key, []).append(query[:100])
        if len(self._drift_log[key]) >= 3:
            self._migrate(from_topic, to_topic, self._drift_log[key])
            self._drift_log[key] = []
    
    def _migrate(self, from_topic, to_topic, queries):
        moved = 0
        for i, doc in enumerate(self._documents):
            if self._doc_topics[i][0] == from_topic:
                for q in queries:
                    if any(t in doc for t in self._tokenize(q)):
                        self._doc_topics[i] = [to_topic]
                        moved += 1
                        break
        if moved:
            logger.info('Migrated: %s->%s (%d docs)', from_topic, to_topic, moved)
