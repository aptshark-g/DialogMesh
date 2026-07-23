# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
import time

SOURCE_CONFIDENCE = {
    "framenet": 0.95, "wordnet": 0.90,
    "conceptnet": 0.80, "wikipedia": 0.70,
    "user_project": 0.85, "web_scrape": 0.60,
    "inference": 0.50, "manual_rule": 0.90, "cache": 0.75,
}

@dataclass
class KnowledgeEntry:
    slot_name: str
    value: str
    candidates: list
    source_name: str = "manual"
    confidence: float = 0.7
    timestamp: float = 0.0
    domain: str = "general"
    metadata: dict = field(default_factory=dict)
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
    @property
    def effective_confidence(self):
        base = SOURCE_CONFIDENCE.get(self.source_name, 0.5)
        return min(1.0, self.confidence * base * 1.1)

@dataclass
class QueryResult:
    entries: list = field(default_factory=list)
    query_time_ms: float = 0.0
    sources_queried: int = 0
    cache_hit: bool = False
    def best(self):
        if not self.entries: return None
        return max(self.entries, key=lambda e: e.effective_confidence)
    def above_threshold(self, threshold=0.5):
        return [e for e in self.entries if e.effective_confidence >= threshold]

class SourceScorer:
    WEIGHTS = {"source_reliability": 0.4, "match_quality": 0.3, "recency": 0.1, "domain_relevance": 0.2}
    def score(self, entry, context=None):
        r = self._source_score(entry) * 0.4
        r += self._match_score(entry) * 0.3
        r += self._recency_score(entry) * 0.1
        r += self._domain_score(entry, context) * 0.2
        return min(1.0, max(0.0, r))
    def _source_score(self, e):
        return SOURCE_CONFIDENCE.get(e.source_name, 0.5)
    def _match_score(self, e):
        if not e.value or not e.candidates: return 0.0
        v = e.value.lower()
        hits = sum(1 for c in e.candidates if c.lower() in v or v in c.lower())
        return max(0.3, min(0.95, hits / max(len(e.candidates), 1)))
    def _recency_score(self, e):
        age = time.time() - e.timestamp
        return max(0.1, 1.0 - age / 864000)
    def _domain_score(self, e, ctx):
        if not ctx or not ctx.get("domain"): return 0.5
        return 0.9 if e.domain == ctx["domain"] else 0.3

class LRUCache:
    def __init__(self, maxsize=500, ttl=3600):
        self.maxsize = maxsize; self.ttl = ttl
        self._data = {}; self._timestamps = {}
    def get(self, key):
        if key not in self._data: return None
        if time.time() - self._timestamps.get(key, 0) > self.ttl:
            del self._data[key]; del self._timestamps[key]
            return None
        return self._data[key]
    def set(self, key, value):
        if len(self._data) >= self.maxsize:
            oldest = min(self._timestamps, key=self._timestamps.get)
            del self._data[oldest]; del self._timestamps[oldest]
        self._data[key] = value
        self._timestamps[key] = time.time()