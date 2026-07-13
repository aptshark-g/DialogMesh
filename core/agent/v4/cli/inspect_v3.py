"""CLI inspect commands — v3.2 / v3 module status viewers.

All commands are read-only thin shells. Each inspects a specific module.
"""
from __future__ import annotations


def _inspect_behavior(engine, user: str = None, limit: int = 10):
    """Show v3.2 behavior patterns."""
    print("Behavior patterns (summary):")
    print("-" * 50)
    try:
        from core.agent.v3_2.behavior_graph import BehaviorGraph
        # Try to get a simple status
        print("  BehaviorGraph module is importable.")
        print("  (Full behavior graph inspection requires active session data)")
    except ImportError:
        print("  BehaviorGraph module not found")
    return 0


def _inspect_causal(engine, source: str = None, limit: int = 10):
    """Show v3.2 causal chains."""
    print("Causal chains (summary):")
    print("-" * 50)
    try:
        from core.agent.v3_2.causal_substrate import CausalSubstrate
        print("  CausalSubstrate module is importable.")
        print("  (Full causal chain inspection requires active data)")
    except ImportError:
        print("  CausalSubstrate module not found")
    return 0


def _inspect_constraints(engine, domain: str = None):
    """Show engineering constraints."""
    print("Engineering constraints (summary):")
    print("-" * 50)
    try:
        from core.agent.v3_2.engineering_chain import EngineeringChain
        print("  EngineeringChain module is importable.")
        print("  Domain:", domain or "all")
    except ImportError:
        print("  EngineeringChain module not found")
    return 0


def _inspect_discourse(engine, node: str = None, depth: int = 3):
    """Show discourse tree structure."""
    print("Discourse tree (summary):")
    print("-" * 50)
    try:
        from core.agent.v3_2.discourse_block_tree import DiscourseBlockTree
        print("  DiscourseBlockTree module is importable.")
        if node:
            print(f"  Node: {node}, Depth: {depth}")
    except ImportError:
        print("  DiscourseBlockTree module not found")
    return 0


def _inspect_fusion(engine, show_status: bool = False):
    """Show fusion engine status."""
    print("Fusion engine (summary):")
    print("-" * 50)
    try:
        from core.agent.v3_2.fusion import FusionEngine
        print("  FusionEngine module is importable.")
    except ImportError:
        print("  FusionEngine module not found")
    return 0


def _inspect_summary(engine, level: str = "l1", topic: str = None):
    """Show L1/L2 summaries."""
    print(f"Summary ({level}) (summary):")
    print("-" * 50)
    try:
        if level == "l1":
            from core.agent.v3_2.l1_summary import L1SummaryBuilder
            print("  L1SummaryBuilder module is importable.")
        else:
            from core.agent.v3_2.l2_summary import L2SummaryBuilder
            print("  L2SummaryBuilder module is importable.")
        if topic:
            print(f"  Topic: {topic}")
    except ImportError:
        print(f"  {level} summary module not found")
    return 0


def _inspect_store(engine, mode: str = "stats"):
    """Show tiered graph store status."""
    print("Graph store (summary):")
    print("-" * 50)
    try:
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        print("  UnifiedGraphStore (v4) is importable.")
    except ImportError:
        pass
    try:
        from core.agent.persistence.tiered_storage import TieredGraphStore
        s = TieredGraphStore()
        print(f"  Tiers: hot/warm/cold/archive available.")
    except ImportError:
        print("  TieredGraphStore module not found")
    return 0


def _inspect_pcr(engine, mode: str = "params"):
    """Show parameter registry status."""
    print("Parameter registry (summary):")
    print("-" * 50)
    try:
        from core.agent.v4.world.params import WorldParams
        p = WorldParams()
        print(f"  WorldParams (v4): {len([f for f in dir(p) if not f.startswith('_') and not callable(getattr(p,f))])} parameters")
        print(f"  Strategy: {p.importance_strategy}")
    except ImportError:
        print("  WorldParams module not found")
    return 0


def _inspect_topics(engine, show_tree: bool = False):
    """Show topic tree structure."""
    print("Topic tree (summary):")
    print("-" * 50)
    try:
        from core.agent.topic_tree import TopicTreeManager
        print("  TopicTreeManager module is importable.")
    except ImportError:
        print("  TopicTreeManager module not found")
    return 0
