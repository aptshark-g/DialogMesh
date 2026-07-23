from dataclasses import dataclass, field


@dataclass
class AttentionNode:
    node_id: str
    activation: float = 0.0
    base_activation: float = 0.0
    distance_from_seed: int = 0


@dataclass
class FocusResult:
    seed_nodes: list
    activated: list
    subgraph_edges: list
    decay_used: float
    fallback_used: bool = False

    @property
    def top_k(self, k=5):
        return sorted(self.activated, key=lambda n: -n.activation)[:k]
