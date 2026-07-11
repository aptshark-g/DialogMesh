class DeltaAdjuster:
    INITIAL = 0.05
    MAX = 0.15
    MIN = 0.0

    def __init__(self):
        self.current = self.INITIAL

    def adjust(self, edge, cycle):
        if cycle % 50 != 0:
            return self.current
        if edge.structural_prior > 0.3 and edge.correction_count < 2:
            self.current = min(self.MAX, self.current + 0.02)
        elif edge.correction_count > 5:
            self.current = max(self.MIN, self.current - 0.02)
        return self.current

    def apply_to_edge(self, edge, delta):
        """Update edge.structural_prior with bounded delta."""
        new_prior = edge.structural_prior + delta
        edge.structural_prior = max(0.0, min(1.0, new_prior))
        return edge.structural_prior

    def apply_to_graph(self, graph, edge_key, delta):
        """Find edge by key in graph, call apply_to_edge."""
        if hasattr(graph, "edges"):
            edge = graph.edges.get(edge_key)
            if edge:
                return self.apply_to_edge(edge, delta)
        return None
