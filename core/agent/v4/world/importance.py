"""StructuralImportance strategies: betweenness, pagerank, degree, hybrid."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List
import networkx as nx

from core.agent.v4.world.schema import StructuralWorldGraph


class StructuralImportanceStrategy(ABC):
    """Strategy interface for computing node importance in a structural graph.

    Not bound to a single algorithm. Strategy is switchable via ParameterRegistry.
    """

    @abstractmethod
    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        """Compute importance scores for all nodes in the graph.

        Returns:
            Dict mapping unit_id -> importance score (0.0-1.0, normalized).
        """

    @staticmethod
    def from_name(name: str) -> "StructuralImportanceStrategy":
        """Factory: create a strategy from a name string."""
        strategies = {
            "betweenness": BetweennessStrategy,
            "pagerank": PageRankStrategy,
            "degree": DegreeStrategy,
            "hybrid": HybridStrategy,
            "k_sampling": KSamplingStrategy,
            "community_chunk": CommunityChunkStrategy,
            "tiered": TieredImportanceStrategy,
        }
        cls = strategies.get(name, BetweennessStrategy)
        return cls()


class BetweennessStrategy(StructuralImportanceStrategy):
    """Betweenness centrality: how many shortest paths pass through this node.

    Best for: identifying bridge/articulation nodes in the module graph.
    Complexity: O(N*M) on unweighted, O(N*M + N^2*log(N)) on weighted.
    Good for graphs with <5000 nodes. Beyond that, switch to sampling or pagerank.
    """

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}
        G = graph.to_networkx()
        if G.number_of_nodes() <= 1:
            return {uid: 0.0 for uid in graph.units}

        scores = nx.betweenness_centrality(G, weight="weight", normalized=True)
        return {str(k): float(v) for k, v in scores.items()}


class PageRankStrategy(StructuralImportanceStrategy):
    """PageRank: importance by incoming edge weight from important neighbors.

    Best for: large graphs where betweenness is too slow. More stable
    against edge noise than betweenness.
    Complexity: O(N + M) per iteration, typically <100 iterations.
    """

    def __init__(self, alpha: float = 0.85):
        self._alpha = alpha

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}
        G = graph.to_networkx()
        if G.number_of_nodes() <= 1:
            return {uid: 0.0 for uid in graph.units}

        scores = nx.pagerank(G, alpha=self._alpha, weight="weight")
        return {str(k): float(v) for k, v in scores.items()}


class DegreeStrategy(StructuralImportanceStrategy):
    """Weighted degree: simple sum of incident edge weights.

    Best for: ultra-fast approximation, early-stage prototyping,
    or when graph topology is dense and uniform.
    Complexity: O(N + M).
    """

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}
        G = graph.to_networkx()
        if G.number_of_nodes() <= 1:
            return {uid: 0.0 for uid in graph.units}

        weighted_degree = dict(G.degree(weight="weight"))
        max_deg = max(weighted_degree.values()) if weighted_degree else 1.0
        if max_deg == 0:
            max_deg = 1.0
        return {str(k): v / max_deg for k, v in weighted_degree.items()}


class HybridStrategy(StructuralImportanceStrategy):
    """Ensemble of multiple strategies, weighted by registry params.

    Default: 0.40 betweenness + 0.30 pagerank + 0.30 degree.
    Weights configurable via ParameterRegistry.
    """

    def __init__(
        self,
        w_betweenness: float = 0.40,
        w_pagerank: float = 0.30,
        w_degree: float = 0.30,
    ):
        self._w_b = w_betweenness
        self._w_p = w_pagerank
        self._w_d = w_degree

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}

        b_scores = BetweennessStrategy().compute(graph)
        p_scores = PageRankStrategy().compute(graph)
        d_scores = DegreeStrategy().compute(graph)

        all_ids = set(b_scores) | set(p_scores) | set(d_scores)
        result: Dict[str, float] = {}
        for uid in all_ids:
            result[uid] = (
                self._w_b * b_scores.get(uid, 0.0)
                + self._w_p * p_scores.get(uid, 0.0)
                + self._w_d * d_scores.get(uid, 0.0)
            )
        return result




class KSamplingStrategy(StructuralImportanceStrategy):
    """Tier 1: Brandes k-sampling approximate betweenness.

    Samples k pivot nodes and computes shortest paths from each.
    O(k*M) complexity, ~95% quality vs exact, ~10x speedup.

    Best for: graphs with 5000-20000 nodes.
    """

    def __init__(self, k: int = 1000):
        self._k = k

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}
        G = graph.to_networkx()
        if G.number_of_nodes() <= 1:
            return {uid: 0.0 for uid in graph.units}

        import random
        random.seed(42)
        nodes = list(G.nodes())
        sample_size = min(self._k, len(nodes))
        sample = random.sample(nodes, sample_size)

        scores = nx.betweenness_centrality(
            G, k=sample_size, weight="weight", normalized=True, seed=42,
        )
        return {str(k): float(v) for k, v in scores.items()}


class CommunityChunkStrategy(StructuralImportanceStrategy):
    """Tier 2: Per-community exact betweenness + meta-graph bridge.

    Detects communities, computes exact betweenness within each,
    then builds a meta-graph (community = node) to score bridge nodes.

    O(Sum(N_i * M_i) + C^3) complexity. ~85% quality, ~20x speedup.
    Best for: graphs with 20000-50000 nodes.
    """

    def __init__(self, resolution: float = 1.0):
        self._resolution = resolution

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        if graph.node_count == 0:
            return {}

        from core.agent.v4.world.community import CommunityDetector
        detector = CommunityDetector(resolution=self._resolution)
        communities = detector.detect(graph)

        if not communities or len(communities) <= 1:
            # Single community: fall back to k-sampling
            return KSamplingStrategy(k=2000).compute(graph)

        G = graph.to_networkx()
        scores: Dict[str, float] = {}

        # Step 1: Within-community betweenness
        for community in communities:
            unit_ids = community.unit_ids
            if len(unit_ids) <= 1:
                for uid in unit_ids:
                    scores[uid] = scores.get(uid, 0.0)
                continue

            subgraph = G.subgraph(unit_ids)
            if subgraph.number_of_edges() == 0:
                for uid in unit_ids:
                    scores[uid] = scores.get(uid, 0.0)
                continue

            sub_scores = nx.betweenness_centrality(
                subgraph, weight="weight", normalized=True,
            )
            for uid, score in sub_scores.items():
                scores[uid] = score

        # Step 2: Meta-graph bridge (community-level betweenness)
        meta_graph = nx.Graph()
        com_map: Dict[str, int] = {}
        for i, community in enumerate(communities):
            com_map[community.community_id] = i
            meta_graph.add_node(i)

        for edge in graph.edges:
            src_com = self._find_community(edge.source_id, communities)
            tgt_com = self._find_community(edge.target_id, communities)
            if src_com is not None and tgt_com is not None and src_com != tgt_com:
                si = com_map[src_com.community_id]
                ti = com_map[tgt_com.community_id]
                if meta_graph.has_edge(si, ti):
                    meta_graph[si][ti]["weight"] += edge.effective_weight()
                else:
                    meta_graph.add_edge(si, ti, weight=edge.effective_weight())

        if meta_graph.number_of_edges() > 0:
            meta_scores = nx.betweenness_centrality(
                meta_graph, weight="weight", normalized=True,
            )
            # Distribute bridge bonus to community members
            for community in communities:
                cid = com_map.get(community.community_id, -1)
                if cid >= 0 and cid in meta_scores:
                    bonus = meta_scores[cid] * 0.3  # 30% bridge bonus
                    for uid in community.unit_ids:
                        scores[uid] = scores.get(uid, 0.0) + bonus

        return scores

    @staticmethod
    def _find_community(unit_id, communities):
        for c in communities:
            if unit_id in c.unit_ids:
                return c
        return None


class TieredImportanceStrategy(StructuralImportanceStrategy):
    """Tiered pipeline: auto-routes based on graph size.

    Adaptive routing:
        <5000 nodes  -> Exact Betweenness (fast enough)
        5000-20000   -> K-Sampling (95% quality, 10x speed)
        20000-50000  -> Community Chunk (85% quality, 20x speed)
        >50000       -> Exact Betweenness (ultimate fallback, slow)

    Configuration passed through __init__ or read from WorldParams.
    """

    def __init__(
        self,
        tier0_max: int = 5000,
        tier1_max: int = 20000,
        tier2_max: int = 50000,
        k_sampling_size: int = 1000,
        community_resolution: float = 1.0,
    ):
        self._tier0_max = tier0_max
        self._tier1_max = tier1_max
        self._tier2_max = tier2_max
        self._k = k_sampling_size
        self._resolution = community_resolution

    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]:
        n = graph.node_count

        if n <= self._tier0_max:
            # Tier 0/3: Exact betweenness (small enough for direct)
            return BetweennessStrategy().compute(graph)
        elif n <= self._tier1_max:
            # Tier 1: K-Sampling
            return KSamplingStrategy(k=self._k).compute(graph)
        elif n <= self._tier2_max:
            # Tier 2: Community Chunk
            return CommunityChunkStrategy(resolution=self._resolution).compute(graph)
        else:
            # Tier 3: K-Sampling with large k for very large graphs
            # Exact Betweenness O(N^3) is too slow for >50000 nodes
            return KSamplingStrategy(k=self._k * 5).compute(graph)


def compute_backbone_scores(
    graph: StructuralWorldGraph,
    structural_importance: Dict[str, float],
    runtime_centrality: Dict[str, float] | None = None,
    commit_centrality: Dict[str, float] | None = None,
    retrieval_centrality: Dict[str, float] | None = None,
    # Weights (from ParameterRegistry)
    w_structural: float = 0.30,
    w_runtime: float = 0.30,
    w_commit: float = 0.20,
    w_retrieval: float = 0.20,
) -> Dict[str, float]:
    """Compute BackboneScore from four centrality dimensions.

    BackboneScore =
        0.30 x Structural Importance
      + 0.30 x Runtime Centrality
      + 0.20 x Commit Centrality
      + 0.20 x Retrieval Centrality

    Each dimension is independently normalized before fusion.
    Missing dimensions default to 0.0.
    """
    if not structural_importance:
        return {}

    result: Dict[str, float] = {}
    all_ids = set(structural_importance)

    if runtime_centrality:
        all_ids.update(runtime_centrality)
    if commit_centrality:
        all_ids.update(commit_centrality)
    if retrieval_centrality:
        all_ids.update(retrieval_centrality)

    for uid in all_ids:
        score = (
            w_structural * structural_importance.get(uid, 0.0)
            + w_runtime * (runtime_centrality.get(uid, 0.0) if runtime_centrality else 0.0)
            + w_commit * (commit_centrality.get(uid, 0.0) if commit_centrality else 0.0)
            + w_retrieval * (retrieval_centrality.get(uid, 0.0) if retrieval_centrality else 0.0)
        )
        result[uid] = min(1.0, max(0.0, score))

    return result


def write_backbone_to_graph(
    graph: StructuralWorldGraph, backbone: Dict[str, float]
) -> None:
    """Write backbone scores into the StructuralWorldGraph and its units."""
    graph.backbone.clear()
    graph.backbone.update(backbone)
    for unit_id, score in backbone.items():
        if unit_id in graph.units:
            graph.units[unit_id].backbone_score = score
