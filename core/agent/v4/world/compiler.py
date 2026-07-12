"""StructuralContextCompiler: subgraph compilation from World Model.

Phase 4 stub. The full ContextCompiler (cross-domain fusion, budget allocation,
intent-aware traversal) is a separate module (DESIGN_V4_CONTEXT_ENGINEERING.md).
This stub provides the interface contract and a simple keyword-based fallback.
"""
from __future__ import annotations
from typing import List

from core.agent.v4.world.schema import (
    StructuralWorldGraph, SubgraphResult, ReferenceUnit, StructuralEdge,
)


class StructuralContextCompiler:
    """Compile a local subgraph from the World Model for a given intent.

    Stub implementation: keyword-based node matching + neighbor expansion.
    Full implementation will replace this with embedding-based or LLM-based
    intent-to-subgraph mapping.
    """

    def __init__(
        self,
        fallback_seed_count: int = 5,
        keyword_seed_count: int = 10,
        token_base: int = 500,
        token_per_node: int = 5,
        backbone_top_n: int = 10,
    ):
        self._fallback_seed_count = fallback_seed_count
        self._keyword_seed_count = keyword_seed_count
        self._token_base = token_base
        self._token_per_node = token_per_node
        self._backbone_top_n = backbone_top_n

    def compile_subgraph(
        self,
        graph: StructuralWorldGraph,
        intent: str = "",
        max_nodes: int = 300,
    ) -> SubgraphResult:
        """Cut a local subgraph for the given intent.

        Args:
            graph: The full StructuralWorldGraph.
            intent: User/agent intent string for relevance matching.
            max_nodes: Maximum nodes in the returned subgraph.

        Returns:
            SubgraphResult with nodes, edges, backbone units, and token estimate.
        """
        if graph.node_count == 0:
            return SubgraphResult()

        # Step 1: Find intent-relevant seed nodes
        seeds = self._find_seeds(graph, intent)

        # Step 2: Expand from seeds via BFS until max_nodes
        subgraph_nodes = self._expand_from_seeds(graph, seeds, max_nodes)

        # Step 3: Collect edges among subgraph nodes
        subgraph_node_ids = {u.unit_id for u in subgraph_nodes}
        subgraph_edges = [
            e for e in graph.edges
            if e.source_id in subgraph_node_ids and e.target_id in subgraph_node_ids
        ]

        # Step 4: Identify backbone units in subgraph
        backbone_units = sorted(
            subgraph_node_ids,
            key=lambda uid: graph.backbone.get(uid, 0.0),
            reverse=True,
        )[:self._backbone_top_n]

        # Step 5: Estimate tokens (rough: 500 for nodes+edges, 300 detail)
        token_estimate = min(2000, self._token_base + len(subgraph_nodes) * self._token_per_node)

        return SubgraphResult(
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            backbone_units=backbone_units,
            total_tokens_estimate=token_estimate,
        )

    # ---- private: stub implementation ----

    def _find_seeds(
        self, graph: StructuralWorldGraph, intent: str
    ) -> List[str]:
        """Find seed nodes matching the intent (simple keyword match)."""
        if not intent:
            # No intent: use top backbone nodes as seeds
            sorted_backbone = sorted(
                graph.backbone.items(), key=lambda x: x[1], reverse=True
            )
            seeds = [uid for uid, _ in sorted_backbone[:self._fallback_seed_count]]
            if not seeds:
                # Fallback: any file unit
                seeds = [
                    uid for uid, u in graph.units.items()
                    if u.unit_type == "file"
                ][:5]
            return seeds

        keywords = intent.lower().split()
        scored: list[tuple[str, float]] = []

        for uid, unit in graph.units.items():
            name_lower = unit.name.lower()
            # Simple scoring: count keyword matches in name
            match_count = sum(1 for kw in keywords if kw in name_lower)
            if match_count > 0 or any(kw in uid.lower() for kw in keywords):
                backbone_bonus = graph.backbone.get(uid, 0.0)
                scored.append((uid, match_count + backbone_bonus))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in scored[:self._keyword_seed_count]]

    def _expand_from_seeds(
        self, graph: StructuralWorldGraph, seeds: List[str], max_nodes: int
    ) -> List[ReferenceUnit]:
        """BFS expand from seed nodes until max_nodes reached."""
        if not seeds:
            # No seeds: return backbone units
            sorted_ids = sorted(
                graph.units.keys(),
                key=lambda uid: graph.backbone.get(uid, 0.0),
                reverse=True,
            )
            return [graph.units[uid] for uid in sorted_ids[:max_nodes]]

        visited: set[str] = set()
        queue: list[str] = list(seeds)
        result: list[ReferenceUnit] = []

        while queue and len(result) < max_nodes:
            uid = queue.pop(0)
            if uid in visited or uid not in graph.units:
                continue
            visited.add(uid)
            result.append(graph.units[uid])

            if len(result) >= max_nodes:
                break

            # Add neighbors to queue, prioritized by backbone score
            neighbors = graph.get_neighbors(uid)
            neighbors.sort(
                key=lambda nid: graph.backbone.get(nid, 0.0), reverse=True
            )
            for nid in neighbors:
                if nid not in visited:
                    queue.append(nid)

        return result
