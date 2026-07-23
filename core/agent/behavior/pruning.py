# """Graph pruning - manage node lifecycle"""
import time

class GraphPruner:
    MAX_NODES = 10000
    INACTIVE_DAYS = 30

    def __init__(self, graph):
        self.graph = graph
        self.orphaned_step_ids = []

    def should_prune(self):
        return len(self.graph.nodes) >= self.MAX_NODES

    def prune(self):
        if not self.should_prune():
            return (0, [])
        now = time.time()
        cutoff = now - (self.INACTIVE_DAYS * 86400)
        leaves = [sid for sid,s in list(self.graph.nodes.items())
                  if s.timestamp < cutoff and not any(
                      e.from_step_id == sid for e in self.graph.edges.values())]
        for sid in leaves:
            keys = [k for k,e in self.graph.edges.items() if e.from_step_id==sid or e.to_step_id==sid]
            for k in keys: del self.graph.edges[k]
            del self.graph.nodes[sid]
        self.orphaned_step_ids = list(leaves)
        # Update last_prune_time in graph statistics
        if hasattr(self.graph, "stats") and hasattr(self.graph.stats, "last_prune_time"):
            self.graph.stats.last_prune_time = time.time()
        return (len(leaves), leaves)
