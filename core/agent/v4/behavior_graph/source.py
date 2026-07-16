"""BehaviorGraph ContextSource for v4 ContextAssembler.

Provides context items from BehaviorGraph steps and chains.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.behavior_graph.adapter import V4BehaviorGraph


class BehaviorSource(ContextSource):
    """Retrieves behavior context from V4BehaviorGraph.

    Items are scored by:
      - edge weight (success rate proxy)
      - recency (timestamp decay)
      - structural_prior (from CausalSubstrate)
    """

    def __init__(self, behavior_graph: V4BehaviorGraph, max_chain_depth: int = 3):
        self._graph = behavior_graph
        self._max_depth = max_chain_depth

    @property
    def name(self) -> str:
        return "behavior"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._graph is None or self._graph.last_step_id is None:
            return []

        # Retrieve recent chain from last step
        chain = self._graph.get_recent_chain(max_depth=self._max_depth)
        if not chain:
            return []

        items = []
        for step, edge in chain:
            # Compose content from step + edge
            content = self._format_step(step, edge)
            relevance = self._score(step, edge)
            items.append(ContextItem(
                source=self.name,
                content=content,
                relevance=relevance,
                metadata={
                    "step_id": getattr(step, "step_id", ""),
                    "edge_id": getattr(edge, "edge_id", ""),
                    "action_type": getattr(step, "action_type", ""),
                    "timestamp": getattr(step, "timestamp", 0.0),
                    "structural_prior": getattr(edge, "structural_prior", 0.0),
                },
            ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    def _format_step(self, step: Any, edge: Any) -> str:
        """Serialize step and edge into a context string."""
        summary = getattr(step, "action_summary", "")
        result = getattr(step, "result", "")
        weight = getattr(edge, "weight", 0.5) if edge else 0.5
        prior = getattr(edge, "structural_prior", 0.0) if edge else 0.0
        parts = [f"Action: {summary}"]
        if result:
            parts.append(f"Result: {result}")
        parts.append(f"weight={weight:.2f} prior={prior:.2f}")
        return " | ".join(parts)

    def _score(self, step: Any, edge: Any) -> float:
        """Compute relevance score for a step/edge pair."""
        import time
        now = time.time()
        ts = getattr(step, "timestamp", now)
        recency = max(0.0, 1.0 - (now - ts) / 3600.0)  # 1-hour decay

        weight = getattr(edge, "weight", 0.5) if edge else 0.5
        prior = getattr(edge, "structural_prior", 0.0) if edge else 0.0

        # Composite: 50% weight + 30% recency + 20% prior
        return weight * 0.5 + recency * 0.3 + prior * 0.2
