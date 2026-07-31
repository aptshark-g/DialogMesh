"""BlockMeta — metadata-driven clustering for DiscourseBlockTree.

Adjusts metadata (summary, tags, cluster_id, priority) without touching
the immutable block content. Cost: one extra hop per access. Safe.

Design: ARCHITECTURE_AUDIT §12.4 — metadata-driven, not content re-chunking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BlockMeta:
    """Metadata wrapper for a DiscourseBlock — all fields mutable."""
    block_id: str
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    cluster_id: str = ""
    priority: float = 0.5
    chunkable: bool = True
    confidence: float = 0.5
    last_modified: str = ""

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "summary": self.summary,
            "tags": self.tags,
            "cluster_id": self.cluster_id,
            "priority": self.priority,
            "chunkable": self.chunkable,
            "confidence": self.confidence,
            "last_modified": self.last_modified,
        }


class BlockMetaStore:
    """In-memory metadata store — one BlockMeta per discourse block.

    Adjusting metadata (tags, summary, priority) never touches block content.
    Content stays immutable in DiscourseBlockTree.
    """

    def __init__(self):
        self._meta: Dict[str, BlockMeta] = {}

    def get(self, block_id: str) -> Optional[BlockMeta]:
        return self._meta.get(block_id)

    def set(self, block_id: str, meta: BlockMeta) -> None:
        import time
        meta.last_modified = str(time.time())
        self._meta[block_id] = meta

    def update_tags(self, block_id: str, tags: List[str]) -> None:
        if block_id in self._meta:
            self._meta[block_id].tags = tags

    def update_summary(self, block_id: str, summary: str) -> None:
        if block_id in self._meta:
            self._meta[block_id].summary = summary

    def update_priority(self, block_id: str, priority: float) -> None:
        if block_id in self._meta:
            self._meta[block_id].priority = max(0.0, min(1.0, priority))

    def recluster(self, blocks: List[str], new_cluster_id: str) -> None:
        """Reassign multiple blocks to a new cluster."""
        for block_id in blocks:
            if block_id in self._meta:
                self._meta[block_id].cluster_id = new_cluster_id

    def mark_non_chunkable(self, block_id: str) -> None:
        if block_id in self._meta:
            self._meta[block_id].chunkable = False

    def get_by_cluster(self, cluster_id: str) -> List[BlockMeta]:
        return [m for m in self._meta.values() if m.cluster_id == cluster_id]

    def get_by_tag(self, tag: str) -> List[BlockMeta]:
        return [m for m in self._meta.values() if tag in m.tags]

    def stats(self) -> dict:
        return {
            "total_blocks": len(self._meta),
            "clustered": sum(1 for m in self._meta.values() if m.cluster_id),
            "non_chunkable": sum(1 for m in self._meta.values() if not m.chunkable),
            "avg_priority": (
                sum(m.priority for m in self._meta.values()) / max(1, len(self._meta))
            ),
        }
