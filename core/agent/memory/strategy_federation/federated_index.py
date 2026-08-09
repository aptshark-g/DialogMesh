"""Federated Anchor Index — 10-chain indices unified with temperature tiering.

Each chain provides its own anchor type. Query searches ALL indices in parallel.
Results merged by temperature × relevance.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class AnchorHit:
    """One hit from any index."""
    anchor_id: str
    source: str          # "rag" | "discourse" | "behavior" | "association" | "engineering" | "meta"
    score: float         # relevance score (0-1)
    temperature: int     # 0=Hot, 1=Warm, 2=Cold, 3=Frozen
    data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def priority(self) -> float:
        """Combined priority: relevance × temperature recency."""
        temp_weight = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.1}
        return self.score * temp_weight.get(self.temperature, 0.5)


class FederatedAnchorIndex:
    """Multi-source anchor index with temperature-aware merging.

    Sources:
      - rag: vector embeddings → HNSW
      - discourse: BM25 topic match on DiscourseBlockTree blocks
      - behavior: BehaviorEdge patterns
      - association: EntityNode from RelationSubstrate
      - engineering: MCP tool registry
      - meta: HeuristicChain from DerivationCompressor

    Usage:
        fed = FederatedAnchorIndex()
        fed.add_source("rag", rag_search_fn)
        fed.add_source("discourse", discourse_match_fn)
        hits = fed.search("AES密钥问题")
        # → sorted by temperature × relevance
    """

    def __init__(self, max_workers: int = 6, max_results: int = 20):
        self._sources: Dict[str, Any] = {}  # source_name → search_fn(query, top_k) → List[AnchorHit]
        self.max_workers = max_workers
        self.max_results = max_results
        
        # LRU-style temperature tracking per source
        self._access_counts: Dict[str, int] = {}  # anchor_id → count
        self._last_access: Dict[str, float] = {}

    def add_source(self, name: str, search_fn):
        """Register a search function. 
        search_fn(query: str, top_k: int) → List[AnchorHit]
        """
        self._sources[name] = search_fn

    def search(self, query: str, top_k: int = 10,
              sources: List[str] = None, 
              min_temperature: int = 3) -> List[AnchorHit]:
        """Parallel federated search across all (or specified) sources.

        Args:
            query: search query
            top_k: max results per source
            sources: which sources to search (None = all)
            min_temperature: minimum temperature to include (0=Hot,3=All)
        """
        source_names = sources or list(self._sources.keys())
        if not source_names or not query:
            return []

        results: List[AnchorHit] = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(source_names))) as pool:
            futures = {}
            for name in source_names:
                fn = self._sources.get(name)
                if fn:
                    futures[pool.submit(fn, query, top_k)] = name

            for future in as_completed(futures):
                source_name = futures[future]
                try:
                    hits = future.result()
                    for h in (hits if isinstance(hits, list) else []):
                        if h.temperature <= min_temperature:
                            self._touch(h.anchor_id)
                            results.append(h)
                except Exception as e:
                    logger.debug("Source %s failed: %s", source_name, e)

        # Sort by combined priority (temperature × relevance)
        results.sort(key=lambda h: -h.priority())
        
        # Dedup by anchor_id (keep highest priority)
        seen = set()
        deduped = []
        for h in results:
            if h.anchor_id not in seen:
                seen.add(h.anchor_id)
                deduped.append(h)
            if len(deduped) >= self.max_results:
                break

        return deduped

    def _touch(self, anchor_id: str):
        """Record access for LRU/temperature tracking."""
        self._access_counts[anchor_id] = self._access_counts.get(anchor_id, 0) + 1
        self._last_access[anchor_id] = time.time()

    def get_temperature(self, anchor_id: str) -> int:
        """Get current temperature tier of an anchor."""
        count = self._access_counts.get(anchor_id, 0)
        last = self._last_access.get(anchor_id, 0)
        age = time.time() - last
        
        if count > 10 and age < 60:    return 0  # Hot
        if count > 3 and age < 3600:   return 1  # Warm
        if age < 86400:                return 2  # Cold
        return 3  # Frozen

    def status(self) -> dict:
        return {
            "sources": list(self._sources.keys()),
            "total_anchors": len(self._access_counts),
            "hot_anchors": sum(1 for a in self._access_counts 
                              if self.get_temperature(a) == 0),
        }


# ── Source factories: wrap existing modules as anchor sources ──

def discourse_anchor_source(discourse_tree) -> callable:
    """Wrap DiscourseBlockTree as an anchor source."""
    def search(query: str, top_k: int = 5) -> List[AnchorHit]:
        from core.agent.compiler.topic_quick_match import TopicQuickMatcher
        matcher = TopicQuickMatcher()
        results = []
        
        for session_id in getattr(discourse_tree, '_trees', {}):
            tree = discourse_tree._trees[session_id]
            for block in list(tree.blocks.values())[:20]:
                text = getattr(block, 'raw_text', '') or ''
                status = getattr(block, 'status', 'active')
                temp = {"active": 0, "paused": 1, "cold": 2, "frozen": 3}.get(status, 1)
                
                # Simple keyword overlap scoring
                query_words = set(query)
                text_words = set(text)
                if query_words & text_words:
                    score = len(query_words & text_words) / max(1, len(query_words))
                    results.append(AnchorHit(
                        anchor_id=getattr(block, 'block_id', str(id(block))),
                        source="discourse",
                        score=min(score, 1.0),
                        temperature=temp,
                        data={"text": text[:200], "intent": getattr(block, 'primary_intent', '')},
                    ))
        
        results.sort(key=lambda h: -h.priority())
        return results[:top_k]
    return search


def behavior_anchor_source(behavior_graph=None) -> callable:
    """Wrap BehaviorEdge graph as an anchor source."""
    def search(query: str, top_k: int = 5) -> List[AnchorHit]:
        results = []
        from core.agent.behavior.models import BehaviorEdge
        # This would query the actual graph — placeholder
        return results[:top_k]
    return search


def meta_anchor_source(compressor=None) -> callable:
    """Wrap DerivationCompressor's HeuristicChain pool as an anchor source."""
    def search(query: str, top_k: int = 5) -> List[AnchorHit]:
        results = []
        if not compressor:
            return results
        for chain in getattr(compressor, '_pool', {}).values():
            conditions = getattr(chain, 'conditions', [])
            text = ' '.join(str(c) for c in conditions)
            if any(w in text for w in query.split()[:5]):
                results.append(AnchorHit(
                    anchor_id=getattr(chain, 'chain_id', ''),
                    source="meta",
                    score=getattr(chain, 'freshness', lambda: 0.5)(),
                    temperature=1,
                    data={"conditions": conditions},
                ))
        return results[:top_k]
    return search
