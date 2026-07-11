"""HybridSearch (keyword+summary) and HyDERetriever."""
from __future__ import annotations
import logging
from typing import Callable, List, Optional
from .unified_graph_store import UnifiedGraphStore
from .unified_search import UnifiedSearch

logger = logging.getLogger(__name__)


class HybridSearchEngine:

    def __init__(self, store: UnifiedGraphStore, embedding_fn: Callable = None):
        self._store = store
        self._searcher = UnifiedSearch(store)
        self._embedding_fn = embedding_fn

    def search(self, query: str, domain: str = None,
               node_type: str = None, limit: int = 20) -> List[dict]:
        kw = self._searcher.keyword_search(query, domain, node_type, limit)
        sm = self._searcher.summary_search(query, domain, node_type, limit)
        seen = set()
        merged = []
        for r in kw + sm:
            nid = r.get("node_id", "")
            if nid not in seen:
                seen.add(nid)
                merged.append(r)
        merged.sort(key=lambda n: n.get("importance", 0), reverse=True)
        return merged[:limit]


class HyDERetriever:

    def __init__(self, searcher, expand_fn: Callable = None):
        self._searcher = searcher
        self._expand_fn = expand_fn

    def retrieve(self, query: str, domain: str = None,
                 node_type: str = None, limit: int = 20) -> List[dict]:
        expanded = query
        if self._expand_fn:
            try:
                expanded = self._expand_fn(query)
            except Exception:
                logger.warning("HyDE expansion failed, using raw query")
        return self._searcher.search(expanded, domain=domain,
                                     node_type=node_type, limit=limit)
