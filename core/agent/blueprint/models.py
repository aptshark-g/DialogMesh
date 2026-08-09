# -*- coding: utf-8 -*-
"""Blueprint data models — §14.2 BlueprintDAG schema.

BlueprintDAG = LLM-built execution graph, compiled → EventBus.
BlueprintNode = one business chain invocation.
BlueprintEdge = data dependency between chains.
ExecutionAudit = Meta's post-execution scoring record (§14.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

# Valid chain identifiers (10 business chains + llm_reply + tool)
# G1 (FLOW_SELF_GROWTH): tool 链 = 动态生成 DAG 的真实工具执行节点
#   params: {tool: "arxiv_search"|..., args: {...}} → ToolRegistry.execute
CHAIN_IDS = {
    "pcr", "intent", "context", "subgraph", "profile",
    "llm_reply", "behavior", "meta", "discourse", "association",
    "engineering", "metap", "tool",
}

# Valid strategies (§十)
VALID_STRATEGIES = {"RULE_BASED", "TEMPLATE", "HYBRID", "LLM_DRIVEN", "RECOVERY"}


@dataclass
class BlueprintNode:
    """One node in the Blueprint DAG — represents a business chain call.

    node_id: unique within the DAG (e.g. "pcr_0", "intent_1")
    chain: which business chain to invoke (pcr|intent|context|...)
    params: keyword arguments for the chain call
    priority: execution priority, 0 = highest
    checkpoint: if True, pause before this node for PlanGate review
    """
    node_id: str
    chain: str
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    checkpoint: bool = False

    def __post_init__(self):
        if self.chain not in CHAIN_IDS:
            raise ValueError(f"Unknown chain '{self.chain}'. Valid: {sorted(CHAIN_IDS)}")
        if self.priority < 0 or self.priority > 9:
            raise ValueError(f"priority must be 0-9, got {self.priority}")


@dataclass
class BlueprintEdge:
    """Directed data dependency between two BlueprintNodes.

    from_node → to_node: to_node needs data_key from from_node's output.
    required: if True, to_node blocks until from_node completes.
              if False, to_node can proceed with default/empty data.
    """
    from_node: str
    to_node: str
    data_key: str
    required: bool = True


@dataclass
class BlueprintDAG:
    """LLM-built execution graph — compiled → EventBus for execution.

    nodes: all chain invocations in this graph
    edges: data dependencies between nodes
    strategy: which of the 5 Blueprint strategies was used
    confidence: LLM's self-assessed confidence (0.0-1.0)
    design_rationale: why the LLM chose this graph structure
    """
    nodes: List[BlueprintNode] = field(default_factory=list)
    edges: List[BlueprintEdge] = field(default_factory=list)
    strategy: str = "TEMPLATE"
    confidence: float = 1.0
    design_rationale: str = ""

    def __post_init__(self):
        if self.strategy not in VALID_STRATEGIES:
            raise ValueError(f"Invalid strategy '{self.strategy}'. Valid: {sorted(VALID_STRATEGIES)}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")

    @property
    def node_ids(self) -> set:
        return {n.node_id for n in self.nodes}

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def get_node(self, node_id: str) -> Optional[BlueprintNode]:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def incoming_edges(self, node_id: str) -> List[BlueprintEdge]:
        return [e for e in self.edges if e.to_node == node_id]

    def outgoing_edges(self, node_id: str) -> List[BlueprintEdge]:
        return [e for e in self.edges if e.from_node == node_id]

    def roots(self) -> List[BlueprintNode]:
        """Nodes with no incoming edges."""
        has_incoming = {e.to_node for e in self.edges}
        return [n for n in self.nodes if n.node_id not in has_incoming]

    def validate(self) -> List[str]:
        """Check structural validity. Returns list of error messages."""
        errors = []
        ids = self.node_ids
        for e in self.edges:
            if e.from_node not in ids:
                errors.append(f"Edge from unknown node: {e.from_node}")
            if e.to_node not in ids:
                errors.append(f"Edge to unknown node: {e.to_node}")
            if e.from_node == e.to_node:
                errors.append(f"Self-loop edge: {e.from_node} → {e.to_node}")
        return errors


@dataclass
class ExecutionAudit:
    """Post-execution audit record — Meta LLM consumes these (§14.4).

    Key: MetaFeedback.update_strategy_weights() reads dag_quality_score.
    anomalies triggers automatic degradation or learning suggestions.
    """
    request_id: str
    blueprint_id: str
    strategy: str
    dag_quality_score: float = 0.0
    anomalies: List[str] = field(default_factory=list)
