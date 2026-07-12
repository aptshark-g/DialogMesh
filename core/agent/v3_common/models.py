# -*- coding: utf-8 -*-
"""
core/agent/models.py
────────────────────
Industrial-grade data models for the layered Agent architecture.
All entities are serializable, hashable, and type-safe.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from typing import (
    Dict, List, Any, Optional, Set, Tuple, Union, Callable,
    Iterator, Iterable, FrozenSet,
)
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class IntentCategory(Enum):
    """Top-level intent classification for reverse engineering tasks."""
    # ── Memory operations ─────────────────────────────────────────────
    SCAN_MEMORY = "scan_memory"           # first_scan / next_scan
    READ_MEMORY = "read_memory"           # read_memory
    WRITE_MEMORY = "write_memory"         # write_memory
    RESOLVE_POINTER = "resolve_pointer"   # pointer chain resolution
    # ── Code analysis ─────────────────────────────────────────────────
    DISASSEMBLE = "disassemble"           # disassemble / disassemble_region
    DECOMPILE = "decompile"               # Ghidra decompilation
    ANALYZE_PROTECTION = "analyze_protection"  # packer / anti-debug detection
    DEOBFUSCATE = "deobfuscate"           # junk code removal
    UNPACK = "unpack"                     # unpack module
    # ── Dynamic tracing ───────────────────────────────────────────────
    SET_BREAKPOINT = "set_breakpoint"     # debugger / DFG breakpoint
    GET_BREAKPOINT_HITS = "get_breakpoint_hits"
    TRACE_EXECUTION = "trace_execution"   # run + trace
    # ── Pattern / heuristic ───────────────────────────────────────────
    FIND_PATTERN = "find_pattern"         # AOB / signature scan
    PATTERN_DETECT = "pattern_detect"     # ML-based pattern detection
    # ── Symbolic / formal ─────────────────────────────────────────────
    BUILD_CFG = "build_cfg"               # angr CFG
    SYMBOLIC_EXECUTE = "symbolic_execute" # angr symbolic execution
    SOLVE_CONSTRAINTS = "solve_constraints"  # Z3
    VERIFY_INPUT = "verify_input"         # Unicorn emulation
    # ── High-level compound ───────────────────────────────────────────
    ANALYZE_PROCESS = "analyze_process"   # full process analysis
    HACK_VALUE = "hack_value"             # scan → verify → write
    FIND_FUNCTION = "find_function"       # locate function by signature / name
    EXPLOIT_VULNERABILITY = "exploit_vulnerability"  # PoC generation
    # ── Meta ──────────────────────────────────────────────────────────
    ASK_USER = "ask_user"                 # clarification
    FINISH = "finish"                     # terminate session
    UNKNOWN = "unknown"                   # unclassified
    CHITCHAT = "chitchat"                 # non-task conversation


class EntityType(Enum):
    """Entity types extracted from natural language."""
    # Addresses & memory
    MEMORY_ADDRESS = "memory_address"       # 0x00400000, 0x7FFE0000
    POINTER_CHAIN = "pointer_chain"       # [[base+0x10]+0x20]+0x8
    MEMORY_SIZE = "memory_size"           # 256, 0x1000
    # Values
    NUMERIC_VALUE = "numeric_value"       # 100, 3.14, 0xDEADBEEF
    STRING_VALUE = "string_value"         # "health", "ammo"
    BYTE_PATTERN = "byte_pattern"         # "48 89 5C 24 ??", "AB CD EF"
    # Process & module
    PROCESS_NAME = "process_name"         # "notepad.exe", "game.exe"
    PID = "pid"                           # 1234
    MODULE_NAME = "module_name"           # "kernel32.dll", "game.dll"
    FUNCTION_NAME = "function_name"       # "CreateProcessW", "sub_1234"
    # Scan
    SCAN_TYPE = "scan_type"               # "exact", "unknown", "changed"
    DATA_TYPE = "data_type"               # "4 bytes", "float", "double", "byte"
    # Debugger
    BREAKPOINT_ADDRESS = "breakpoint_address"
    BREAKPOINT_TYPE = "breakpoint_type"   # "write", "read", "execute"
    # Ghidra / static
    SYMBOL_NAME = "symbol_name"           # "main", "_start"
    # Temporal
    TIME_EXPRESSION = "time_expression"   # "after 5 seconds", "when it changes"
    # Condition
    CONDITION = "condition"               # "greater than 100", "equals player id"


class TaskStatus(Enum):
    """Lifecycle state of a TaskNode."""
    PENDING = "pending"       # Waiting for dependencies
    RUNNING = "running"       # Currently executing
    SUCCESS = "success"       # Completed successfully
    FAILED = "failed"         # Execution failed
    BLOCKED = "blocked"       # Blocked by upstream failure
    CANCELLED = "cancelled"   # Explicitly cancelled
    SKIPPED = "skipped"       # Condition evaluated false
    NEEDS_CLARIFICATION = "needs_clarification"  # Ambiguous, waiting for user


class DependencyType(Enum):
    """Types of edges in the Task DAG."""
    SEQUENTIAL = "sequential"   # B must wait for A to finish
    CONDITIONAL = "conditional"   # B only runs if A succeeded / condition met
    ITERATIVE = "iterative"     # B may run multiple times while A produces results
    PARALLEL = "parallel"       # B can run concurrently with A (synchronization point)
    FALLBACK = "fallback"       # B is an alternative if A fails


class ConfidenceLevel(Enum):
    """Confidence in an extraction or classification."""
    CERTAIN = 1.0
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    GUESS = 0.2
    UNKNOWN = 0.0


class AmbiguityType(Enum):
    """Types of ambiguity that require clarification."""
    MISSING_ENTITY = "missing_entity"         # Required value not provided
    AMBIGUOUS_ENTITY = "ambiguous_entity"     # Multiple possible interpretations
    CONFLICTING_ENTITIES = "conflicting_entities"  # Entities contradict each other
    VAGUE_SCOPE = "vague_scope"               # Unclear what memory region / module
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MULTIPLE_INTENTS = "multiple_intents"     # User likely wants several things at once


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Entity:
    """A typed value extracted from user input."""
    type: EntityType
    value: Any
    raw_text: str = ""           # Original substring from user input
    confidence: float = 1.0      # 0.0–1.0
    start_pos: int = -1
    end_pos: int = -1
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self):
        # Validate confidence range
        if not (0.0 <= self.confidence <= 1.0):
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Entity":
        return cls(
            type=EntityType(d["type"]),
            value=d["value"],
            raw_text=d.get("raw_text", ""),
            confidence=d.get("confidence", 1.0),
            start_pos=d.get("start_pos", -1),
            end_pos=d.get("end_pos", -1),
            metadata=d.get("metadata", {}),
        )

    def __str__(self) -> str:
        return f"Entity({self.type.value}={self.value}, conf={self.confidence:.2f})"


@dataclass(frozen=False)
class Intent:
    """A parsed, classified user intent with all extracted entities."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: IntentCategory = IntentCategory.UNKNOWN
    raw_input: str = ""
    normalized_input: str = ""
    entities: List[Entity] = field(default_factory=list)
    confidence: float = 0.0
    # Multi-intent detection: if the user said several things at once
    sub_intents: List["Intent"] = field(default_factory=list)
    # Context flags
    requires_process: bool = True      # Does this need an attached process?
    is_destructive: bool = False      # Does this write / modify memory?
    is_reversible: bool = False        # Can we undo it automatically?
    # Ambiguity
    ambiguities: List["Ambiguity"] = field(default_factory=list)
    # Timing / scope modifiers
    temporal_constraint: Optional[str] = None
    scope_constraint: Optional[str] = None
    # Metadata
    created_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_entities(self, etype: EntityType) -> List[Entity]:
        """Filter entities by type."""
        return [e for e in self.entities if e.type == etype]

    def get_entity(self, etype: EntityType) -> Optional[Entity]:
        """Get first entity of a given type, or None."""
        for e in self.entities:
            if e.type == etype:
                return e
        return None

    def has_entity(self, etype: EntityType) -> bool:
        return any(e.type == etype for e in self.entities)

    def is_ambiguous(self) -> bool:
        return len(self.ambiguities) > 0 or len(self.sub_intents) > 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "raw_input": self.raw_input,
            "normalized_input": self.normalized_input,
            "entities": [e.to_dict() for e in self.entities],
            "confidence": self.confidence,
            "sub_intents": [si.to_dict() for si in self.sub_intents],
            "requires_process": self.requires_process,
            "is_destructive": self.is_destructive,
            "is_reversible": self.is_reversible,
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "temporal_constraint": self.temporal_constraint,
            "scope_constraint": self.scope_constraint,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Intent":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            category=IntentCategory(d.get("category", "unknown")),
            raw_input=d.get("raw_input", ""),
            normalized_input=d.get("normalized_input", ""),
            entities=[Entity.from_dict(e) for e in d.get("entities", [])],
            confidence=d.get("confidence", 0.0),
            sub_intents=[Intent.from_dict(si) for si in d.get("sub_intents", [])],
            requires_process=d.get("requires_process", True),
            is_destructive=d.get("is_destructive", False),
            is_reversible=d.get("is_reversible", False),
            ambiguities=[Ambiguity.from_dict(a) for a in d.get("ambiguities", [])],
            temporal_constraint=d.get("temporal_constraint"),
            scope_constraint=d.get("scope_constraint"),
            created_at=d.get("created_at", time.time()),
            session_id=d.get("session_id"),
            metadata=d.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"Intent({self.id}, {self.category.value}, "
            f"entities={len(self.entities)}, ambiguities={len(self.ambiguities)})"
        )


