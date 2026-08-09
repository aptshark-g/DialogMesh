"""CausalSubstrate ContextSource for v4 ContextAssembler.

Provides causal inference context (structural_prior, edge analysis)
as IREntry items for CrossDomainContextIR.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.agent.context.source import ContextSource, ContextItem
from core.agent.v4.causal_substrate.adapter import CausalSubstrateAdapter


class CausalSource(ContextSource):
    """Retrieves causal context from the v4 CausalSubstrateAdapter.

    Items include:
      - Edge structural_prior values
      - Causal chain summaries
      - Trigger status (whether causal processing fired)
    """

    def __init__(self, causal_substrate: CausalSubstrateAdapter):
        self._substrate = causal_substrate

    @property
    def name(self) -> str:
        return "causal"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._substrate is None:
            return []

        # The v4 adapter lazily owns the v3_2 CausalSubstrate; read through it.
        inner = getattr(self._substrate, "_substrate", None)
        graph = getattr(inner, "graph", None) if inner is not None else None
        stats = {
            "min_chain": getattr(self._substrate, "_min_chain", 10),
            "graph_node_count": len(getattr(graph, "nodes", {}) or {}),
            "graph_edge_count": len(getattr(graph, "edges", {}) or {}),
        }
        items = []

        # Add a summary item
        items.append(ContextItem(
            source=self.name,
            content=f"CausalSubstrate active: min_chain={stats.get('min_chain', 10)}, "
                    f"nodes={stats.get('graph_node_count', 0)}, "
                    f"edges={stats.get('graph_edge_count', 0)}",
            relevance=0.6,
            metadata={"type": "substrate_summary", "stats": stats},
        ))

        # If the substrate has been initialized, scan top edges by structural_prior
        if graph is not None:
            edges = sorted(
                (getattr(graph, "edges", {}) or {}).values(),
                key=lambda e: getattr(e, "structural_prior", 0.0),
                reverse=True,
            )
            for edge in edges[:top_k]:
                prior = getattr(edge, "structural_prior", 0.0)
                if prior <= 0.0:
                    continue
                items.append(ContextItem(
                    source=self.name,
                    content=f"Edge {getattr(edge, 'edge_id', '')}: "
                            f"structural_prior={prior:.3f}, "
                            f"weight={getattr(edge, 'weight', 0.5):.3f}, "
                            f"success_rate={getattr(edge, 'success_rate', 0.5):.3f}",
                    relevance=min(1.0, prior + 0.3),
                    metadata={
                        "edge_id": getattr(edge, "edge_id", ""),
                        "structural_prior": prior,
                        "type": "edge_prior",
                    },
                ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]
