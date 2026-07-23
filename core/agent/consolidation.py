"""ConsolidationCycle - adaptive batch event consolidation for BehaviorGraph.
Batches edge changes by volume (not turn count), consolidates when threshold reached.
Works with ColdIndexer for Layer 3 pruning and re-warming."""

import time
from .cold_indexer import ColdIndexer


class ConsolidationCycle:
    EDGE_CHANGE_THRESHOLD = 15
    EDGE_CHANGE_RANGE = (8, 30)
    PRUNE_ACTIVATION = 3
    PRUNE_ACTIVATION_RANGE = (2, 6)
    PRUNE_SAMPLES = 10
    PRUNE_SAMPLES_RANGE = (5, 20)

    def __init__(self, graph, cold_indexer=None):
        self.graph = graph
        self.cold = cold_indexer or ColdIndexer()
        self.pending: dict[str, dict] = {}
        self.cycle_count = 0

    def record_event(self, edge_key, event_type, delta=0.0):
        if edge_key not in self.pending:
            self.pending[edge_key] = {'weight_delta': 0.0, 'corrections': 0, 'successes': 0}
        if event_type == 'SUCCESS':
            self.pending[edge_key]['successes'] += 1
        elif event_type == 'CORRECTION':
            self.pending[edge_key]['corrections'] += 1
        self.pending[edge_key]['weight_delta'] += delta
        if len(self.pending) >= self.EDGE_CHANGE_THRESHOLD:
            return self.consolidate()
        return None

    def consolidate(self):
        self.cycle_count += 1
        count = 0
        pruned = 0
        for ek, changes in list(self.pending.items()):
            if ek in self.graph.edges:
                e = self.graph.edges[ek]
                old_w = e.weight
                e.weight = max(0.0, min(1.0, e.weight + changes['weight_delta']))
                e.correction_count += changes['corrections']
                e.sample_count += changes['successes'] + changes['corrections']
                if hasattr(e, 'importance'):
                    if changes['successes'] > 0:
                        e.importance = min(1.0, e.importance + 0.02 * changes['successes'])
                    if changes['corrections'] > 0:
                        e.importance = max(0.0, e.importance - 0.05 * changes['corrections'])
                count += 1
        self.pending.clear()
        pruned = self._prune_low_activation()
        return {'consolidated': count, 'pruned': pruned, 'cycle': self.cycle_count}

    def _prune_low_activation(self, threshold=None):
        act_t = threshold or self.PRUNE_ACTIVATION
        pruned = 0
        for ek in list(self.graph.edges.keys()):
            e = self.graph.edges[ek]
            if e.sample_count >= self.PRUNE_SAMPLES and e.activation_count < act_t:
                self.cold.store(e)
                del self.graph.edges[ek]
                pruned += 1
        return pruned

    def search_with_cold(self, query_tokens, top_k=5, flat_data_provider=None):
        from .behavior_graph.models import BehaviorEdge
        hits = []
        for ek, e in list(self.graph.edges.items()):
            fs = getattr(e, 'action_summary', '')
            ts = getattr(e, 'to_summary', '')
            etext = (fs + ' ' + ts).lower()
            overlap = len(query_tokens & set(etext.split()))
            if overlap > 0:
                hits.append((ek, overlap))
        hits.sort(key=lambda x: -x[1])
        result = [h for h, _ in hits[:top_k]]
        if len(result) < top_k and flat_data_provider:
            cold_hits = self.cold.search(query_tokens, top_k=top_k - len(result))
            for rec in cold_hits:
                cb = lambda eid=rec.edge_id: flat_data_provider(eid)
                edge = self.cold.recall(rec, cb)
                if edge:
                    self.graph.add_edge(edge)
                    self.record_event(rec.edge_id, 'CONSOLIDATE')
                    result.append(rec.edge_id)
        return result
