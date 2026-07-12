"""CommunityDetector: Louvain/Leiden community detection on multi-edge weighted graphs."""
from __future__ import annotations
from typing import Dict, List
import networkx as nx
from networkx.algorithms.community import louvain_communities

from core.agent.v4.world.schema import StructuralWorldGraph, Community


class CommunityDetector:
    """Detect module boundaries via community detection on multi-edge graphs.

    Git directory tree is only an initial Prior, not the final cluster.
    True module boundaries come from community detection on the structural graph.

    Uses Louvain algorithm (default) on the multi-edge weighted graph.
    """

    def __init__(self, resolution: float = 1.0, seed: int = 42):
        """Initialize with Louvain resolution parameter.

        Args:
            resolution: Higher values produce more communities (finer granularity).
                        Default 1.0. Tunable via ParameterRegistry.
            seed: Random seed for deterministic community detection.
                  Default 42. Tunable via ParameterRegistry.
        """
        self._resolution = resolution
        self._seed = seed

    def detect(self, graph: StructuralWorldGraph) -> List[Community]:
        """Run community detection and return communities.

        Each community represents a module boundary in the codebase.
        Communities are sorted by size (largest first).
        """
        if graph.node_count == 0:
            return []

        if graph.node_count == 1:
            uid = list(graph.units.keys())[0]
            return [Community(community_id='community_0', unit_ids=[uid], name=uid)]

        G = graph.to_networkx()
        if G.number_of_edges() == 0:
            # Each disconnected node is its own community
            return [
                Community(community_id=f'community_{i}', unit_ids=[uid], name=uid)
                for i, uid in enumerate(sorted(graph.units.keys()))
            ]

        # Louvain community detection on weighted graph
        raw_communities = louvain_communities(
            G, weight="weight", resolution=self._resolution, seed=self._seed
        )

        communities: List[Community] = []
        for i, node_set in enumerate(raw_communities):
            unit_ids = sorted(node_set)
            if unit_ids:
                # Name the community after the most central node
                name = self._choose_community_name(G, unit_ids)
                communities.append(Community(
                    community_id=f"community_{i}",
                    unit_ids=unit_ids,
                    name=name,
                ))

        # Sort by size descending
        communities.sort(key=lambda c: len(c.unit_ids), reverse=True)
        return communities

    def _choose_community_name(self, G: nx.Graph, unit_ids: List[str]) -> str:
        """Pick a name for the community based on the most central node."""
        if not unit_ids:
            return ""
        if len(unit_ids) == 1:
            return unit_ids[0].split("::")[0] if "::" in unit_ids[0] else unit_ids[0]

        # Use degree centrality within the subgraph
        subgraph = G.subgraph(unit_ids)
        if subgraph.number_of_edges() == 0:
            return unit_ids[0].split('::')[0] if '::' in unit_ids[0] else unit_ids[0]
        centrality = nx.degree_centrality(subgraph)
        best = max(centrality, key=centrality.get)
        # Return module-level name (strip function/class qualifier)
        return best.split("::")[0] if "::" in best else best


def assign_communities_to_graph(
    graph: StructuralWorldGraph, communities: List[Community]
) -> None:
    """Write community assignments back into the StructuralWorldGraph."""
    graph.communities.clear()
    for c in communities:
        graph.communities[c.community_id] = list(c.unit_ids)
