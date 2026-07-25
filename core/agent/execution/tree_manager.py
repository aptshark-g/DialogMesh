"""AgentTreeManager — 7 trees inheriting DiscourseBlockTree.

DiscourseTree    — conversation content
ExecutionTree   — task decomposition, sub-agent spawning, tool execution
ConstraintTree  — engineering rules, file/command constraints
AssociationTree — entity relations, cross-tree mapping queries
BehaviorTree    — user preferences, tool habits, correction history
MetaTree        — metacognition arbitration, audit trail, synthesis
ProfileTree     — OCEAN evolution, inertia tracking

All trees share: node format, branching, progressive summary, archive.
Communication: query-driven (Q-style pull), no push notifications.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


# ═══ Base: AgentTreeBlock — extends DiscourseBlock ═══

class NodeStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    ARCHIVED = "archived"
    REOPENED = "reopened"


@dataclass
class AgentTreeNode:
    """Unified tree node — base for all 7 trees."""
    node_id: str
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    archived_at: Optional[float] = None

    # Domain-agnostic fields — each tree fills what it needs
    content: Dict[str, Any] = field(default_factory=dict)
    pointers: List[str] = field(default_factory=list)  # → other tree nodes
    queries: List[str] = field(default_factory=list)    # → FederatedIndex
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 0  # Increments on each modification

    def archive(self):
        self.status = NodeStatus.ARCHIVED
        self.archived_at = time.time()

    def reopen(self):
        self.status = NodeStatus.REOPENED
        self.version += 1


@dataclass
class TreeStats:
    tree_name: str
    total_nodes: int = 0
    active: int = 0
    completed: int = 0
    archived: int = 0
    failed: int = 0


class AgentTree:
    """Base class for all 7 trees."""

    def __init__(self, name: str):
        self.name = name
        self._nodes: Dict[str, AgentTreeNode] = {}
        self._roots: List[str] = []  # Node IDs without parents

    def create_node(self, node_id: str = None, parent_id: str = None,
                    content: dict = None, pointers: list = None,
                    queries: list = None, metadata: dict = None) -> AgentTreeNode:
        """Create a node under parent (or as root)."""
        nid = node_id or f"{self.name}_{len(self._nodes)}_{int(time.time()*1000)}"
        node = AgentTreeNode(
            node_id=nid, parent_id=parent_id,
            content=content or {}, pointers=pointers or [],
            queries=queries or [], metadata=metadata or {},
        )
        self._nodes[nid] = node
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].children.append(nid)
        else:
            self._roots.append(nid)
        return node

    def get_node(self, node_id: str) -> Optional[AgentTreeNode]:
        return self._nodes.get(node_id)

    def query_nodes(self, content_filter: callable = None) -> List[AgentTreeNode]:
        """Query nodes matching filter. Called by other trees."""
        if content_filter is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if content_filter(n)]

    def archive_completed(self, ticks_threshold: int = 5):
        """Archive nodes completed more than N ticks ago."""
        now = time.time()
        for n in self._nodes.values():
            if n.status == NodeStatus.COMPLETED and n.completed_at:
                if now - n.completed_at > ticks_threshold * 1.0:
                    n.archive()

    def get_stats(self) -> TreeStats:
        stats = TreeStats(tree_name=self.name, total_nodes=len(self._nodes))
        for n in self._nodes.values():
            if n.status == NodeStatus.ACTIVE: stats.active += 1
            elif n.status == NodeStatus.COMPLETED: stats.completed += 1
            elif n.status == NodeStatus.ARCHIVED: stats.archived += 1
            elif n.status == NodeStatus.FAILED: stats.failed += 1
        return stats


# ═══ 7 Concrete Trees ═══

class DiscourseTree(AgentTree):
    """Stores conversation turns, LLM responses, user messages."""
    def __init__(self): super().__init__("discourse")

    def record_turn(self, user_text: str, response_text: str, metadata: dict = None):
        return self.create_node(
            content={"user": user_text, "response": response_text},
            metadata=metadata or {},
        )


class ExecutionTree(AgentTree):
    """Task decomposition, sub-agent spawning, tool execution tracking."""
    def __init__(self): super().__init__("execution")

    def create_task(self, plan: dict, parent_id: str = None) -> AgentTreeNode:
        return self.create_node(
            parent_id=parent_id,
            content={
                "task_type": "plan",
                "steps": plan.get("steps", []),
                "confidence": plan.get("confidence", 0.0),
                "strategy": plan.get("strategy", "RULE_BASED"),
            },
            pointers=plan.get("pointers", []),
            queries=plan.get("queries", []),
        )

    def spawn_sub_agent(self, parent_id: str, task: str, context_size: int,
                        pointers: list = None, queries: list = None) -> AgentTreeNode:
        return self.create_node(
            parent_id=parent_id,
            content={"task_type": "sub_agent", "task": task,
                     "context_size": context_size},
            pointers=pointers or [], queries=queries or [],
        )

    def complete_node(self, node_id: str, result: dict):
        node = self.get_node(node_id)
        if node:
            node.status = NodeStatus.COMPLETED
            node.completed_at = time.time()
            node.content["result"] = result


class ConstraintTree(AgentTree):
    """Engineering rules, file/command constraints, security policies."""
    def __init__(self): super().__init__("constraint")

    def add_rule(self, rule_id: str, domain: str, pattern: str,
                 action: str = "block", priority: int = 5):
        return self.create_node(
            node_id=rule_id,
            content={"domain": domain, "pattern": pattern,
                     "action": action, "priority": priority},
        )

    def check(self, tool: str, params: dict) -> List[dict]:
        """Check if a tool call violates any active constraint."""
        violations = []
        for n in self.query_nodes(
            lambda n: n.status == NodeStatus.ACTIVE
        ):
            pattern = n.content.get("pattern", "")
            domain = n.content.get("domain", "")
            # File path check
            if domain == "file" and "path" in params:
                if pattern in params["path"]:
                    violations.append({
                        "rule": n.node_id, "pattern": pattern,
                        "action": n.content.get("action", "block"),
                        "priority": n.content.get("priority", 5),
                    })
            # Command check
            if domain == "command" and "command" in params:
                if pattern in params["command"]:
                    violations.append({
                        "rule": n.node_id, "pattern": pattern,
                        "action": n.content.get("action", "block"),
                        "priority": n.content.get("priority", 5),
                    })
        return violations


class AssociationTree(AgentTree):
    """Entity relations, cross-tree mapping via RelationSubstrate."""
    def __init__(self): super().__init__("association")

    def map_nodes(self, source_tree: str, source_id: str,
                  target_tree: str, target_id: str,
                  relation_type: str = "constraint_mapping"):
        """Create cross-tree mapping between two nodes."""
        return self.create_node(
            content={
                "source_tree": source_tree, "source_id": source_id,
                "target_tree": target_tree, "target_id": target_id,
                "relation": relation_type,
            },
            pointers=[target_id],
        )

    def find_mappings(self, tree_name: str, node_id: str) -> List[AgentTreeNode]:
        return self.query_nodes(
            lambda n:
                (n.content.get("source_tree") == tree_name and
                 n.content.get("source_id") == node_id) or
                (n.content.get("target_tree") == tree_name and
                 n.content.get("target_id") == node_id)
        )


class BehaviorTree(AgentTree):
    """User preferences, tool habits, PlanGate learning, correction history."""
    def __init__(self): super().__init__("behavior")

    def record_pattern(self, tool: str, approved: bool,
                       risk: str = "low", modified: bool = False):
        return self.create_node(
            content={"tool": tool, "approved": approved,
                     "risk": risk, "modified": modified},
        )

    def get_approval_rate(self, tool: str) -> float:
        """Calculate approval rate for a specific tool."""
        nodes = self.query_nodes(lambda n: n.content.get("tool") == tool)
        if not nodes:
            return 0.5  # Neutral
        approved = sum(1 for n in nodes if n.content.get("approved"))
        return approved / len(nodes)


class MetaTree(AgentTree):
    """Metacognition arbitration, audit trail, synthesis."""
    def __init__(self): super().__init__("meta")

    def record_decision(self, decision_type: str, inputs: dict,
                        verdict: str, reasoning: str):
        return self.create_node(
            content={"type": decision_type, "inputs": inputs,
                     "verdict": verdict, "reasoning": reasoning},
        )

    def assess_quality(self, sub_agent_results: List[dict]) -> dict:
        """Assess sub-agent output quality → decision: archive/retry/replan."""
        all_success = all(r.get("status") == "success" for r in sub_agent_results)
        if all_success:
            return {"action": "archive", "confidence": 1.0}
        failures = [r for r in sub_agent_results if r.get("status") != "success"]
        if len(failures) <= 1:
            return {"action": "retry", "targets": [f["task_id"] for f in failures],
                    "confidence": 0.6}
        return {"action": "replan", "reason": f"{len(failures)} failures",
                "confidence": 0.3}


class ProfileTree(AgentTree):
    """OCEAN evolution, inertia tracking, user profile changes."""
    def __init__(self): super().__init__("profile")

    def record_profile_update(self, dimension: str, old_value: float,
                              new_value: float, trigger: str):
        return self.create_node(
            content={"dimension": dimension, "old": old_value,
                     "new": new_value, "trigger": trigger},
        )


# ═══ Agent Tree Manager ═══

class AgentTreeManager:
    """Manages all 7 trees — creates, queries, archives, and coordinates.

    Usage:
        atm = AgentTreeManager()
        exe = atm.execution
        node = exe.create_task(plan)
        mapping = atm.association.map_nodes("execution", node.node_id,
                                            "constraint", "rule_1")
    """

    def __init__(self):
        self.discourse = DiscourseTree()
        self.execution = ExecutionTree()
        self.constraint = ConstraintTree()
        self.association = AssociationTree()
        self.behavior = BehaviorTree()
        self.meta = MetaTree()
        self.profile = ProfileTree()

        self._all_trees: List[AgentTree] = [
            self.discourse, self.execution, self.constraint,
            self.association, self.behavior, self.meta, self.profile,
        ]

    def global_query(self, query_text: str, max_results: int = 10) -> List[AgentTreeNode]:
        """Search ALL trees for matching content. Q-style pull."""
        results = []
        query_lower = query_text.lower()
        for tree in self._all_trees:
            for node in tree.query_nodes():
                content_str = str(node.content).lower()
                if query_lower in content_str:
                    results.append(node)
                if len(results) >= max_results:
                    return results
        return results

    def get_node_by_pointer(self, pointer: str) -> Optional[AgentTreeNode]:
        """Resolve a pointer → specific node in any tree."""
        for tree in self._all_trees:
            node = tree.get_node(pointer)
            if node:
                return node
        return None

    def archive_all_completed(self, ticks: int = 5):
        for tree in self._all_trees:
            tree.archive_completed(ticks)

    def get_all_stats(self) -> List[TreeStats]:
        return [t.get_stats() for t in self._all_trees]
