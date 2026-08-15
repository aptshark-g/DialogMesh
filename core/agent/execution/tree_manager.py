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

    # ── 序列化（2026-08-15: 七树持久化, Warm 层落盘）──

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "children": list(self.children),
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "archived_at": self.archived_at,
            "content": self.content,
            "pointers": list(self.pointers),
            "queries": list(self.queries),
            "metadata": self.metadata,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTreeNode":
        node = cls(
            node_id=data.get("node_id", ""),
            parent_id=data.get("parent_id"),
            children=list(data.get("children", [])),
            status=NodeStatus(data.get("status", "active")),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
            archived_at=data.get("archived_at"),
            content=dict(data.get("content", {})),
            pointers=list(data.get("pointers", [])),
            queries=list(data.get("queries", [])),
            metadata=dict(data.get("metadata", {})),
            version=int(data.get("version", 0)),
        )
        return node


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
        return stats

    # ── 序列化（2026-08-15: 七树持久化）──

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "roots": list(self._roots),
            "nodes": [n.to_dict() for n in self._nodes.values()],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """原地重建树（保持实例引用, 不换对象）。"""
        self._nodes.clear()
        self._roots.clear()
        self.name = data.get("name", self.name)
        for nd in data.get("nodes", []):
            node = AgentTreeNode.from_dict(nd)
            self._nodes[node.node_id] = node
        self._roots = list(data.get("roots", []))

    def node_count(self) -> int:
        return len(self._nodes)

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

    # ── 消费端只读 API（2026-08-13, EXEC_TREE_CONSUMPTION 吸收落地）──
    # 设计意图: 行为链读树学模式 / 元认知读树发现偏差（淘宝 PES 全链路
    # 可回放的消费侧）。纪律（吸收自 Grok/Hermes）:
    #   - 只读观察者: 查询不改树, 消费回调不控执行循环
    #   - 结果词汇化: success/error/cancelled 稳定枚举（对齐 ToolOutcome）

    def get_tasks(self, status: Optional[NodeStatus] = None) -> List[AgentTreeNode]:
        """全部任务（plan）节点, 可按状态过滤。"""
        return [n for n in self._nodes.values()
                if n.content.get("task_type") == "plan"
                and (status is None or n.status == status)]

    def get_subagents(self, task_id: str) -> List[AgentTreeNode]:
        """某任务的全部步骤（sub_agent 子节点, 按创建序）。"""
        task = self._nodes.get(task_id)
        if task is None:
            return []
        out = []

        def _walk(nid: str):
            node = self._nodes.get(nid)
            if node is None:
                return
            for cid in node.children:
                child = self._nodes.get(cid)
                if child is not None:
                    if child.content.get("task_type") == "sub_agent":
                        out.append(child)
                    _walk(cid)

        _walk(task_id)
        return out

    def tree_patterns(self) -> Dict[str, Any]:
        """消费端模式提取（元认知偏差信号 + 行为链学习原料）。

        输出（全部确定性, 只读）:
          tasks / completed / failed / stuck_active / text_only
          tool_outcomes: {tool: {success, error, cancelled}}（词汇化结果）
          failing_tools: 失败 >=2 且 >= 成功的工具（抖动信号）
          doom_loops: 同工具+同输入连续 3 次（吸收 O3, 输入不变才
            是死循环——不是失败次数）
          consecutive_failures: 每个任务内连续失败步骤数
          tool_sequences: 每任务工具序列（行为链学习原料）
          avg_steps_per_task / max_steps_per_task（深度偏好信号, W7 雏形）
        """
        tasks = self.get_tasks()
        tool_outcomes: Dict[str, Dict[str, int]] = {}
        failing_tools: List[str] = []
        doom_loops: List[Dict[str, Any]] = []
        tool_sequences: List[List[str]] = []
        consecutive_failures: List[int] = []
        text_only_tasks = 0
        stuck_active = 0
        completed = 0
        now = time.time()
        for t in tasks:
            if t.status == NodeStatus.COMPLETED:
                completed += 1
            # 卡 ACTIVE: 创建超过 5 分钟仍未完成（无步骤也计入 —
            # 2026-08-14 修复: 旧代码在 "if not steps: continue"
            # 之前漏检了无步骤的卡死任务）
            if t.status == NodeStatus.ACTIVE and (
                    t.created_at and now - t.created_at > 300):
                stuck_active += 1
            steps = self.get_subagents(t.node_id)
            if not steps:
                if t.status == NodeStatus.COMPLETED:
                    text_only_tasks += 1
                continue
            seq: List[str] = []
            run_fail = 0
            max_fail = 0
            last_key: Optional[tuple] = None
            same_run = 0
            for s in steps:
                outcome = self._outcome_of(s)
                tool_name = self._tool_name_of(s)
                if tool_name:
                    seq.append(tool_name)
                    bucket = tool_outcomes.setdefault(
                        tool_name, {"success": 0, "error": 0, "cancelled": 0})
                    bucket[outcome] = bucket.get(outcome, 0) + 1
                    # doom loop（吸收 O3）: 同工具+同输入连续 3 次
                    inp = (s.content.get("input") or "") or ""
                    key = (tool_name, inp)
                    if key == last_key:
                        same_run += 1
                        if same_run >= 3:
                            doom_loops.append({
                                "task": t.node_id, "tool": tool_name,
                                "input": inp[:120], "count": same_run + 1,
                            })
                    else:
                        last_key, same_run = key, 1
                if outcome == "error":
                    run_fail += 1
                    max_fail = max(max_fail, run_fail)
                else:
                    run_fail = 0
            consecutive_failures.append(max_fail)
            if seq:
                tool_sequences.append(seq)
        for tool, bucket in tool_outcomes.items():
            if bucket.get("error", 0) >= 2 and bucket["error"] >= bucket.get(
                    "success", 0):
                failing_tools.append(tool)
        steps_lens = [len(self.get_subagents(t.node_id)) for t in tasks]
        return {
            "tasks": len(tasks),
            "completed": completed,
            "failed": sum(1 for t in tasks
                          if t.status == NodeStatus.FAILED),
            "stuck_active": stuck_active,
            "text_only": text_only_tasks,
            "tool_outcomes": tool_outcomes,
            "failing_tools": sorted(failing_tools),
            "doom_loops": doom_loops,
            "consecutive_failures": consecutive_failures,
            "tool_sequences": tool_sequences,
            "avg_steps_per_task": round(
                sum(steps_lens) / max(1, len(steps_lens)), 2),
            "max_steps_per_task": max(steps_lens) if steps_lens else 0,
        }

    @staticmethod
    def _outcome_of(node: AgentTreeNode) -> str:
        """结果词汇化（对齐 Grok ToolOutcome 子集）: success/error/cancelled。

        2026-08-14（阶段 0）: 优先读写侧词汇化 content["outcome"]
        （TaskRunner._step_hook 落树）; 回退 content.result 的
        status 映射（TaskResult: ok→success, aborted→cancelled,
        其余→error）。"""
        written = node.content.get("outcome")
        if written in ("success", "error", "cancelled"):
            return written
        result = (node.content.get("result") or {})
        if isinstance(result, dict):
            st = str(result.get("status", ""))
            if st == "ok":
                return "success"
            if st in ("aborted", "cancelled"):
                return "cancelled"
            if st in ("failed", "error", "rejected", "replan",
                      "ask_user", "timeout"):
                return "error"
        if node.status in (NodeStatus.FAILED, NodeStatus.BLOCKED):
            return "error"
        return "success"

    @staticmethod
    def _tool_name_of(node: AgentTreeNode) -> str:
        task = (node.content.get("task") or "") or ""
        name = (task or "").split(":", 1)[0].strip()
        return name if len(name) <= 32 else name[:32]


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

    # ── 持久化（2026-08-15: Warm 层落盘, A17 记录不删）──

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trees": {
                tree.name: tree.to_dict() for tree in self._all_trees
            },
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """原地恢复七树（保持实例引用, 不换对象）。"""
        trees = data.get("trees") or {}
        by_name = {tree.name: tree for tree in self._all_trees}
        for name, payload in trees.items():
            tree = by_name.get(name)
            if tree is not None and isinstance(payload, dict):
                tree.from_dict(payload)

    def save(self, path: str) -> bool:
        """原子写盘（tmp + replace, 与 discourse 落盘同模式）。"""
        import json as _json
        import os as _os
        try:
            _os.makedirs(_os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(self.to_dict(), f, ensure_ascii=False)
            _os.replace(tmp, path)
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, path: str) -> Optional["AgentTreeManager"]:
        """从盘恢复（不存在/损坏 → None, 调用方回退新建）。"""
        import json as _json
        import os as _os
        if not _os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            mgr = cls()
            mgr.from_dict(data)
            return mgr
        except Exception:
            return None
