"""RelationGraph — entity-relationship graph, pure-Python (no pandas required).

Follows GraphRAG pattern: entities + relationships → graph traversal.
Phase 3 core: stores entities extracted by AssociationChain L1.5.
pandas optional — used only for DataFrame-style access when installed.

Design: ARCHITECTURE_AUDIT §12.3, OPENSOURCE_DEEP_READ §2 (gleaning pattern).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple, Protocol, Any

logger = logging.getLogger("dm.relation_graph")

# Optional pandas — for DataFrame-style access when installed
try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    pd = None
    _HAS_PANDAS = False


# ── Data Model ──

class GraphBackend(Protocol):
    """Pluggable graph storage — swap list-based for Neo4j/Kuzu."""
    def add_entity(self, entity_id: str, etype: str, desc: str,
                   block_id: str, confidence: float) -> None: ...
    def add_relationship(self, source: str, target: str, desc: str,
                         weight: float, block_id: str) -> None: ...
    def traverse(self, entity_id: str, depth: int) -> List[str]: ...
    def filter_orphans(self) -> None: ...
    def stats(self) -> Dict[str, int]: ...


class InMemoryGraphBackend:
    """Default: pure-Python lists + optional networkx. Good for <50K nodes.

    entities: list[dict] — id, type, description, block_id, confidence
    relationships: list[dict] — source, target, description, weight, block_id
    """

    def __init__(self):
        self.entities: List[dict] = []
        self.relationships: List[dict] = []
        self._entity_ids: Set[str] = set()  # fast dedup
        self._graph = None  # networkx cache (optional)

    # ── Write ──

    def add_entity(self, entity_id: str, etype: str, desc: str,
                   block_id: str = "", confidence: float = 0.5) -> None:
        if entity_id in self._entity_ids:
            return  # dedup
        self.entities.append({
            "id": entity_id, "type": etype, "description": desc,
            "block_id": block_id, "confidence": confidence,
        })
        self._entity_ids.add(entity_id)

    def add_relationship(self, source: str, target: str, desc: str,
                         weight: float = 0.5, block_id: str = "") -> None:
        self.relationships.append({
            "source": source, "target": target, "description": desc,
            "weight": weight, "block_id": block_id,
        })
        self._graph = None  # invalidate cache

    # ── Read ──

    def traverse(self, entity_id: str, depth: int = 2) -> List[str]:
        """BFS traversal up to depth hops. Returns connected entity ids."""
        if entity_id not in self._entity_ids:
            return [entity_id]
        if self._graph is not None:
            return self._traverse_graph(entity_id, depth)
        return self._traverse_bfs(entity_id, depth)

    def _traverse_bfs(self, entity_id: str, depth: int) -> List[str]:
        """Pure-Python BFS — no networkx needed."""
        # Build adjacency on the fly (relationships are small)
        adj: Dict[str, Set[str]] = {}
        for r in self.relationships:
            adj.setdefault(r["source"], set()).add(r["target"])
            adj.setdefault(r["target"], set()).add(r["source"])

        visited: Set[str] = {entity_id}
        frontier: List[str] = [entity_id]
        for _ in range(depth):
            next_frontier: List[str] = []
            for node in frontier:
                for neighbor in adj.get(node, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
        return list(visited)

    def _traverse_graph(self, entity_id: str, depth: int) -> List[str]:
        import networkx as nx
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

    def get_entities_by_block(self, block_id: str) -> List[dict]:
        return [e for e in self.entities if e["block_id"] == block_id]

    def filter_orphans(self) -> int:
        """Remove relationships referencing non-existent entities."""
        before = len(self.relationships)
        self.relationships = [
            r for r in self.relationships
            if r["source"] in self._entity_ids and r["target"] in self._entity_ids
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

    def try_build_graph(self) -> bool:
        """Build networkx graph if available (for faster multi-hop traversal)."""
        try:
            import networkx as nx
            self._graph = nx.DiGraph()
            for r in self.relationships:
                self._graph.add_edge(r["source"], r["target"], weight=r["weight"])
            return True
        except ImportError:
            self._graph = None
            return False


# ── Public API ──

class RelationGraph:
    """Entity-relationship graph store. Backend-pluggable (list → Neo4j/Kuzu)."""

    def __init__(self, backend: str = "in_memory"):
        self._backend: GraphBackend = InMemoryGraphBackend()
        self._backend_name: str = backend
        if backend != "in_memory":
            logger.info("RelationGraph: %s backend not implemented, using in_memory", backend)

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

    def get_entities_by_block(self, block_id: str) -> List[dict]:
        """Get all entities from a discourse block."""
        return self._backend.get_entities_by_block(block_id)

    def filter_orphans(self) -> int:
        return self._backend.filter_orphans()

    def stats(self) -> dict:
        return {**self._backend.stats(), "backend": self._backend_name}

    def to_dataframe(self):
        """Optional pandas view — raises if pandas not installed."""
        if not _HAS_PANDAS:
            raise ImportError("pandas required for DataFrame view")
        return (
            pd.DataFrame(self._backend.entities),
            pd.DataFrame(self._backend.relationships),
        )
