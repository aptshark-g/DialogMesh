"""InteractionGraph — dynamic state propagation over relations.

Upgrades RelationGraph from static edges to dynamic interactions:
  Relation:  "A depends_on B" (what)
  Interaction: "When A changes, B changes by weight 0.8" (how + why)

Design: every edge has a propagation_rule that describes HOW state flows.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from enum import Enum
import time

from core.agent.v4.state.state_object import StateObject, StateDelta


# ═══════════════════════ Interaction Types ═══════════════════════

class InteractionType(Enum):
    """How state propagates between nodes."""
    CONTAINS = "contains"          # A contains B → B inherits A's attention
    DEPENDS_ON = "depends_on"      # A depends on B → B's confidence affects A
    IMPLEMENTS = "implements"      # A implements B → B's changes trigger A rebuild
    CAUSAL = "causal"              # A causes B → A's activation propagates to B
    CONTRADICTS = "contradicts"    # A contradicts B → A↑ → B↓
    SUPPORTS = "supports"          # A supports B → A↑ → B↑
    ATTENTION = "attention"        # A attends to B → B's weight increases
    ANALOGOUS = "analogous"        # A is analogous to B → shared attention
    BEHAVIOR = "behavior"          # user behavior pattern edge


# ═══════════════════════ InteractionEdge ═══════════════════════

@dataclass
class InteractionEdge:
    """A dynamic edge that propagates state changes between nodes."""

    source: str                          # source node ID
    target: str                          # target node ID
    interaction_type: InteractionType    # how state propagates

    # ── Propagation rules ──
    influence_weight: float = 0.5        # how strongly source affects target [0,1]
    activation_threshold: float = 0.3    # min source confidence to activate

    # ── Built-in propagation rules (per type) ──
    # These are auto-set based on interaction_type, but can be overridden
    propagation_rule: Optional[Callable] = None

    # ── Metadata ──
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    activation_count: int = 0
    last_activated: float = 0.0

    def propagate(self, source_state: Dict[str, Any], target_state: Dict[str, Any]) -> Dict[str, Any]:
        """Propagate state from source to target.

        Returns updated target_state.
        """
        if self.propagation_rule:
            return self.propagation_rule(source_state, target_state)

        # Default propagation per type
        conf = source_state.get("confidence", 0.5)
        if conf < self.activation_threshold:
            return target_state  # Below threshold: no propagation

        result = dict(target_state)
        delta = conf * self.influence_weight

        if self.interaction_type == InteractionType.SUPPORTS:
            result["confidence"] = min(1.0, target_state.get("confidence", 0.5) + delta * 0.3)
        elif self.interaction_type == InteractionType.CONTRADICTS:
            result["confidence"] = max(0.01, target_state.get("confidence", 0.5) - delta * 0.3)
        elif self.interaction_type == InteractionType.DEPENDS_ON:
            result["attention"] = target_state.get("attention", 0.5) + delta * 0.2
        elif self.interaction_type == InteractionType.CAUSAL:
            result["activation"] = target_state.get("activation", 0.0) + delta * 0.5
        elif self.interaction_type == InteractionType.CONTAINS:
            result["attention"] = max(target_state.get("attention", 0.0), conf * self.influence_weight)
        elif self.interaction_type == InteractionType.ATTENTION:
            result["attention"] = min(1.0, target_state.get("attention", 0.5) + delta * 0.15)
        elif self.interaction_type == InteractionType.IMPLEMENTS:
            result["consistency"] = target_state.get("consistency", 0.5) + delta * 0.1

        return result


# ═══════════════════════ InteractionGraph ═══════════════════════

class InteractionGraph:
    """Dynamic graph where state propagates along typed edges.

    Usage:
        graph = InteractionGraph()
        graph.add_edge("Runtime", "Scheduler", InteractionType.DEPENDS_ON, influence=0.9)
        graph.add_edge("Scheduler", "Observation", InteractionType.USES, influence=0.7)

        # When Runtime's confidence changes, propagate to all neighbors:
        graph.propagate("Runtime", {"confidence": 0.8})
        # → Scheduler.attention += 0.8*0.9*0.2 = +0.144
        # → (chain) Observation.attention += ...
    """

    def __init__(self):
        self._adjacency: Dict[str, List[InteractionEdge]] = {}   # source → [edges]
        self._node_states: Dict[str, Dict[str, Any]] = {}        # node_id → state
        self._edge_count: int = 0

    # ── CRUD ──

    def add_edge(
        self,
        source: str,
        target: str,
        interaction_type: InteractionType,
        influence_weight: float = 0.5,
        evidence: List[str] = None,
        confidence: float = 0.5,
    ) -> InteractionEdge:
        """Add an interaction edge."""
        edge = InteractionEdge(
            source=source, target=target,
            interaction_type=interaction_type,
            influence_weight=influence_weight,
            evidence=evidence or [],
            confidence=confidence,
        )
        self._adjacency.setdefault(source, []).append(edge)
        self._edge_count += 1

        # Initialize node states
        if source not in self._node_states:
            self._node_states[source] = {"confidence": 0.5, "attention": 0.5}
        if target not in self._node_states:
            self._node_states[target] = {"confidence": 0.5, "attention": 0.5}

        return edge

    def get_node_state(self, node_id: str) -> Dict[str, Any]:
        return self._node_states.get(node_id, {})

    def set_node_state(self, node_id: str, state: Dict[str, Any]):
        self._node_states[node_id] = state

    # ── Propagation ──

    def propagate(
        self,
        node_id: str,
        new_state: Dict[str, Any],
        max_depth: int = 3,
        visited: Set[str] = None,
    ) -> List[StateDelta]:
        """Propagate state changes from a node through the graph.

        Returns list of StateDelta describing what changed.
        """
        if visited is None:
            visited = set()
        if node_id in visited or max_depth <= 0:
            return []

        visited.add(node_id)
        old_state = self._node_states.get(node_id, {})
        self._node_states[node_id] = {**old_state, **new_state}

        deltas = []
        for edge in self._adjacency.get(node_id, []):
            target_old = self._node_states.get(edge.target, {})
            target_new = edge.propagate(new_state, target_old)
            self._node_states[edge.target] = target_new

            # Record delta
            for key, new_val in target_new.items():
                old_val = target_old.get(key, 0)
                if abs(new_val - old_val) > 0.001:
                    deltas.append(StateDelta(
                        key=f"{edge.target}.{key}",
                        operation="set",
                        value=new_val,
                    ))

            edge.activation_count += 1
            edge.last_activated = time.time()

            # Recurse: propagate further
            if max_depth > 1:
                deltas.extend(
                    self.propagate(edge.target, target_new, max_depth - 1, visited)
                )

        return deltas

    def propagate_chain(
        self,
        chain: List[str],
        initial_state: Dict[str, Any],
    ) -> List[StateDelta]:
        """Propagate state along an explicit chain of nodes.

        Example: propagate_chain(["Runtime","Scheduler","Observation"], {"conf":0.8})
        """
        all_deltas = []
        current_state = initial_state
        for node in chain:
            self.set_node_state(node, current_state)
            deltas = self.propagate(node, current_state, max_depth=1)
            all_deltas.extend(deltas)
            current_state = self.get_node_state(node)
        return all_deltas

    # ── Query ──

    def get_causal_chain(
        self, start: str, min_confidence: float = 0.5, max_depth: int = 5
    ) -> List[str]:
        """Get a causal chain starting from a node."""
        chain = [start]
        visited = {start}
        self._dfs_causal(start, chain, visited, min_confidence, max_depth)
        return chain

    def _dfs_causal(self, node, chain, visited, min_conf, depth):
        if depth <= 0:
            return
        for edge in self._adjacency.get(node, []):
            if edge.interaction_type in (InteractionType.CAUSAL, InteractionType.DEPENDS_ON):
                if edge.confidence >= min_conf and edge.target not in visited:
                    visited.add(edge.target)
                    chain.append(edge.target)
                    self._dfs_causal(edge.target, chain, visited, min_conf, depth - 1)

    def get_attention_subgraph(self, focus_nodes: List[str], radius: int = 2) -> Set[str]:
        """Get the subgraph within `radius` hops of focus nodes."""
        subgraph = set(focus_nodes)
        frontier = set(focus_nodes)
        for _ in range(radius):
            next_frontier = set()
            for node in frontier:
                for edge in self._adjacency.get(node, []):
                    if edge.target not in subgraph:
                        subgraph.add(edge.target)
                        next_frontier.add(edge.target)
            frontier = next_frontier
        return subgraph

    # ── Stats ──

    def stats(self) -> Dict[str, Any]:
        return {
            "nodes": len(self._node_states),
            "edges": self._edge_count,
            "avg_influence": sum(e.influence_weight for edges in self._adjacency.values() for e in edges) / max(1, self._edge_count),
            "most_active": max(
                ((e.source, e.target, e.activation_count) for edges in self._adjacency.values() for e in edges),
                key=lambda x: x[2], default=("", "", 0),
            ),
        }
