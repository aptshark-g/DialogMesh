# -*- coding: utf-8 -*-
"""
core/agent/frontend/taskgraph_viz.py
─────────────────────────────────────
TaskGraph 可视化协议（Layer 3，v2.4 新增）。

定义任务图在前端的展示格式（节点/边/状态/更新）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskNodePayload:
    """任务图节点可视化数据。"""
    node_id: str
    name: str                              # 人类可读标签
    description: str = ""                   # 详细说明
    status: str = "PENDING"               # PENDING | RUNNING | SUCCESS | FAILED | BLOCKED | SKIPPED
    progress_pct: Optional[float] = None   # 进度 0-100
    node_type: str = "generic"              # scan | read | write | analyze | ask_user | explain | fallback
    result_summary: Optional[str] = None   # 成功结果摘要
    error_summary: Optional[str] = None    # 失败错误摘要
    is_destructive: bool = False           # 是否危险操作
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 样式映射（前端可用）
    STATUS_COLORS = {
        "PENDING": {"border": "#9CA3AF", "fill": "#F3F4F6", "icon": "⏳"},
        "RUNNING": {"border": "#3B82F6", "fill": "#DBEAFE", "icon": "▶️"},
        "SUCCESS": {"border": "#10B981", "fill": "#D1FAE5", "icon": "✅"},
        "FAILED": {"border": "#EF4444", "fill": "#FEE2E2", "icon": "❌"},
        "BLOCKED": {"border": "#F59E0B", "fill": "#FEF3C7", "icon": "🔒"},
        "SKIPPED": {"border": "#9CA3AF", "fill": "#F3F4F6", "icon": "⏭️"},
    }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "node_type": self.node_type,
            "result_summary": self.result_summary,
            "error_summary": self.error_summary,
            "is_destructive": self.is_destructive,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskNodePayload:
        return cls(
            node_id=d["node_id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            status=d.get("status", "PENDING"),
            progress_pct=d.get("progress_pct"),
            node_type=d.get("node_type", "generic"),
            result_summary=d.get("result_summary"),
            error_summary=d.get("error_summary"),
            is_destructive=d.get("is_destructive", False),
            metadata=d.get("metadata", {}),
        )


@dataclass
class TaskEdgePayload:
    """任务图边可视化数据。"""
    source_id: str
    target_id: str
    edge_type: str = "sequential"           # sequential | conditional | fallback | parallel
    label: Optional[str] = None              # 条件标签
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "label": self.label,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskEdgePayload:
        return cls(
            source_id=d["source_id"],
            target_id=d["target_id"],
            edge_type=d.get("edge_type", "sequential"),
            label=d.get("label"),
            active=d.get("active", True),
        )


@dataclass
class TaskGraphPayload:
    """任务图可视化协议。"""
    version: str = "1.0"
    task_graph_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    nodes: List[TaskNodePayload] = field(default_factory=list)
    edges: List[TaskEdgePayload] = field(default_factory=list)
    overall_status: str = "pending"         # pending | running | completed | failed | partial
    progress_pct: Optional[float] = None
    interactive: bool = True
    auto_layout: str = "dagre"                # dagre | circular | grid

    def __post_init__(self):
        """构造后自动计算整体状态。"""
        self._recalculate_overall_status()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "task_graph_id": self.task_graph_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "overall_status": self.overall_status,
            "progress_pct": self.progress_pct,
            "interactive": self.interactive,
            "auto_layout": self.auto_layout,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskGraphPayload:
        return cls(
            version=d.get("version", "1.0"),
            task_graph_id=d.get("task_graph_id", str(uuid.uuid4())[:12]),
            nodes=[TaskNodePayload.from_dict(n) for n in d.get("nodes", [])],
            edges=[TaskEdgePayload.from_dict(e) for e in d.get("edges", [])],
            overall_status=d.get("overall_status", "pending"),
            progress_pct=d.get("progress_pct"),
            interactive=d.get("interactive", True),
            auto_layout=d.get("auto_layout", "dagre"),
        )

    def get_node(self, node_id: str) -> Optional[TaskNodePayload]:
        """按 ID 查找节点。"""
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def update_node_status(self, node_id: str, status: str,
                          progress_pct: Optional[float] = None,
                          result_summary: Optional[str] = None,
                          error_summary: Optional[str] = None) -> bool:
        """更新节点状态。"""
        node = self.get_node(node_id)
        if node is None:
            return False
        node.status = status
        if progress_pct is not None:
            node.progress_pct = progress_pct
        if result_summary is not None:
            node.result_summary = result_summary
        if error_summary is not None:
            node.error_summary = error_summary
        self._recalculate_overall_status()
        return True

    def _recalculate_overall_status(self) -> None:
        """重新计算整体状态。"""
        if not self.nodes:
            self.overall_status = "pending"
            return
        statuses = [n.status for n in self.nodes]
        if any(s == "FAILED" for s in statuses):
            self.overall_status = "failed"
        elif all(s in ("SUCCESS", "SKIPPED") for s in statuses):
            self.overall_status = "completed"
        elif any(s == "RUNNING" for s in statuses):
            self.overall_status = "running"
        else:
            self.overall_status = "partial"

        # 计算总进度
        total = len(self.nodes)
        completed = sum(1 for s in statuses if s in ("SUCCESS", "SKIPPED"))
        self.progress_pct = (completed / total) * 100 if total > 0 else 0.0

    @classmethod
    def from_task_graph(cls, task_graph) -> TaskGraphPayload:
        """从内部 TaskGraph 对象生成可视化负载。"""
        # 适配：如果 task_graph 有 nodes 和 edges 属性
        nodes = []
        edges = []
        node_id_map = {}

        if hasattr(task_graph, "nodes") and task_graph.nodes:
            for i, (nid, node) in enumerate(task_graph.nodes.items()):
                node_id_map[i] = nid
                nodes.append(TaskNodePayload(
                    node_id=nid,
                    name=node.name if hasattr(node, "name") else nid,
                    description=node.description if hasattr(node, "description") else "",
                    status=node.status if hasattr(node, "status") else "PENDING",
                    node_type=node.type if hasattr(node, "type") else "generic",
                    is_destructive=node.is_destructive if hasattr(node, "is_destructive") else False,
                    result_summary=node.result_summary if hasattr(node, "result_summary") else None,
                    error_summary=node.error_summary if hasattr(node, "error_summary") else None,
                ))

        if hasattr(task_graph, "edges") and task_graph.edges:
            for edge in task_graph.edges:
                edges.append(TaskEdgePayload(
                    source_id=edge.source if hasattr(edge, "source") else str(edge[0]),
                    target_id=edge.target if hasattr(edge, "target") else str(edge[1]),
                    edge_type=edge.type if hasattr(edge, "type") else "sequential",
                    label=edge.label if hasattr(edge, "label") else None,
                ))

        return cls(
            task_graph_id=getattr(task_graph, "id", str(uuid.uuid4())[:12]),
            nodes=nodes,
            edges=edges,
        )


@dataclass
class TaskGraphUpdateEvent:
    """WebSocket 实时推送的任务图更新。"""
    task_graph_id: str
    update_type: str                          # node_status_change | node_progress | node_result | edge_activate | all_done
    node_id: Optional[str] = None
    new_status: Optional[str] = None
    progress_pct: Optional[float] = None
    result_summary: Optional[str] = None
    error_summary: Optional[str] = None
    edge: Optional[TaskEdgePayload] = None
    overall_status: Optional[str] = None
    overall_progress_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "task_graph_id": self.task_graph_id,
            "update_type": self.update_type,
        }
        if self.node_id is not None:
            result["node_id"] = self.node_id
        if self.new_status is not None:
            result["new_status"] = self.new_status
        if self.progress_pct is not None:
            result["progress_pct"] = self.progress_pct
        if self.result_summary is not None:
            result["result_summary"] = self.result_summary
        if self.error_summary is not None:
            result["error_summary"] = self.error_summary
        if self.edge is not None:
            result["edge"] = self.edge.to_dict()
        if self.overall_status is not None:
            result["overall_status"] = self.overall_status
        if self.overall_progress_pct is not None:
            result["overall_progress_pct"] = self.overall_progress_pct
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskGraphUpdateEvent:
        return cls(
            task_graph_id=d["task_graph_id"],
            update_type=d["update_type"],
            node_id=d.get("node_id"),
            new_status=d.get("new_status"),
            progress_pct=d.get("progress_pct"),
            result_summary=d.get("result_summary"),
            error_summary=d.get("error_summary"),
            edge=TaskEdgePayload.from_dict(d["edge"]) if "edge" in d else None,
            overall_status=d.get("overall_status"),
            overall_progress_pct=d.get("overall_progress_pct"),
        )
