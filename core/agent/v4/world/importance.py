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
