"""CausalSubstrate v4 adapter: bridges v3_2 CausalSubstrate into v4 Slow Path.

Design:
- Wraps v3_2 CausalSubstrate behind RuntimeAdapter interface
- Reads BehaviorGraph from ctx.world_graph (set by BehaviorGraphAdapter)
- Triggers on chain length threshold (MIN_CHAIN from v3_2)
- Writes structural_prior back to graph edges
- Produces CausalContext entries for ContextAssembler
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.runtime.adapter import RuntimeAdapter, RuntimeContext, AdapterResult

logger = logging.getLogger(__name__)


@dataclass
class CausalContextEntry:
    """A single causal inference result for v4 ContextAssembler."""
    edge_key: str
    from_step_id: str
    to_step_id: str
    structural_prior: float
    confidence: float
    chain_position: int
    timestamp: float = field(default_factory=time.time)


class CausalSubstrateAdapter(RuntimeAdapter):
    """Wraps v3_2 CausalSubstrate for v4 Slow Path.

    Usage in engine:
        adapter = CausalSubstrateAdapter(name="causal_substrate")
        result = adapter.timed_execute(ctx)  # processes behavior chain

    Prerequisites:
        - ctx.world_graph must be set by BehaviorGraphAdapter (upstream Async Path)
        - ctx.observations should contain recent behavior steps

    Output:
        - AdapterResult.data = List[CausalContextEntry]
        - Graph edges updated with structural_prior
    """

    def __init__(self, name: str = "causal_substrate", timeout_ms: int = 30000,
                 retry: int = 1, params: dict = None):
        super().__init__(name, timeout_ms, retry, params)
        self._min_chain: int = params.get("min_chain", 10) if params else 10
        self._substrate: Optional[Any] = None
        self._entries: List[CausalContextEntry] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def _init_substrate(self, graph: Any) -> None:
        """Lazy-init CausalSubstrate with graph."""
        if self._substrate is None or self._substrate.graph is not graph:
            from core.agent.v3_2.causal_substrate.causal_substrate import CausalSubstrate
            self._substrate = CausalSubstrate(graph)
            logger.debug("CausalSubstrate initialized with graph (%d nodes)",
                         len(graph.nodes) if hasattr(graph, "nodes") else 0)

    # ------------------------------------------------------------------ #
    # RuntimeAdapter interface
    # ------------------------------------------------------------------ #

    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        graph = getattr(ctx, "world_graph", None)
        if graph is None:
            return AdapterResult(
                ok=False,
                error="No world_graph in context. Run BehaviorGraphAdapter first.",
                adapter_name=self.name,
            )

        self._init_substrate(graph)

        # Build behavior chain from observations or graph
        chain = self._build_chain(ctx)
        chain_len = len(chain)

        if chain_len < self._min_chain:
            return AdapterResult(
                ok=True,
                data={
                    "chain_len": chain_len,
                    "triggered": False,
                    "min_chain": self._min_chain,
                    "entries": [],
                },
                adapter_name=self.name,
            )

        # Process chain through CausalSubstrate
        results = self._substrate.process_chain(chain)

        # Convert to CausalContextEntry and update graph edges
        entries: List[CausalContextEntry] = []
        for i, result in enumerate(results):
            edge_key = result.get("edge_key", "")
            prior = result.get("structural_prior", 0.0)

            # Update graph edge
            self._substrate.update_edge_prior(edge_key, prior)

            # Find edge metadata
            edge = graph.edges.get(edge_key) if hasattr(graph, "edges") else None
            entries.append(CausalContextEntry(
                edge_key=edge_key,
                from_step_id=getattr(edge, "from_step_id", "") if edge else "",
                to_step_id=getattr(edge, "to_step_id", "") if edge else "",
                structural_prior=prior,
                confidence=min(1.0, prior + 0.3),  # v4 confidence heuristic
                chain_position=i,
            ))

        self._entries = entries

        # Attach causal entries to context for downstream ContextAssembler
        ctx.hypotheses.extend(entries)

        return AdapterResult(
            ok=True,
            data={
                "chain_len": chain_len,
                "triggered": True,
                "entries": entries,
                "entry_count": len(entries),
            },
            adapter_name=self.name,
        )

    # ------------------------------------------------------------------ #
    # Chain building
    # ------------------------------------------------------------------ #

    def _build_chain(self, ctx: RuntimeContext) -> List[Any]:
        """Build behavior chain from observations or graph traversal."""
        chain: List[Any] = []

        # Prefer observations that contain behavior steps
        for obs in ctx.observations:
            if obs is None:
                continue
            # Case 1: observation is a BehaviorStep-like object
            if hasattr(obs, "action_summary"):
                chain.append(obs)
            # Case 2: observation is a dict with step_id
            elif isinstance(obs, dict) and "step_id" in obs:
                chain.append(obs)

        # Fallback: traverse graph from last known step
        if not chain and hasattr(ctx, "world_graph") and ctx.world_graph is not None:
            graph = ctx.world_graph
            # Try to get recent steps from graph
            if hasattr(graph, "nodes") and graph.nodes:
                # Sort by timestamp descending, take up to min_chain
                steps = sorted(
                    graph.nodes.values(),
                    key=lambda s: getattr(s, "timestamp", 0.0),
                    reverse=True,
                )
                chain = steps[:self._min_chain]
                chain.reverse()  # chronological order

        return chain

    # ------------------------------------------------------------------ #
    # Query API
    # ------------------------------------------------------------------ #

    def get_entries(self) -> List[CausalContextEntry]:
        return list(self._entries)

    def should_trigger(self, chain_len: int) -> bool:
        """Check if chain length meets threshold."""
        if self._substrate is None:
            return chain_len > self._min_chain
        return self._substrate.should_trigger(chain_len)
