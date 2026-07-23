"""Observation Pool: in-memory store for ObservationBundles with subscription support."""
from __future__ import annotations
import time
import threading
from typing import Callable, Dict, List, Optional

from .models import ObservationBundle, ObservationEvent


class ObservationPool:
    """Thread-safe in-memory pool for ObservationBundles.

    Active bundles stay in memory. Consumed bundles can be archived to SQLite.
    """

    def __init__(self, max_age_sec: float = 86400.0):
        self._bundles: Dict[str, ObservationBundle] = {}
        self._by_event: Dict[str, List[str]] = {}
        self._by_domain: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[ObservationEvent], None]] = []
        self._max_age_sec = max_age_sec
        self._consumed: set[str] = set()

    # ── write ────────────────────────────────────────────────

    def put(self, bundle: ObservationBundle) -> None:
        with self._lock:
            self._bundles[bundle.bundle_id] = bundle
            self._by_event.setdefault(bundle.event_id, []).append(bundle.bundle_id)
            for domain in bundle.domain_observations:
                self._by_domain.setdefault(domain, []).append(bundle.bundle_id)

    # ── read ─────────────────────────────────────────────────

    def get(self, bundle_id: str) -> Optional[ObservationBundle]:
        with self._lock:
            return self._bundles.get(bundle_id)

    def get_by_event(self, event_id: str) -> List[ObservationBundle]:
        with self._lock:
            ids = self._by_event.get(event_id, [])
            return [self._bundles[bid] for bid in ids if bid in self._bundles]

    def get_by_domain(self, domain: str, since: float = 0.0) -> List[ObservationBundle]:
        with self._lock:
            ids = self._by_domain.get(domain, [])
            return [
                self._bundles[bid] for bid in ids
                if bid in self._bundles and self._bundles[bid].created_at >= since
            ]

    # ── lifecycle ────────────────────────────────────────────

    def mark_consumed(self, bundle_id: str) -> None:
        with self._lock:
            self._consumed.add(bundle_id)

    def evict_old(self, max_age_sec: float = 0.0) -> int:
        threshold = max_age_sec or self._max_age_sec
        now = time.time()
        removed = 0
        with self._lock:
            to_remove = [
                bid for bid, b in self._bundles.items()
                if now - b.created_at > threshold and bid in self._consumed
            ]
            for bid in to_remove:
                b = self._bundles.pop(bid)
                self._by_event[b.event_id].remove(bid)
                for domain in b.domain_observations:
                    if bid in self._by_domain.get(domain, []):
                        self._by_domain[domain].remove(bid)
                removed += 1
        return removed

    # ── subscriptions ────────────────────────────────────────

    def subscribe(self, callback: Callable[[ObservationEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event: ObservationEvent) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                pass

    # ── stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_bundles": len(self._bundles),
                "consumed": len(self._consumed),
                "by_domain": {d: len(ids) for d, ids in self._by_domain.items()},
            }
