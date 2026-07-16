"""CausalSubstrate adapter: bridges v3_2 CausalSubstrate into v4 runtime.

Integration:
    BehaviorGraphAdapter.graph → CausalSubstrateAdapter
    Slow Path: process_chain() → update structural_prior on edges
    ContextAssembler: retrieve() → causal insights as ContextItem
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.behavior_graph.adapter import (
    BehaviorGraphAdapter, BehaviorChainResult, BehaviorContextItem,
)

# v3_2 imports (read-only)
from core.agent.v3_2.causal_substrate.causal_substrate import CausalSubstrate as V3CausalSubstrate
from core.agent.v3_2.causal_substrate.skeleton_library import SkeletonLibrary
from core.agent.v3_2.causal_substrate.delta_adjuster import DeltaAdjuster

logger = logging.getLogger(__name__)


@dataclass
class CausalInsight:
    """Normalized causal insight for v4 ContextAssembler."""
    insight_id: str
    edge_key: str
    from_summary: str
    to_summary: str
    structural_prior: float
    confidence: float
    description: str = ""
    metadata: dict = field(default_factory=dict)


class CausalSubstrateAdapter(ContextSource):
    """v4 adapter for v3_2 CausalSubstrate.

    Responsibilities:
        1. Wrap v3_2 CausalSubstrate with v4-typed interfaces
        2. Run causal analysis on BehaviorGraph chains (Slow Path)
        3. Feed causal insights into ContextAssembler (ContextSource)
        4. Update edge structural_prior back to BehaviorGraph

    Integration points:
        - Slow Path: ``process_session_chain()`` after checkpoint
        - ContextAssembler: ``retrieve()`` → causal insights as ContextItem
        - BayesianOptimizer: feedback loop via edge prior updates
    """

    def __init__(
        self,
        behavior_adapter: BehaviorGraphAdapter,
        substrate: Optional[V3CausalSubstrate] = None,
        min_chain_length: int = 10,
    ):
        self._behavior = behavior_adapter
        self._substrate = substrate or V3CausalSubstrate(
            graph=behavior_adapter.graph,
            lib=SkeletonLibrary(),
            adj=DeltaAdjuster(),
        )
        self._min_chain_length = min_chain_length
        self._last_insights: List[CausalInsight] = []
        logger.info(
            "CausalSubstrateAdapter initialized (min_chain=%d)",
            min_chain_length,
        )

    # ── Properties ──

    @property
    def name(self) -> str:
        return "causal"

    @property
    def substrate(self) -> V3CausalSubstrate:
        return self._substrate

    # ── Causal Analysis API (Slow Path) ──

    def should_trigger(self, chain: BehaviorChainResult) -> bool:
        """Check if chain is long enough for causal analysis."""
        return self._substrate.should_trigger(len(chain.steps))

    def process_chain(self, chain: BehaviorChainResult) -> List[CausalInsight]:
        """Run causal analysis on a behavior chain.

        Steps:
            1. Convert BehaviorChainResult → v3_2-compatible chain
            2. Call CausalSubstrate.process_chain()
            3. Update edge structural_prior in BehaviorGraph
            4. Return normalized CausalInsight list
        """
        if not self.should_trigger(chain):
            logger.debug("Chain too short (%d < %d), skipping causal analysis", len(chain.steps), self._min_chain_length)
            return []

        # Build v3_2-compatible step list (BehaviorStep-like objects)
        v3_chain = []
        for item in chain.steps:
            # Create a minimal object with required attributes
            step_proxy = _StepProxy(
                step_id=item.step_id,
                action_summary=item.action_summary,
                action_type=item.action_type,
            )
            v3_chain.append(step_proxy)

        # Run v3_2 causal analysis
        try:
            results = self._substrate.process_chain(v3_chain)
        except Exception as e:
            logger.warning("CausalSubstrate.process_chain failed: %s", e)
            return []

        # Normalize results and update graph
        insights: List[CausalInsight] = []
        for result in results:
            edge_key = result.get("edge_key", "")
            prior = result.get("structural_prior", 0.0)

            # Update graph edge
            updated = self._substrate.update_edge_prior(edge_key, prior)

            # Find edge details for insight
            edge_info = next(
                (e for e in chain.edges if e.get("edge_id") == edge_key),
                {},
            )

            insight = CausalInsight(
                insight_id=f"ci_{edge_key}",
                edge_key=edge_key,
                from_summary=edge_info.get("from_step_id", "?"),
                to_summary=edge_info.get("to_step_id", "?"),
                structural_prior=prior,
                confidence=min(1.0, prior + 0.2),
                description=f"Causal prior updated to {prior:.3f} for edge {edge_key}",
                metadata={
                    "updated": updated,
                    "chain_id": chain.chain_id,
                    "edge_weight": edge_info.get("weight", 0.5),
                },
            )
            insights.append(insight)

        self._last_insights = insights
        logger.info("Causal analysis complete: %d insights from chain '%s'", len(insights), chain.chain_id)
        return insights

    def process_session_chain(self, max_depth: int = 10) -> List[CausalInsight]:
        """Convenience: extract recent chain from BehaviorGraphAdapter and analyze."""
        chain = self._behavior.get_recent_chain(n_steps=max_depth)
        return self.process_chain(chain)

    def update_edge_prior(self, edge_key: str, prior: float) -> bool:
        """Manually update an edge's structural_prior."""
        return self._substrate.update_edge_prior(edge_key, prior)

    # ── ContextSource interface ──

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        """Retrieve causal insights for ContextAssembler.

        If no prior insights exist, runs a quick session chain analysis.
        """
        insights = self._last_insights
        if not insights and self._behavior.node_count > 0:
            insights = self.process_session_chain(max_depth=top_k * 2)

        # Filter by query relevance (simple keyword match on descriptions)
        keywords = query.lower().split()
        scored = []
        for ins in insights:
            text = f"{ins.from_summary} {ins.to_summary} {ins.description}".lower()
            score = sum(1 for kw in keywords if kw in text)
            scored.append((ins, score / max(1, len(keywords))))

        scored.sort(key=lambda x: x[1], reverse=True)

        items = []
        for insight, relevance in scored[:top_k]:
            items.append(ContextItem(
                source=self.name,
                content=insight,
                relevance=relevance * insight.confidence,
                metadata={
                    "edge_key": insight.edge_key,
                    "structural_prior": insight.structural_prior,
                    "confidence": insight.confidence,
                    "insight_id": insight.insight_id,
                },
            ))

        return items

    # ── Statistics ──

    def stats(self) -> Dict[str, Any]:
        return {
            "last_insight_count": len(self._last_insights),
            "min_chain_length": self._min_chain_length,
            "graph_nodes": self._behavior.node_count,
            "graph_edges": self._behavior.edge_count,
        }


# ── Internal helpers ──

class _StepProxy:
    """Minimal proxy object compatible with v3_2 CausalSubstrate expectations."""

    def __init__(self, step_id: str, action_summary: str, action_type: str = ""):
        self.step_id = step_id
        self.action_summary = action_summary
        self.action_type = action_type
