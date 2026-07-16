"""CausalRetrievalPlanner: v4 adapter initialization and engine integration helpers.

This module provides factory functions and the __init__ exports for the
``core.agent.v4.causal`` package.
"""
from __future__ import annotations
from typing import Optional

from .planner import CausalPlanner, CausalContextSource, CausalChainResult, BehaviorStepIR, BehaviorEdgeIR

__all__ = [
    "CausalPlanner",
    "CausalContextSource",
    "CausalChainResult",
    "BehaviorStepIR",
    "BehaviorEdgeIR",
    "create_causal_planner",
    "create_causal_source",
]


def create_causal_planner(
    graph_path: Optional[str] = None,
    behavior_graph=None,
    causal_substrate=None,
) -> CausalPlanner:
    """Factory: create a CausalPlanner with optional pre-injected v3_2 instances.

    Args:
        graph_path: Path to a saved BehaviorGraph JSON (optional).
        behavior_graph: Pre-built v3_2 BehaviorGraph instance (optional).
        causal_substrate: Pre-built v3_2 CausalSubstrate instance (optional).

    Returns:
        Configured CausalPlanner instance.
    """
    return CausalPlanner(
        graph_path=graph_path,
        behavior_graph=behavior_graph,
        causal_substrate=causal_substrate,
    )


def create_causal_source(planner: CausalPlanner) -> CausalContextSource:
    """Factory: wrap a CausalPlanner into a ContextSource.

    Args:
        planner: The CausalPlanner instance to wrap.

    Returns:
        CausalContextSource ready for ContextAssembler.
    """
    return CausalContextSource(planner)
