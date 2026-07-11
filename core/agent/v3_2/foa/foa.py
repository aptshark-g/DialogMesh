from .models import FocusResult, AttentionNode
from .actr_activator import ACTRActivator


class FoA:
    def __init__(self, activator=None):
        self.activator = activator or ACTRActivator()

    def focus(self, intent, expectation, node_degrees, edges):
        seeds = self._select_seeds(intent, expectation, node_degrees)
        if not seeds:
            return FocusResult([], [], [], self.activator.decay, fallback_used=True)
        activated = self.activator.propagate(seeds, node_degrees, edges)
        if not activated:
            return FocusResult(seeds, [], [], self.activator.decay, fallback_used=True)
        sub_edges = self.activator.get_subgraph_edges(activated, edges)
        return FocusResult(seeds, activated, sub_edges, self.activator.decay)

    def _select_seeds(self, intent, expectation, degrees):
        seeds = []
        if expectation and expectation in degrees:
            seeds.append(expectation)
        if intent and intent in degrees:
            seeds.append(intent)
        if not seeds:
            sorted_nodes = sorted(degrees.items(), key=lambda x: -x[1])
            seeds = [n for n, _ in sorted_nodes[:2]]
        return seeds[:2]