@dataclass(frozen=False)
class Ambiguity:
    """An ambiguity detected during parsing that requires clarification."""
    type: AmbiguityType
    description: str
    affected_entities: List[EntityType] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    # If the ambiguity can be resolved by a default heuristic
    auto_resolvable: bool = False
    default_choice: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "affected_entities": [e.value for e in self.affected_entities],
            "suggestions": self.suggestions,
            "auto_resolvable": self.auto_resolvable,
            "default_choice": self.default_choice,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Ambiguity":
        return cls(
            type=AmbiguityType(d.get("type", "missing_entity")),
            description=d.get("description", ""),
            affected_entities=[EntityType(e) for e in d.get("affected_entities", [])],
            suggestions=d.get("suggestions", []),
            auto_resolvable=d.get("auto_resolvable", False),
            default_choice=d.get("default_choice"),
            metadata=d.get("metadata", {}),
        )


@dataclass(frozen=False)
class TaskNode:
    """A single node in the TaskGraph — represents one conceptual step."""
    id: str = field(default_factory=lambda: f"T-{str(uuid.uuid4())[:8]}")
    name: str = ""                       # Human-readable label
    description: str = ""                # Detailed explanation
    # Layer mapping
    intent_id: Optional[str] = None      # Link back to originating Intent
    layer: int = 1                       # 1=concept, 2=engineering, 3=execution
    # Planning
    goal: str = ""                       # What this node tries to achieve
    strategy: str = ""                   # How it plans to achieve it
    # Execution
    tool_name: Optional[str] = None     # Concrete tool to call (Layer 3)
    tool_params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    # Alternatives (for backtracking)
    alternative_strategies: List[str] = field(default_factory=list)
    fallback_nodes: List[str] = field(default_factory=list)  # IDs of fallback TaskNodes
    # Metadata
    estimated_cost: float = 1.0          # Estimated LLM token / time cost
    priority: int = 0                    # Higher = more urgent
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Runtime helpers ──────────────────────────────────────────────

    def mark_running(self):
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_success(self, result: Dict[str, Any]):
        self.status = TaskStatus.SUCCESS
        self.result = result
        self.finished_at = time.time()
        self.error = None

    def mark_failed(self, error: str):
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = time.time()

    def mark_blocked(self):
        self.status = TaskStatus.BLOCKED

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "intent_id": self.intent_id,
            "layer": self.layer,
            "goal": self.goal,
            "strategy": self.strategy,
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "alternative_strategies": self.alternative_strategies,
            "fallback_nodes": self.fallback_nodes,
            "estimated_cost": self.estimated_cost,
            "priority": self.priority,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskNode":
        return cls(
            id=d.get("id", f"T-{str(uuid.uuid4())[:8]}"),
            name=d.get("name", ""),
            description=d.get("description", ""),
            intent_id=d.get("intent_id"),
            layer=d.get("layer", 1),
            goal=d.get("goal", ""),
            strategy=d.get("strategy", ""),
            tool_name=d.get("tool_name"),
            tool_params=d.get("tool_params", {}),
            status=TaskStatus(d.get("status", "pending")),
            result=d.get("result"),
            error=d.get("error"),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            alternative_strategies=d.get("alternative_strategies", []),
            fallback_nodes=d.get("fallback_nodes", []),
            estimated_cost=d.get("estimated_cost", 1.0),
            priority=d.get("priority", 0),
            tags=set(d.get("tags", [])),
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            metadata=d.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return f"TaskNode({self.id}, {self.name}, {self.status.value})"


@dataclass(frozen=False)
class TaskEdge:
    """Directed edge in the Task DAG."""
    source_id: str
    target_id: str
    dep_type: DependencyType = DependencyType.SEQUENTIAL
    condition: Optional[str] = None   # e.g., "source.status == SUCCESS and result.count < 10"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "dep_type": self.dep_type.value,
            "condition": self.condition,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskEdge":
        return cls(
            source_id=d["source_id"],
            target_id=d["target_id"],
            dep_type=DependencyType(d.get("dep_type", "sequential")),
            condition=d.get("condition"),
            metadata=d.get("metadata", {}),
        )


class TaskGraph:
    """A DAG of TaskNodes with dependency tracking and topological scheduling."""

    def __init__(self, intent_id: Optional[str] = None):
        self.intent_id: Optional[str] = intent_id
        self.nodes: Dict[str, TaskNode] = {}
        self.edges: List[TaskEdge] = []
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._lock = None  # Initialized lazily for thread safety
        self.metadata: Dict[str, Any] = {}
        self.created_at: float = time.time()

    # ── Node management ─────────────────────────────────────────────

    def add_node(self, node: TaskNode) -> TaskNode:
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str) -> Optional[TaskNode]:
        node = self.nodes.pop(node_id, None)
        if node:
            # Remove all edges connected to this node
            self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
            self._rebuild_index()
        return node

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        return self.nodes.get(node_id)

    # ── Edge management ───────────────────────────────────────────────

    def add_edge(self, edge: TaskEdge) -> None:
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise ValueError(f"Edge references non-existent node: {edge}")
        self.edges.append(edge)
        self._incoming[edge.target_id].add(edge.source_id)
        self._outgoing[edge.source_id].add(edge.target_id)

    def add_dependency(
        self,
        source_id: str,
        target_id: str,
        dep_type: DependencyType = DependencyType.SEQUENTIAL,
        condition: Optional[str] = None,
    ) -> None:
        self.add_edge(TaskEdge(source_id, target_id, dep_type, condition))

    def get_dependencies(self, node_id: str) -> Set[str]:
        return self._incoming.get(node_id, set()).copy()

    def get_dependents(self, node_id: str) -> Set[str]:
        return self._outgoing.get(node_id, set()).copy()

    # ── Query & traversal ────────────────────────────────────────────

    def get_roots(self) -> List[TaskNode]:
        """Nodes with no incoming edges."""
        return [n for n in self.nodes.values() if not self._incoming.get(n.id)]

    def get_leaves(self) -> List[TaskNode]:
        """Nodes with no outgoing edges."""
        return [n for n in self.nodes.values() if not self._outgoing.get(n.id)]

    def topological_order(self) -> List[TaskNode]:
        """Kahn's algorithm. Returns empty list if cycle detected."""
        in_degree = {nid: len(self._incoming.get(nid, set())) for nid in self.nodes}
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order: List[str] = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for dep_nid in self._outgoing.get(nid, set()):
                in_degree[dep_nid] -= 1
                if in_degree[dep_nid] == 0:
                    queue.append(dep_nid)
        if len(order) != len(self.nodes):
            # Cycle detected — return partial order + log warning
            return [self.nodes[nid] for nid in order]
        return [self.nodes[nid] for nid in order]

    def get_ready_nodes(self) -> List[TaskNode]:
        """Nodes whose all dependencies are SUCCESS."""
        ready: List[TaskNode] = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps = self._incoming.get(node.id, set())
            if all(self.nodes[d].status == TaskStatus.SUCCESS for d in deps):
                ready.append(node)
        return ready

    def get_blocked_nodes(self) -> List[TaskNode]:
        """Nodes with at least one failed dependency."""
        blocked: List[TaskNode] = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps = self._incoming.get(node.id, set())
            if any(self.nodes[d].status in (TaskStatus.FAILED, TaskStatus.BLOCKED) for d in deps):
                blocked.append(node)
        return blocked

    # ── Fallback & retry chains ───────────────────────────────────────

    def get_fallback_chain(self, node_id: str) -> List[TaskNode]:
        """Return ordered list of fallback nodes for a given node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        chain: List[TaskNode] = []
        for fid in node.fallback_nodes:
            fnode = self.nodes.get(fid)
            if fnode:
                chain.append(fnode)
        return chain

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskGraph":
        graph = cls(intent_id=d.get("intent_id"))
        for nid, nd in d.get("nodes", {}).items():
            graph.add_node(TaskNode.from_dict(nd))
        for ed in d.get("edges", []):
            graph.add_edge(TaskEdge.from_dict(ed))
        graph.metadata = d.get("metadata", {})
        graph.created_at = d.get("created_at", time.time())
        return graph

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    @classmethod
    def from_json(cls, s: str) -> "TaskGraph":
        return cls.from_dict(json.loads(s))

    # ── Internal ──────────────────────────────────────────────────────

    def _rebuild_index(self) -> None:
        self._incoming.clear()
        self._outgoing.clear()
        for e in self.edges:
            self._incoming[e.target_id].add(e.source_id)
            self._outgoing[e.source_id].add(e.target_id)

    def __repr__(self) -> str:
        return f"TaskGraph(nodes={len(self.nodes)}, edges={len(self.edges)}, intent={self.intent_id})"

    # ── Display helpers (for interactive_test.py) ────────────────────────

    def to_ascii(self) -> str:
        """Render TaskGraph as ASCII tree."""
        if not self.nodes:
            return "  [空任务图]"
        # Sort by layer then creation time
        order = sorted(self.nodes.values(), key=lambda n: (n.layer, n.created_at))
        # Find roots (no incoming edges)
        roots = [n for n in order if not self._incoming.get(n.id, set())]
        if not roots:
            roots = [order[0]]
        lines = [f"  TaskGraph: {self.intent_id or 'unknown'} ({len(self.nodes)} nodes, {len(self.edges)} edges)"]
        lines.append("")
        visited: set = set()
        for root in roots:
            _render_task_subtree(root, self, 0, lines, visited)
        # Status summary
        status_counts: Dict[str, int] = {}
        for n in self.nodes.values():
            status_counts[n.status.value] = status_counts.get(n.status.value, 0) + 1
        lines.append("")
        lines.append(f"  状态: {', '.join(f'{k}={v}' for k, v in status_counts.items())}")
        return "\n".join(lines)


def _render_task_subtree(node, graph, depth, lines, visited):
    if node.id in visited:
        return
    visited.add(node.id)
    indent = "    " + "│   " * depth
    prefix = "├─ " if depth > 0 else ""
    status_icon = {
        "pending": "⏳", "running": "🔄", "success": "✅", "failed": "❌",
        "blocked": "🚫", "cancelled": "⛔", "skipped": "⏭️", "needs_clarification": "❓",
    }.get(node.status.value, "•")
    layer_label = {1: "[概念]", 2: "[工程]", 3: "[执行]"}.get(node.layer, "")
    lines.append(f"{indent}{prefix}{status_icon} {node.name} {layer_label}")
    if node.description:
        lines.append(f"{indent}│   {node.description}")
    # Find outgoing edges and show dependency type
    edge_type_labels = {
        "sequential": "→", "conditional": "⇒", "iterative": "↻",
        "fallback": "⤾", "parallel": "∥",
    }
    for edge in graph.edges:
        if edge.source_id == node.id:
            child = graph.nodes.get(edge.target_id)
            if child and child.id not in visited:
                arrow = edge_type_labels.get(edge.dep_type.value, "→")
                if edge.dep_type.value == "fallback":
                    # Show fallback edge inline with label
                    lines.append(f"{indent}│   {arrow} [FALLBACK] {child.name}")
                _render_task_subtree(child, graph, depth + 1, lines, visited)


@dataclass(frozen=False)
class ParseResult:
    """Final output of the IntentParser — may contain a runnable graph or a clarification request."""
    intent: Intent
    task_graph: Optional[TaskGraph] = None
    is_actionable: bool = False
    # If not actionable, a clarification message to show the user
    clarification_message: Optional[str] = None
    # Suggested next actions for the user (buttons / quick replies)
    suggestions: List[str] = field(default_factory=list)
    # Trace log for debugging / observability
    trace_log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "task_graph": self.task_graph.to_dict() if self.task_graph else None,
            "is_actionable": self.is_actionable,
            "clarification_message": self.clarification_message,
            "suggestions": self.suggestions,
            "trace_log": self.trace_log,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParseResult":
        return cls(
            intent=Intent.from_dict(d["intent"]),
            task_graph=TaskGraph.from_dict(d["task_graph"]) if d.get("task_graph") else None,
            is_actionable=d.get("is_actionable", False),
            clarification_message=d.get("clarification_message"),
            suggestions=d.get("suggestions", []),
            trace_log=d.get("trace_log", []),
        )

    def __repr__(self) -> str:
        return (
            f"ParseResult(actionable={self.is_actionable}, "
            f"ambiguities={len(self.intent.ambiguities)}, "
            f"tasks={len(self.task_graph.nodes) if self.task_graph else 0})"
        )


class UserExpectation(Enum):
    """User expectation type as determined by PCR (Layer 0)."""
    TOOL = "tool"           # Direct execution mode
    ADVISOR = "advisor"     # Analytical / judgment mode
    COMPANION = "companion" # Exploratory / dialogue mode
    UNKNOWN = "unknown"     # Unclear, needs clarification


@dataclass(frozen=False)
class CognitiveProfile:
    """Layer-1 cognitive profile (derived from PCR CognitiveProfile_v1)."""
    metacognition: float = 0.0
    divergence: float = 0.0
    tracking_depth: float = 0.0
    stability: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metacognition": self.metacognition,
            "divergence": self.divergence,
            "tracking_depth": self.tracking_depth,
            "stability": self.stability,
            "confidence": self.confidence,
        }

    @classmethod
    def from_pcr_profile(cls, profile) -> "CognitiveProfile":
        """Build from PCR datacontract CognitiveProfile_v1."""
        return cls(
            metacognition=profile.metacognition,
            divergence=profile.divergence,
            tracking_depth=profile.tracking_depth,
            stability=profile.stability,
            confidence=profile.confidence,
        )


@dataclass(frozen=False)
class IntentContext:
    """
    PCR output translated into Layer-1 IntentContext.
    Used as the control signal injected into Layer 1 (IntentParser).
    """
    expectation: UserExpectation = UserExpectation.UNKNOWN
    noise_level: float = 0.0
    complexity_level: float = 0.0
    cognitive_profile: CognitiveProfile = field(default_factory=CognitiveProfile)
    # Derived strategies
    execution_mode: str = "BALANCED"          # CONSERVATIVE / BALANCED / AGGRESSIVE
    auto_resolve_threshold: float = 0.5
    max_ambiguities_before_ask: int = 3
    max_sub_intents: int = 5
    min_confidence_threshold: float = 0.4
    prompt_style: str = "BALANCED"            # BRIEF / EXPLANATORY / TUTORIAL
    # Trace
    noise_source: Optional[str] = None  # v2.2: noise source awareness (referential_dissonance, etc.)
    trace_log: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_pcr_output(cls, output) -> "IntentContext":
        """Factory: build IntentContext from PCR PCROutput_v1."""
        # Map expectation string → UserExpectation enum
        exp_map = {
            "TOOL": UserExpectation.TOOL,
            "ADVISOR": UserExpectation.ADVISOR,
            "COMPANION": UserExpectation.COMPANION,
            "UNKNOWN": UserExpectation.UNKNOWN,
        }
        expectation = exp_map.get(output.expectation, UserExpectation.UNKNOWN)

        # Build cognitive profile from PCR output
        cog = CognitiveProfile.from_pcr_profile(output.cognitive_profile)

        # Extract parser overrides (PCR may provide them as a dict)
        overrides = output.parser_config_overrides or {}

        return cls(
            expectation=expectation,
            noise_level=output.noise_level,
            complexity_level=output.complexity_level,
            cognitive_profile=cog,
            execution_mode=output.execution_mode,
            auto_resolve_threshold=overrides.get(
                "auto_resolve_threshold",
                0.7 if output.noise_level < 0.4 else 0.5 if output.noise_level < 0.7 else 0.3
            ),
            max_ambiguities_before_ask=overrides.get(
                "max_ambiguities_before_ask",
                5 if output.noise_level < 0.3 else 3 if output.noise_level < 0.7 else 1
            ),
            max_sub_intents=overrides.get(
                "max_sub_intents",
                10 if output.complexity_level > 0.8 else 5 if output.complexity_level > 0.5 else 3
            ),
            min_confidence_threshold=overrides.get(
                "min_confidence_threshold",
                0.6 if cog.confidence > 0.7 else 0.4 if cog.confidence > 0.3 else 0.25
            ),
            prompt_style=output.prompt_style,
            noise_source=overrides.get("noise_source"),  # v2.2: noise source awareness
            trace_log=list(output.trace_log or []),
            created_at=time.time(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expectation": self.expectation.value,
            "noise_level": self.noise_level,
            "complexity_level": self.complexity_level,
            "cognitive_profile": self.cognitive_profile.to_dict(),
            "execution_mode": self.execution_mode,
            "auto_resolve_threshold": self.auto_resolve_threshold,
            "max_ambiguities_before_ask": self.max_ambiguities_before_ask,
            "max_sub_intents": self.max_sub_intents,
            "min_confidence_threshold": self.min_confidence_threshold,
            "prompt_style": self.prompt_style,
            "noise_source": self.noise_source,
            "trace_log": self.trace_log,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class ParserConfig:
    """Runtime configuration for the IntentParser."""
    # Rule engine
    enable_rule_engine: bool = True
    enable_llm_fallback: bool = True
    # Entity extraction
    max_entities: int = 50
    min_confidence_threshold: float = 0.3
    # Ambiguity
    auto_resolve_ambiguities: bool = True       # Try heuristics before asking user
    auto_resolve_threshold: float = 0.7         # Confidence required for auto-resolve
    max_ambiguities_before_ask: int = 3         # If more than this, ask user immediately
    # Multi-intent
    max_sub_intents: int = 5
    split_on_conjunctions: bool = True            # "and then" / "first... then..."
    # Context
    context_window_size: int = 10               # How many previous turns to keep
    inherit_entities_from_context: bool = True
    # Performance
    enable_caching: bool = True
    cache_ttl_seconds: float = 300.0
    # Fast Path gating thresholds (P0-1: adaptive threshold regulation)
    fast_path_entity_threshold: float = 0.85
    fast_path_intent_threshold: float = 0.40
    # Debug
    verbose_logging: bool = False
    trace_every_step: bool = False
    # PCR-derived flags (dynamic tuning)
    enable_synonym_expansion: bool = False       # Activated when stability < 0.5
    enable_topic_inheritance: bool = False        # Activated when tracking_depth > 0.6
    prompt_style: str = "BALANCED"              # BRIEF / EXPLANATORY / TUTORIAL
    trace_log: List[str] = field(default_factory=list)  # v2.2: tuning trace log

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParserConfig":
        return cls(**d)

    @classmethod
    def from_intent_context(cls, ctx: IntentContext) -> "ParserConfig":
        """Dynamic config generation driven by PCR IntentContext."""
        config = cls(
            enable_rule_engine=True,
            enable_llm_fallback=True,
            max_entities=50,
            min_confidence_threshold=ctx.min_confidence_threshold,
            auto_resolve_ambiguities=ctx.auto_resolve_threshold > 0.5,
            auto_resolve_threshold=ctx.auto_resolve_threshold,
            max_ambiguities_before_ask=ctx.max_ambiguities_before_ask,
            max_sub_intents=ctx.max_sub_intents,
            split_on_conjunctions=True,
            context_window_size=10,
            inherit_entities_from_context=True,
            enable_caching=True,
            cache_ttl_seconds=300.0,
            verbose_logging=False,
            trace_every_step=True,
            enable_synonym_expansion=ctx.cognitive_profile.stability >= 0.7,  # v2.2: high stability → expand
            enable_topic_inheritance=ctx.cognitive_profile.tracking_depth > 0.6,
            prompt_style=ctx.prompt_style,
        )

        # v2.2: Noise-source-aware tuning (replaces simple "high noise → conservative" policy)
        # If noise is mainly from referential dissonance, enable synonym expansion
        # and deep context window instead of simply raising conservativeness.
        if (
            ctx.noise_level > 0.7
            and ctx.cognitive_profile.stability < 0.3
            and ctx.noise_source == "referential_dissonance"
        ):
            config.enable_synonym_expansion = True
            config.context_window_size = 20
            config.max_ambiguities_before_ask = 3
            config.trace_every_step = True
            if config.trace_log is None:
                config.trace_log = []
            config.trace_log.append(
                "[ParserConfig] High referential dissonance detected: "
                "enabling synonym expansion + deep context window (20)"
            )

        return config


# ═══════════════════════════════════════════════════════════════════════════════
# Context container for multi-turn reasoning
# ═══════════════════════════════════════════════════════════════════════════════

class ParseContext:
    """Mutable container that carries state across multiple parse calls in one session."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.history: List[Intent] = []          # Previous parsed intents
        self.resolved_entities: Dict[str, Any] = {}  # Entity values user confirmed
        self.pending_clarifications: List[Ambiguity] = []
        self.process_name: Optional[str] = None
        self.process_type: Optional[str] = None
        self.pid: Optional[int] = None
        self.metadata: Dict[str, Any] = {}
        self._entity_cache: Dict[str, List[Entity]] = {}

    def add_intent(self, intent: Intent) -> None:
        self.history.append(intent)
        # Extract confirmed entities
        for e in intent.entities:
            if e.confidence >= 0.8:
                self.resolved_entities[e.type.value] = e.value

    def get_last_intent(self) -> Optional[Intent]:
        return self.history[-1] if self.history else None

    def get_resolved_value(self, etype: EntityType) -> Any:
        return self.resolved_entities.get(etype.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "history_count": len(self.history),
            "resolved_entities": self.resolved_entities,
            "pending_clarifications": [a.to_dict() for a in self.pending_clarifications],
            "process_name": self.process_name,
            "process_type": self.process_type,
            "pid": self.pid,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"ParseContext(session={self.session_id}, intents={len(self.history)})"
