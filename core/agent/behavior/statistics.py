"""Graph statistics collection"""
from .models import GraphStatistics


class GraphStatisticsCollector:
    """Compute and update graph statistics after each operation."""

    def __init__(self, graph):
        self.graph = graph

    def compute(self) -> GraphStatistics:
        """Compute all statistics from current graph state."""
        stats = GraphStatistics()
        stats.node_count = len(self.graph.nodes)
        stats.edge_count = len(self.graph.edges)
        stats.seed_count = len(getattr(self.graph.cold_start, "seeds", []))
        stats.total_samples = sum(
            e.sample_count for e in self.graph.edges.values()
        )

        # Edge-based averages
        edges = list(self.graph.edges.values())
        if edges:
            stats.avg_weight = sum(e.weight for e in edges) / len(edges)
            stats.avg_importance = sum(e.importance for e in edges) / len(edges)
            stats.avg_activation = sum(e.activation_count for e in edges) / len(edges)
            stats.unstable_edge_count = sum(
                1 for e in edges if e.instability_ratio > 0.3
            )
        else:
            stats.avg_weight = 0.0
            stats.avg_importance = 0.0
            stats.avg_activation = 0.0
            stats.unstable_edge_count = 0

        # Deprecated seed count
        csm = getattr(self.graph, "cold_start", None)
        if csm and hasattr(csm, "seeds"):
            stats.deprecated_seed_count = sum(
                1 for s in csm.seeds if s.is_deprecated
            )
        else:
            stats.deprecated_seed_count = 0

        # Preserve existing timestamps
        existing = getattr(self.graph, "stats", None)
        if existing:
            stats.last_prune_time = existing.last_prune_time
            stats.last_discovery_time = existing.last_discovery_time

        return stats

    def update(self):
        """Compute and write statistics back to graph."""
        self.graph.stats = self.compute()
