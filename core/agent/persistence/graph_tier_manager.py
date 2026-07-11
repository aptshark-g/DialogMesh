"""GraphTierManager: automatic GC-like tier migration for UnifiedGraphStore.

Implements Hot/Warm/Cold/Archive tiering based on activation_count + importance.
Inspired by JVM GC: promotion on access, demotion on staleness, data stripping.
"""
from __future__ import annotations
import logging, threading, time
from typing import Dict, List, Optional
from .unified_graph_store import UnifiedGraphStore

logger = logging.getLogger(__name__)

HOT_MAX_NODES = 999
WARM_TO_COLD_IMPORTANCE = 0.3
WARM_TO_COLD_ACTIVATION = 5
HOT_TO_WARM_INACTIVE_ROUNDS = 10


class GraphTierManager:

    def __init__(self, store: UnifiedGraphStore):
        self._store = store
        self._lock = threading.Lock()
        self._last_gc_time = 0.0
        self._gc_interval_sec = 3600

    def on_access(self, node_id: str):
        """Called on every node access (touch). Auto-promote if deserved."""
        self._store.touch(node_id)
        node = self._store.load_node(node_id)
        if node is None: return
        tier = node.get("tier", "H")
        activation = node.get("activation_count", 0)

        if tier in ("C", "A") and activation >= 3:
            self._store.update_tier(node_id, "W")
            logger.info(f"Promoted {node_id}: {tier} -> W (activation={activation})")
        elif tier == "W" and activation >= 10:
            self._store.update_tier(node_id, "H")
            logger.info(f"Promoted {node_id}: W -> H (activation={activation})")

    def gc_if_needed(self):
        """Run GC cycle if interval has elapsed."""
        now = time.time()
        if now - self._last_gc_time < self._gc_interval_sec:
            return
        self.run_gc()

    def run_gc(self):
        self._last_gc_time = time.time()
        with self._lock:
            counts = self._store.get_tier_counts()
            if counts.get('H', 0) > HOT_MAX_NODES:
                excess = counts.get('H', 0) - HOT_MAX_NODES
                self._store.demote_stale_nodes('H', 'W', max_activation=HOT_TO_WARM_INACTIVE_ROUNDS, limit=excess)
        with self._lock:
            counts = self._store.get_tier_counts()
            if counts.get('W', 0) > 100:
                self._store.demote_stale_nodes('W', 'C', max_activation=WARM_TO_COLD_ACTIVATION, limit=counts.get('W',0)//2)
            self._strip_cold_data()
        with self._lock:
            counts = self._store.get_tier_counts()
            if counts.get('C', 0) > 50:
                self._store.demote_stale_nodes('C', 'A', max_activation=0, limit=counts.get('C',0)//4)


    def _strip_cold_data(self):
        """For Cold-tier nodes, strip full data but keep summary + l2_summary + metadata."""
        with self._store._lock:
            self._store._conn.execute(
                "UPDATE unified_nodes SET data='{}' "
                "WHERE tier='C' AND data != '{}'")
            self._store._conn.commit()


    def promote_node(self, node_id: str) -> str:
        node = self._store.load_node(node_id)
        if node is None:
            return "?"
        current = node.get("tier", "W")
        tiers = {"A": "C", "C": "W", "W": "H", "H": "H"}
        target = tiers.get(current, current)
        if target != current:
            self._store.update_tier(node_id, target)
        return target

    def demote_node(self, node_id: str) -> str:
        node = self._store.load_node(node_id)
        if node is None:
            return "?"
        current = node.get("tier", "W")
        tiers = {"H": "W", "W": "C", "C": "A", "A": "A"}
        target = tiers.get(current, current)
        if target != current:
            self._store.update_tier(node_id, target)
        return target

    def get_stats(self) -> dict:
        return {
            "tiers": self._store.get_tier_counts(),
            "last_gc": self._last_gc_time,
            "gc_interval_sec": self._gc_interval_sec,
        }
