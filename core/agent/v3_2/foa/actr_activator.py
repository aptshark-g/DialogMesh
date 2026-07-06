from .models import AttentionNode


class ACTRActivator:
    DEFAULT_DECAY = 0.3
    ACTIVATION_THRESHOLD = 0.3
    MAX_NODES = 5

    def __init__(self, decay=DEFAULT_DECAY):
        self.decay = decay

    def propagate(self, seeds, node_degrees, edges):
        visited = {}
        for seed in seeds:
            visited[seed] = AttentionNode(seed, 1.0, node_degrees.get(seed, 0), 0)
        queue = list(seeds)
        while queue:
            current = queue.pop(0)
            cur = visited[current]
            for (src, tgt), weight in edges.items():
                if src == current and tgt not in visited:
                    dist = cur.distance_from_seed + 1
                    base = node_degrees.get(tgt, 0)
                    act = base + weight * cur.activation - self.decay * dist
                    if act > self.ACTIVATION_THRESHOLD:
                        visited[tgt] = AttentionNode(tgt, act, base, dist)
                        queue.append(tgt)
        nodes = sorted(visited.values(), key=lambda n: -n.activation)
        return nodes[:self.MAX_NODES]

    def get_subgraph_edges(self, nodes, all_edges):
        ids = {n.node_id for n in nodes}
        return [(s, t) for (s, t) in all_edges if s in ids and t in ids]
