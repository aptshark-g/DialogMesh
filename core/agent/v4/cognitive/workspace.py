"""CognitiveWorkspace + WorkspaceGraph + ExecutionTrace.

Design: docs/v3.0/DESIGN_COGNITIVE_RUNTIME.md §3, §5
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class CognitiveWorkspace:
    """Single reasoning workspace — the LLM's current thinking space."""
    id: str
    parent_id: Optional[str] = None

    # Input
    goal: str = ""
    focus_objects: List[str] = field(default_factory=list)

    # Working memory
    active_objects: List[str] = field(default_factory=list)
    active_relations: List[dict] = field(default_factory=list)

    # Reasoning output
    reasoning_tree: Optional[dict] = None
    candidate_answers: List[dict] = field(default_factory=list)
    hypotheses: List[dict] = field(default_factory=list)

    # Self-monitoring
    confidence: float = 0.5
    conflicts: List[str] = field(default_factory=list)
    reflection_log: List[dict] = field(default_factory=list)

    # Lifecycle
    state: str = "INIT"
    committed: bool = False
    reasoning_depth: int = 0
    max_reasoning_depth: int = 3
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkspaceNode:
    """A node in the WorkspaceGraph."""
    workspace: CognitiveWorkspace
    children: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    merge_strategy: str = "weighted"
    status: str = "pending"


class WorkspaceGraph:
    """Directed graph of workspaces. Stack is the single-child special case."""

    def __init__(self):
        self.nodes: Dict[str, WorkspaceNode] = {}
        self.root_id: Optional[str] = None

    def add(self, node: WorkspaceNode, parent_id: str = None):
        self.nodes[node.workspace.id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node.workspace.id)
        if self.root_id is None:
            self.root_id = node.workspace.id

    def can_merge(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return True
        return all(
            self.nodes[dep_id].status == "done"
            for dep_id in node.dependencies
            if dep_id in self.nodes
        )

    def merge(self, node_id: str):
        """Merge child hypotheses into parent."""
        node = self.nodes.get(node_id)
        if not node:
            return
        merged_hyp = []
        confidences = []
        for child_id in node.children:
            child = self.nodes.get(child_id)
            if child:
                merged_hyp.extend(child.workspace.hypotheses)
                confidences.append(child.workspace.confidence)
        if merged_hyp:
            node.workspace.hypotheses = merged_hyp
        if confidences:
            node.workspace.confidence = sum(confidences) / len(confidences)


@dataclass
class TraceStep:
    """One cognitive operation recorded for replay/debug."""
    step_id: str
    state: str
    observer_snapshot: dict = field(default_factory=dict)
    workspace_snapshot: dict = field(default_factory=dict)
    decision: str = ""
    llm_input_tokens: int = 0
    llm_output: str = ""
    latency_ms: float = 0.0
    parent_step: Optional[str] = None


class ExecutionTrace:
    """Full trace of one reasoning session."""

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.steps: List[TraceStep] = []
        self.final_answer: str = ""
        self.final_confidence: float = 0.0

    def add(self, step: TraceStep):
        self.steps.append(step)

    def summary(self) -> str:
        states = [s.state for s in self.steps]
        total_ms = sum(s.latency_ms for s in self.steps)
        return (
            f"Trace: {len(self.steps)} steps, {total_ms:.0f}ms, "
            f"path: {' -> '.join(states)}, "
            f"confidence: {self.final_confidence:.2f}"
        )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "steps": [
                {
                    "step_id": s.step_id,
                    "state": s.state,
                    "decision": s.decision,
                    "latency_ms": s.latency_ms,
                }
                for s in self.steps
            ],
            "final_confidence": self.final_confidence,
        }
