"""RelationGraph — entity-relationship graph (pandas + networkx).

Follows GraphRAG pattern: entities_df + relationships_df → networkx graph.
Phase 3 core: stores entities extracted by AssociationChain L1.5.

Design: ARCHITECTURE_AUDIT §12.3, OPENSOURCE_DEEP_READ §2 (gleaning pattern).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple, Protocol

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger("dm.relation_graph")


# ── Data Model ──

class GraphBackend(Protocol):
    """Pluggable graph storage — swap pandas/nx for Neo4j/Kuzu."""
    def add_entity(self, entity_id: str, etype: str, desc: str,
                   block_id: str, confidence: float) -> None: ...
    def add_relationship(self, source: str, target: str, desc: str,
                         weight: float, block_id: str) -> None: ...
    def traverse(self, entity_id: str, depth: int) -> List[str]: ...
    def filter_orphans(self) -> None: ...
    def stats(self) -> Dict[str, int]: ...


class InMemoryGraphBackend:
    """Default: pandas + networkx. Good for <50K nodes."""

    def __init__(self):
        if pd is None:
            raise ImportError("pandas required for RelationGraph. Install: pip install pandas")
        self.entities = pd.DataFrame(columns=[
            "id", "type", "description", "block_id", "confidence"
        ])
        self.relationships = pd.DataFrame(columns=[
            "source", "target", "description", "weight", "block_id"
        ])
        self._graph = None  # networkx cache

    def add_entity(self, entity_id: str, etype: str, desc: str,
                   block_id: str = "", confidence: float = 0.5) -> None:
        if entity_id in self.entities["id"].values:
            return  # dedup
        self.entities = pd.concat([self.entities, pd.DataFrame([{
            "id": entity_id, "type": etype, "description": desc,
            "block_id": block_id, "confidence": confidence
        }])], ignore_index=True)

    def add_relationship(self, source: str, target: str, desc: str,
                         weight: float = 0.5, block_id: str = "") -> None:
        self.relationships = pd.concat([self.relationships, pd.DataFrame([{
            "source": source, "target": target, "description": desc,
            "weight": weight, "block_id": block_id
        }])], ignore_index=True)
        self._graph = None  # invalidate cache

    def traverse(self, entity_id: str, depth: int = 2) -> List[str]:
        """BFS traversal up to depth hops. Returns connected entity ids."""
        if self._graph is None:
            self._build_graph()
        if not self._graph or entity_id not in self._graph:
            return [entity_id]

        visited: Set[str] = {entity_id}
        frontier: List[str] = [entity_id]
        for _ in range(depth):
            next_frontier: List[str] = []
            for node in frontier:
                for neighbor in self._graph.neighbors(node):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
        return list(visited)

    def filter_orphans(self) -> int:
        """Remove relationships referencing non-existent entities. Returns removed count."""
        eids = set(self.entities["id"])
        before = len(self.relationships)
        self.relationships = self.relationships[
            self.relationships["source"].isin(eids) &
            self.relationships["target"].isin(eids)
        ]
        removed = before - len(self.relationships)
        if removed:
            logger.info("Removed %d orphan relationships", removed)
        return removed

    def stats(self) -> Dict[str, int]:
        return {
            "entities": len(self.entities),
            "relationships": len(self.relationships),
            "orphans_removed": 0,
        }

    def _build_graph(self) -> None:
        try:
            import networkx as nx
            self._graph = nx.from_pandas_edgelist(
                self.relationships, "source", "target", "weight",
                create_using=nx.DiGraph()
            )
        except ImportError:
            logger.warning("networkx not installed — graph traversal disabled")
            self._graph = None


# ── Public API ──

class RelationGraph:
    """Entity-relationship graph store. Backend-pluggable (pandas/nx → Neo4j/Kuzu)."""

    def __init__(self, backend: str = "in_memory"):
        self._backend: GraphBackend = InMemoryGraphBackend()
        self._backend_name: str = backend

    # ── Write ──

    def add_entity(self, entity_id: str, etype: str, desc: str,
                   block_id: str = "", confidence: float = 0.5) -> None:
        self._backend.add_entity(entity_id, etype, desc, block_id, confidence)

    def add_relationship(self, source: str, target: str, desc: str,
                         weight: float = 0.5, block_id: str = "") -> None:
        self._backend.add_relationship(source, target, desc, weight, block_id)

    def extract_from_text(self, text: str, block_id: str,
                          entities: List[Dict] = None) -> int:
        """Batch add entities and relationships extracted from a discourse block."""
        if not entities:
            return 0
        added = 0
        for ent in entities:
            self.add_entity(
                entity_id=ent.get("id", ent.get("name", "")),
                etype=ent.get("type", "unknown"),
                desc=ent.get("description", ""),
                block_id=block_id,
                confidence=ent.get("confidence", 0.5),
            )
            added += 1
        # Extract relationships from same block's entities
        for i, a in enumerate(entities):
            for b in entities[i + 1:]:
                aid = a.get("id", a.get("name", ""))
                bid = b.get("id", b.get("name", ""))
                if aid and bid:
                    self.add_relationship(aid, bid, "co-occurrence", 0.3, block_id)
                    added += 1
        return added

    # ── Read ──

    def traverse(self, entity_id: str, depth: int = 2) -> List[str]:
        """Traverse graph from entity up to depth hops."""
        return self._backend.traverse(entity_id, depth)

    def get_entities_by_block(self, block_id: str) -> pd.DataFrame:
        """Get all entities from a discourse block."""
        return self._backend.entities[
            self._backend.entities["block_id"] == block_id
        ]

    def filter_orphans(self) -> int:
        return self._backend.filter_orphans()

    def stats(self) -> dict:
        return {**self._backend.stats(), "backend": self._backend_name}
