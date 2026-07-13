"""Subgraph overflow pruning: 4-round trim + 3-step landing (stub).
Design ref: docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md §11.3–11.4"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class PruningNode:
    node_id: str; domain: str; content: str; activation_count: int = 0
    last_accessed_turn: int = 0; betweenness: float = 0.0; estimated_tokens: int = 0
    cross_ref_ids: List[str] = field(default_factory=list); compressed: bool = False; summary: Optional[str] = None

@dataclass
class PruningConfig:
    alpha: float = 0.3; beta: float = 0.2; gamma: float = 0.5
    struct_threshold: float = 0.6; recency_turns: int = 3

_INTENT: Dict[str, PruningConfig] = {
    "task": PruningConfig(0.3, 0.2, 0.5), "discussion": PruningConfig(0.2, 0.5, 0.3),
    "correction": PruningConfig(0.5, 0.3, 0.2), "topic_switch": PruningConfig(0.1, 0.6, 0.3),
    "casual": PruningConfig(0.4, 0.4, 0.2), "query": PruningConfig(0.3, 0.3, 0.4),
}

def _sc(n, c, t): return c.alpha*n.activation_count - c.beta*max(0, t-n.last_accessed_turn) + c.gamma*n.betweenness

def _compress(n):
    if not n.compressed: n.summary, n.estimated_tokens, n.compressed = n.content[:40]+"…", max(8, n.estimated_tokens//3), True

class SubgraphPruner:
    """Stub: 4-round trim + 3-step landing. Interfaces complete, logic minimized."""
    def __init__(self, cfg=None): self._cfg = cfg or PruningConfig()

    def prune(self, nodes, budget, turn, intent="task"):
        """R1 capacitance → R2 struct protect → R3 temporal → R4 compress."""
        c = _INTENT.get(intent, self._cfg)
        if not nodes or sum(n.estimated_tokens for n in nodes) <= budget: return list(nodes)
        s = sorted(nodes, key=lambda n: _sc(n, c, turn))
        cand = {n.node_id for n in s[:max(1, int(len(s)*0.3))]}
        cand -= {n.node_id for n in s if n.betweenness > c.struct_threshold}            # R2
        cand -= {n.node_id for n in s if turn - n.last_accessed_turn < c.recency_turns} # R3
        for n in s:                                                                      # R4
            if n.node_id in cand: _compress(n)
        out, used = [], 0
        for n in sorted(s, key=lambda x: _sc(x, c, turn), reverse=True):
            if used + n.estimated_tokens <= budget: out.append(n); used += n.estimated_tokens
        return out

    def topic_switch_landing(self, old, new, budget, turn):
        """Step1 old summary → Step2 keep connectors → Step3 expand new."""
        for n in old:
            if n.betweenness <= self._cfg.struct_threshold: _compress(n)
        keep = [n for n in old if n.betweenness > self._cfg.struct_threshold]
        pruned = self.prune(new, max(0, budget - sum(n.estimated_tokens for n in keep)), turn, "topic_switch")
        return keep + pruned
