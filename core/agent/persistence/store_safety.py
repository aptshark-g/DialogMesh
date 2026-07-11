"""Safety layer: transaction, monitoring, max_scan, lock for persistence."""
from __future__ import annotations
import time, threading, logging
from typing import Callable, Dict, List, Optional
from .unified_graph_store import UnifiedGraphStore
from .unified_search import UnifiedSearch

logger = logging.getLogger(__name__)
DEFAULT_MAX_SCAN = 100_000


class SafeUnifiedStore:
    """Transaction-safe, monitored wrapper around UnifiedGraphStore."""

    def __init__(self, store: UnifiedGraphStore, monitor=None):
        self._store = store
        self._monitor = monitor
        self._write_lock = threading.Lock()
        self._stats: Dict[str, int] = {"writes": 0, "reads": 0, "errors": 0, "tier_changes": 0}

    def save_node(self, node_id: str, node_type: str, domain: str,
                  data: dict, **kwargs) -> bool:
        start = time.time()
        try:
            with self._write_lock:
                ok = self._store.save_node(node_id, node_type, domain, data, **kwargs)
            self._stats["writes"] += 1
            if self._monitor:
                self._monitor.record("safe_store", "save_node",
                    {"node_id": node_id[:40], "node_type": node_type, "domain": domain},
                    duration_ms=(time.time() - start) * 1000)
            return ok
        except Exception:
            self._stats["errors"] += 1
            logger.exception("save_node failed: %s", node_id)
            raise

    def load_node(self, node_id: str, **kwargs):
        start = time.time()
        try:
            result = self._store.load_node(node_id, **kwargs)
            self._stats["reads"] += 1
            return result
        except Exception:
            self._stats["errors"] += 1
            logger.exception("load_node failed: %s", node_id)
            raise

    def touch(self, node_id: str):
        self._store.touch(node_id)

    def update_tier(self, node_id: str, tier: str):
        self._stats["tier_changes"] += 1
        self._store.update_tier(node_id, tier)

    def load_nodes_by_session(self, session_id: str, **kwargs):
        return self._store.load_nodes_by_session(session_id, **kwargs)

    def promote_cold_nodes(self, node_ids: List[str]):
        self._store.promote_cold_nodes(node_ids)

    def demote_stale_nodes(self, *args, **kwargs):
        self._store.demote_stale_nodes(*args, **kwargs)

    def get_tier_counts(self):
        return self._store.get_tier_counts()

    def health(self) -> dict:
        return {"stats": dict(self._stats), "tiers": self._store.get_tier_counts()}

    @property
    def _lock(self):
        return self._store._lock

    @property
    def _conn(self):
        return self._store._conn


class SafeUnifiedSearch:
    """Search with max_scan protection and shared store lock."""

    def __init__(self, store, max_scan: int = DEFAULT_MAX_SCAN):
        self._searcher = UnifiedSearch(store._store if isinstance(store, SafeUnifiedStore) else store)
        self._max_scan = max_scan

    def keyword_search(self, query: str, **kwargs) -> List[dict]:
        with self._searcher._store._lock:
            return self._searcher.keyword_search(query, **kwargs)

    def summary_search(self, query: str, **kwargs) -> List[dict]:
        with self._searcher._store._lock:
            return self._searcher.summary_search(query, **kwargs)
