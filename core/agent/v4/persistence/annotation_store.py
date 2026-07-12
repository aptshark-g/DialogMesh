"""NodeAnnotationStore: multi-domain annotation index with versioning.
Supports soft (stale-mark) invalidation and history tracking.
"""
from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NodeAnnotation:
    node_id: str
    domain: str
    data: dict = field(default_factory=dict)
    version: int = 1
    stale: bool = False
    previous_versions: list = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


class NodeAnnotationStore:
    """Multi-domain annotation index. Thread-safe.

    Each (node_id, domain) pair holds one active annotation plus history.
    Stale annotations are re-classified on next get().
    """

    def __init__(self):
        self._store: Dict[str, NodeAnnotation] = {}
        self._lock = threading.Lock()

    # ?? core ??????????????????????????????????????????????????

    def put(self, node_id: str, domain: str, data: dict,
            version: int = 1) -> NodeAnnotation:
        key = self._key(node_id, domain)
        with self._lock:
            existing = self._store.get(key)
            if existing is not None:
                existing.previous_versions.append({
                    "data": dict(existing.data),
                    "version": existing.version,
                    "updated_at": existing.updated_at,
                })
                version = max(version, existing.version + 1)
            ann = NodeAnnotation(
                node_id=node_id, domain=domain, data=data,
                version=version, stale=False,
                previous_versions=existing.previous_versions if existing else [],
            )
            self._store[key] = ann
            return ann

    def get(self, node_id: str, domain: str) -> Optional[NodeAnnotation]:
        key = self._key(node_id, domain)
        with self._lock:
            return self._store.get(key)

    def mark_stale(self, node_id: str, domain: str) -> None:
        key = self._key(node_id, domain)
        with self._lock:
            if key in self._store:
                self._store[key].stale = True

    def mark_stale_by_domain(self, domain: str) -> int:
        count = 0
        with self._lock:
            for key, ann in self._store.items():
                if ann.domain == domain:
                    ann.stale = True
                    count += 1
        return count

    def get_stale(self, domain: str, limit: int = 100) -> list[NodeAnnotation]:
        results: list[NodeAnnotation] = []
        with self._lock:
            for key, ann in self._store.items():
                if ann.domain == domain and ann.stale:
                    results.append(ann)
                    if len(results) >= limit:
                        break
        return results

    def history(self, node_id: str, domain: str) -> list[dict]:
        ann = self.get(node_id, domain)
        if ann is None:
            return []
        return ann.previous_versions

    def remove(self, node_id: str, domain: str) -> bool:
        key = self._key(node_id, domain)
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def stats(self) -> dict:
        with self._lock:
            domains: Dict[str, int] = {}
            stale_counts: Dict[str, int] = {}
            for ann in self._store.values():
                domains[ann.domain] = domains.get(ann.domain, 0) + 1
                if ann.stale:
                    stale_counts[ann.domain] = stale_counts.get(ann.domain, 0) + 1
            return {
                "total_annotations": len(self._store),
                "by_domain": domains,
                "stale_by_domain": stale_counts,
            }

    @staticmethod
    def _key(node_id: str, domain: str) -> str:
        return f"{domain}:{node_id}"
