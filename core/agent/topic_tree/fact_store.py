"""Topic Tree — Fact Store + Relation Metadata (immutable facts, mutable relations).

Design: docs/v5/TOPIC_TREE_DISCUSSION.md (Q2 resolved)
Pattern: Event Sourcing — facts are append-only, relations are versioned metadata.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time, json, logging

logger = logging.getLogger(__name__)


@dataclass
class FactBlock:
    """Immutable dialogue fact. Content never changes."""
    block_id: str
    content: str
    entities: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    source_chain: str = "discourse"  # which chain produced this fact

    def __hash__(self):
        return hash(self.block_id)


@dataclass
class RelationMetadata:
    """Versioned relationship between facts. This is what changes."""
    block_a: str
    block_b: str
    relation_type: str = "sequential"  # causal/temporal/sibling/contradiction
    version: int = 1
    changed_at: float = field(default_factory=time.time)
    previous_relation: Optional[str] = None
    
    @property
    def is_changed(self) -> bool:
        return self.previous_relation is not None and self.previous_relation != self.relation_type


class FactStore:
    """Append-only immutable fact storage."""
    
    def __init__(self):
        self._facts: Dict[str, FactBlock] = {}
        self._index_by_entity: Dict[str, List[str]] = {}
    
    def put(self, block: FactBlock):
        if block.block_id not in self._facts:
            self._facts[block.block_id] = block
            for entity in block.entities:
                self._index_by_entity.setdefault(entity, []).append(block.block_id)
    
    def get(self, block_id: str) -> Optional[FactBlock]:
        return self._facts.get(block_id)
    
    def by_entity(self, entity: str) -> List[FactBlock]:
        return [self._facts[bid] for bid in self._index_by_entity.get(entity, []) if bid in self._facts]
    
    def __len__(self):
        return len(self._facts)


class RelationMetadataStore:
    """Versioned relationship metadata. Git-like history."""
    
    def __init__(self):
        self._relations: Dict[str, List[RelationMetadata]] = {}
        self._current: Dict[str, RelationMetadata] = {}
    
    def _key(self, a: str, b: str) -> str:
        return f"{a}::{b}" if a < b else f"{b}::{a}"
    
    def update(self, block_a: str, block_b: str, relation_type: str):
        key = self._key(block_a, block_b)
        prev = self._current.get(key)
        version = (prev.version + 1) if prev else 1
        meta = RelationMetadata(
            block_a=block_a, block_b=block_b,
            relation_type=relation_type, version=version,
            previous_relation=prev.relation_type if prev else None
        )
        self._relations.setdefault(key, []).append(meta)
        self._current[key] = meta
        if meta.is_changed:
            logger.debug("Relation changed: %s %s→%s (v%d)", key, prev.relation_type, relation_type, version)
    
    def get(self, block_a: str, block_b: str) -> Optional[RelationMetadata]:
        return self._current.get(self._key(block_a, block_b))
    
    def history(self, block_a: str, block_b: str) -> List[RelationMetadata]:
        return self._relations.get(self._key(block_a, block_b), [])
    
    def rollback(self, block_a: str, block_b: str, version: int) -> bool:
        key = self._key(block_a, block_b)
        history = self._relations.get(key, [])
        for meta in history:
            if meta.version == version:
                self._current[key] = meta
                return True
        return False
