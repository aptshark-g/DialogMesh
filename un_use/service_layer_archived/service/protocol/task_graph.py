# -*- coding: utf-8 -*-
"""
service/protocol/task_graph.py
────────────────────────────────
TaskGraph 可视化协议（§13.3）。

定义任务 DAG 的节点、边、整体状态以及实时更新事件格式。
前端据此渲染进度图、状态色块、交互详情面板。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举定义（字符串值，便于 JSON 序列化）
# ═══════════════════════════════════════════════════════════════════════════════

class NodeStatus(str, Enum):
    """TaskNode 生命周期状态。"""

    PENDING = "PENDING"
    """等待依赖完成"""
    RUNNING = "RUNNING"
    """正在执行"""
    SUCCESS = "SUCCESS"
    """成功完成"""
    FAILED = "FAILED"
    """执行失败"""
    BLOCKED = "BLOCKED"
    """被上游失败阻塞"""
    SKIPPED = "SKIPPED"
    """条件不满足，跳过执行"""


class EdgeType(str, Enum):
    """任务 DAG 中的边类型。"""

    SEQUENTIAL = "SEQUENTIAL"
    """顺序依赖：A 完成后 B 才能开始"""
    CONDITIONAL = "CONDITIONAL"
    """条件依赖：满足条件才执行"""
    FALLBACK = "FALLBACK"
    """回退依赖：A 失败时走 B"""
    PARALLEL = "PARALLEL"
    """并行依赖：B 可与 A 并发（同步点）"""


class NodeType(str, Enum):
    """节点业务类型，影响前端图标与颜色。"""

    SCAN = "SCAN"
    """扫描操作（如内存扫描）"""
    READ = "READ"
    """读取操作"""
    WRITE = "WRITE"
    """写入操作（危险）"""
    ANALYZE = "ANALYZE"
    """分析操作（如反汇编、CFG）"""
    ASK_USER = "ASK_USER"
    """需要用户输入/确认"""
    EXPLAIN = "EXPLAIN"
    """解释/展示结果"""
    FALLBACK = "FALLBACK"
    """回退/替代方案节点"""


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容基类
# ═══════════════════════════════════════════════════════════════════════════════

class _CompatModel(BaseModel):
    """兼容基类：为 Pydantic v2 模型提供 V1 风格的 `.dict()` 方法。"""

    def dict(self, **kwargs) -> Dict[str, Any]:
        return self.model_dump(**kwargs)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Payload 模型
# ═══════════════════════════════════════════════════════════════════════════════

class TaskNodePayload(_CompatModel):
    """任务图节点负载，对应核心引擎 TaskNode 的可视化投影。"""

    node_id: str = Field(..., description="节点唯一标识")
    name: str = Field(..., description="人类可读标签，如'首次扫描'")
    description: str = Field("", description="详细说明，用于悬停提示或详情面板")
    status: NodeStatus = Field(NodeStatus.PENDING, description="当前生命周期状态")
    progress_pct: Optional[float] = Field(
        None,
        description="执行进度 0-100（仅 RUNNING 状态时有意义）",
        ge=0,
        le=100,
    )
    node_type: NodeType = Field(NodeType.SCAN, description="业务类型，决定前端图标/颜色")
    result_summary: Optional[str] = Field(
        None,
        description="结果摘要，如'找到 3 个地址'",
    )
    error_summary: Optional[str] = Field(
        None,
        description="错误摘要（FAILED 时展示，可展开详情）",
    )
    is_destructive: bool = Field(
        False,
        description="是否为危险操作（影响前端警示样式）",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="前端可扩展的元数据字典",
    )


class TaskEdgePayload(_CompatModel):
    """任务图边负载，定义节点间的依赖关系。"""

    source_id: str = Field(..., description="源节点 ID")
    target_id: str = Field(..., description="目标节点 ID")
    edge_type: EdgeType = Field(EdgeType.SEQUENTIAL, description="边类型")
    label: Optional[str] = Field(
        None,
        description="条件标签或说明文字，如 'count==1'",
    )
    active: bool = Field(
        True,
        description="是否激活（CONDITIONAL 中可能为 false）",
    )


class TaskGraphPayload(_CompatModel):
    """任务图可视化协议根对象，前端据此渲染完整 DAG。"""

    version: str = Field("1.0", description="协议版本号")
    task_graph_id: str = Field(..., description="任务图唯一标识")
    nodes: List[TaskNodePayload] = Field(
        default_factory=list,
        description="节点列表",
    )
    edges: List[TaskEdgePayload] = Field(
        default_factory=list,
        description="边列表",
    )
    overall_status: str = Field(
        "pending",
        description="全局状态：pending / running / completed / failed / partial",
    )
    progress_pct: Optional[float] = Field(
        None,
        description="整体进度 0-100（基于节点完成比例）",
        ge=0,
        le=100,
    )
    interactive: bool = Field(
        True,
        description="前端是否允许点击节点查看详情",
    )
    auto_layout: str = Field(
        "dagre",
        description="布局算法：dagre / circular / grid",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 实时更新事件
# ═══════════════════════════════════════════════════════════════════════════════

class NodeStatusUpdate(_CompatModel):
    """单个节点状态更新，用于增量推送。"""

    node_id: str = Field(..., description="节点唯一标识")
    status: NodeStatus = Field(..., description="新状态")
    progress_pct: Optional[float] = Field(
        None,
        description="执行进度 0-100（仅 RUNNING 时）",
        ge=0,
        le=100,
    )
    result_preview: Optional[str] = Field(
        None,
        description="结果预览，如'扫描找到 3 个地址'",
    )


class TaskGraphUpdateEvent(_CompatModel):
    """WebSocket 实时推送的任务图更新事件。"""

    update_type: str = Field(
        ...,
        description="更新类型：node_status_change / node_progress / node_result / edge_activate / all_done",
    )
    node_id: Optional[str] = Field(
        None,
        description="受影响的节点 ID（节点相关更新时必填）",
    )
    new_status: Optional[NodeStatus] = Field(
        None,
        description="节点新状态（node_status_change 时）",
    )
    progress_pct: Optional[float] = Field(
        None,
        description="节点进度（node_progress 时）",
        ge=0,
        le=100,
    )
    result_summary: Optional[str] = Field(
        None,
        description="节点结果摘要（node_result 时）",
    )
    error_summary: Optional[str] = Field(
        None,
        description="节点错误摘要（node_result 失败时）",
    )
    edge: Optional[TaskEdgePayload] = Field(
        None,
        description="边信息（edge_activate 时）",
    )
    overall_status: Optional[str] = Field(
        None,
        description="全局状态变更",
    )
    overall_progress_pct: Optional[float] = Field(
        None,
        description="整体进度变更",
        ge=0,
        le=100,
    )
