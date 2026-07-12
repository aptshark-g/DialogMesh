# -*- coding: utf-8 -*-
"""
core/agent/v3_0/data_models.py
─────────────────────────────
DialogMesh Agent v3.0 核心数据模型。

用途：
- 定义 v3.0 版本化的所有 Pydantic 数据模型，面向服务层与异步架构。
- 提供与 v2.x 数据模型的兼容转换层（import 引用）。
- 支持 FastAPI 的 Pydantic Schema 生成、JSON 序列化与异步验证。
- 所有枚举复用 ``core.agent.models`` 中的工业级定义，确保版本兼容。

设计原则：
- 全面使用 Pydantic v2 BaseModel，利用其严格的类型校验与序列化能力。
- 所有模型支持 ``model_dump_json()`` 与 ``model_validate_json()`` 的异步包装。
- 核心枚举（IntentCategory、TaskStatus 等）不重复定义，直接从 v2.x 导入，
  避免版本漂移。
- 引入 v3.0 特有的服务层模型（SessionState_v3、WebSocketEvent 等），
  为 FastAPI / WebSocket 提供原生 Schema 支持。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import (
    Any, Dict, Generic, List, Optional, Set, Tuple, TypeVar, Union,
)

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 引用现有 v2.x 核心枚举（确保版本兼容，不重复定义）
#
# 策略：优先尝试常规 import；若 core.agent 包初始化因 v2.x 配置模块异常而失败，
# 则使用 importlib 直接从文件加载 models.py，避免级联错误。这是 v3.0 的
# 防御性设计，确保数据模型本身在任何情况下都可独立加载。
# ═══════════════════════════════════════════════════════════════════════════════
_import_fallback_needed = False
try:
    from core.agent.v3_common.models import (
        AmbiguityType,
        ConfidenceLevel,
        DependencyType,
        EntityType,
        IntentCategory,
        TaskStatus,
        UserExpectation,
    )
except Exception as _import_err:
    logger.warning(
        f"core.agent.models 常规导入失败（{_import_err.__class__.__name__}），"
        "使用 importlib 直接从文件加载..."
    )
    _import_fallback_needed = True

if _import_fallback_needed:
    import importlib.util
    import sys
    from pathlib import Path

    _models_path = Path(__file__).resolve().parents[1] / "models.py"
    _spec = importlib.util.spec_from_file_location("core.agent.models", _models_path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"无法加载 core.agent.models 文件: {_models_path}")
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["core.agent.models"] = _mod
    _spec.loader.exec_module(_mod)

    AmbiguityType = _mod.AmbiguityType
    ConfidenceLevel = _mod.ConfidenceLevel
    DependencyType = _mod.DependencyType
    EntityType = _mod.EntityType
    IntentCategory = _mod.IntentCategory
    TaskStatus = _mod.TaskStatus
    UserExpectation = _mod.UserExpectation

    del _models_path, _spec, _mod, _import_fallback_needed

# ═══════════════════════════════════════════════════════════════════════════════
# v3.0 新增枚举
# ═══════════════════════════════════════════════════════════════════════════════

class EventType(str, Enum):
    """WebSocket 事件类型——所有前端推送事件的标准分类。"""
    MESSAGE = "message"
    CLARIFICATION = "clarification"
    TASK_UPDATE = "task_update"
    TASK_GRAPH = "task_graph"
    SYSTEM_STATUS = "system_status"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    SESSION_CREATED = "session_created"
    SESSION_CLOSED = "session_closed"


class MessageRole(str, Enum):
    """消息角色——用于区分会话参与方。"""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"


class ComponentType(str, Enum):
    """系统组件类型——健康检查与遥测的组件标识。"""
    PARSER = "parser"
    PCR = "pcr"
    COMPILER = "compiler"
    ORCHESTRATOR = "orchestrator"
    PERSISTENCE = "persistence"
    WEBSOCKET = "websocket"
    LLM_PROVIDER = "llm_provider"


# ═══════════════════════════════════════════════════════════════════════════════
# 基础模型
# ═══════════════════════════════════════════════════════════════════════════════

class TimestampedModel(BaseModel):
    """带创建时间戳的基础模型——所有时间敏感模型的基类。"""
    model_config = ConfigDict(
        extra="allow",
        json_encoders={datetime: lambda v: v.isoformat()},
        validate_assignment=True,
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    async def async_validate(self) -> None:
        """异步验证钩子（子类可覆盖）。"""
        await asyncio.sleep(0)  # 让出事件循环，避免阻塞


class VersionedModel(BaseModel):
    """带版本标记的基础模型——确保序列化数据的前向兼容。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    schema_version: str = Field(default="3.0.0", alias="schemaVersion")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 核心数据模型（Pydantic v2）
# ═══════════════════════════════════════════════════════════════════════════════

class Entity_v3(BaseModel):
    """v3.0 实体模型——从用户输入中提取的带类型值。

    与 v2.x ``Entity`` 的语义完全等价，但使用 Pydantic v2 进行严格校验。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    type: EntityType
    value: Any
    raw_text: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    start_pos: int = -1
    end_pos: int = -1
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        """将置信度裁剪到 [0.0, 1.0] 范围；异常输入回退到 1.0。"""
        try:
            return float(max(0.0, min(1.0, v)))
        except Exception as exc:
            logger.warning(f"Confidence validation error ({exc}), defaulting to 1.0")
            return 1.0


class Ambiguity_v3(BaseModel):
    """v3.0 歧义检测模型——解析过程中发现的需要澄清的歧义。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    type: AmbiguityType
    description: str
    affected_entities: List[EntityType] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    auto_resolvable: bool = False
    default_choice: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Intent_v3(BaseModel):
    """v3.0 意图模型——解析并分类后的用户意图，包含所有提取实体。

    支持子意图嵌套（多意图检测）与歧义标记，可序列化为 FastAPI Schema。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: IntentCategory = IntentCategory.UNKNOWN
    raw_input: str = ""
    normalized_input: str = ""
    entities: List[Entity_v3] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sub_intents: List[Intent_v3] = Field(default_factory=list)
    requires_process: bool = True
    is_destructive: bool = False
    is_reversible: bool = False
    ambiguities: List[Ambiguity_v3] = Field(default_factory=list)
    temporal_constraint: Optional[str] = None
    scope_constraint: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def is_ambiguous(self) -> bool:
        """判断意图是否存在歧义。"""
        return len(self.ambiguities) > 0 or len(self.sub_intents) > 1

    def get_entities(self, etype: EntityType) -> List[Entity_v3]:
        """按类型过滤实体。"""
        return [e for e in self.entities if e.type == etype]

    def get_entity(self, etype: EntityType) -> Optional[Entity_v3]:
        """获取第一个匹配类型的实体。"""
        for e in self.entities:
            if e.type == etype:
                return e
        return None

    def has_entity(self, etype: EntityType) -> bool:
        """检查是否存在指定类型的实体。"""
        return any(e.type == etype for e in self.entities)

    async def async_validate(self) -> None:
        """异步验证：递归确保子意图的置信度在合法范围内。"""
        try:
            await asyncio.sleep(0)
            for sub in self.sub_intents:
                await sub.async_validate()
        except Exception as exc:
            logger.error(f"Intent_v3 async_validate failed: {exc}")
            raise


class TaskNode_v3(BaseModel):
    """v3.0 任务节点——任务 DAG 中的单个节点，代表一个概念步骤。

    layer 字段约定：
    - 1 = 概念层（Concept）
    - 2 = 工程层（Engineering）
    - 3 = 执行层（Execution）
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    id: str = Field(default_factory=lambda: f"T-{str(uuid.uuid4())[:8]}")
    name: str = ""
    description: str = ""
    intent_id: Optional[str] = None
    layer: int = Field(default=1, ge=1, le=3)
    goal: str = ""
    strategy: str = ""
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    alternative_strategies: List[str] = Field(default_factory=list)
    fallback_nodes: List[str] = Field(default_factory=list)
    estimated_cost: float = Field(default=1.0, ge=0.0)
    priority: int = 0
    tags: Set[str] = Field(default_factory=set)
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def mark_running(self) -> None:
        """标记为运行中。"""
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_success(self, result: Dict[str, Any]) -> None:
        """标记为成功。"""
        self.status = TaskStatus.SUCCESS
        self.result = result
        self.finished_at = time.time()
        self.error = None

    def mark_failed(self, error: str) -> None:
        """标记为失败。"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = time.time()

    def mark_blocked(self) -> None:
        """标记为阻塞。"""
        self.status = TaskStatus.BLOCKED

    def can_retry(self) -> bool:
        """检查是否还可以重试。"""
        return self.retry_count < self.max_retries

    def to_summary(self) -> Dict[str, Any]:
        """生成节点摘要，用于前端渲染与日志。"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "layer": self.layer,
            "retry_count": self.retry_count,
        }


class TaskEdge_v3(BaseModel):
    """v3.0 任务边——任务 DAG 中的有向边。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    source_id: str
    target_id: str
    dep_type: DependencyType = DependencyType.SEQUENTIAL
    condition: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskGraph_v3(BaseModel):
    """v3.0 任务图——带依赖追踪与拓扑调度的 DAG。

    与 v2.x ``TaskGraph`` 的语义等价，但使用 Pydantic v2 的列表/字典存储，
    更便于 FastAPI 自动序列化为 JSON。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    intent_id: Optional[str] = None
    nodes: Dict[str, TaskNode_v3] = Field(default_factory=dict)
    edges: List[TaskEdge_v3] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def add_node(self, node: TaskNode_v3) -> TaskNode_v3:
        """添加节点。"""
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str) -> Optional[TaskNode_v3]:
        """移除节点并清理相关边。"""
        try:
            node = self.nodes.pop(node_id, None)
            if node:
                self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
            return node
        except Exception as exc:
            logger.error(f"remove_node failed for {node_id}: {exc}")
            raise

    def get_node(self, node_id: str) -> Optional[TaskNode_v3]:
        """获取节点。"""
        return self.nodes.get(node_id)

    def add_edge(self, edge: TaskEdge_v3) -> None:
        """添加边（要求两端节点必须已存在）。"""
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise ValueError(f"Edge references non-existent node: {edge}")
        self.edges.append(edge)

    def get_roots(self) -> List[TaskNode_v3]:
        """获取根节点（无入边）。"""
        incoming = {e.target_id for e in self.edges}
        return [n for n in self.nodes.values() if n.id not in incoming]

    def get_leaves(self) -> List[TaskNode_v3]:
        """获取叶节点（无出边）。"""
        outgoing = {e.source_id for e in self.edges}
        return [n for n in self.nodes.values() if n.id not in outgoing]

    def topological_order(self) -> List[TaskNode_v3]:
        """Kahn 算法拓扑排序（检测到环时返回部分顺序并记录警告）。"""
        try:
            in_degree: Dict[str, int] = {}
            for nid in self.nodes:
                in_degree[nid] = 0
            for e in self.edges:
                in_degree[e.target_id] = in_degree.get(e.target_id, 0) + 1

            queue = [nid for nid, deg in in_degree.items() if deg == 0]
            order: List[str] = []
            while queue:
                nid = queue.pop(0)
                order.append(nid)
                for e in self.edges:
                    if e.source_id == nid:
                        in_degree[e.target_id] -= 1
                        if in_degree[e.target_id] == 0:
                            queue.append(e.target_id)

            if len(order) != len(self.nodes):
                logger.warning(
                    "Cycle detected in TaskGraph_v3, returning partial order"
                )
            return [self.nodes[nid] for nid in order]
        except Exception as exc:
            logger.error(f"topological_order failed: {exc}")
            raise

    async def async_get_ready_nodes(self) -> List[TaskNode_v3]:
        """异步获取已就绪节点（所有依赖均成功完成）。"""
        try:
            await asyncio.sleep(0)  # 让出事件循环，支持并发
            incoming_map: Dict[str, Set[str]] = {}
            for e in self.edges:
                incoming_map.setdefault(e.target_id, set()).add(e.source_id)

            ready: List[TaskNode_v3] = []
            for node in self.nodes.values():
                if node.status != TaskStatus.PENDING:
                    continue
                deps = incoming_map.get(node.id, set())
                if all(self.nodes[d].status == TaskStatus.SUCCESS for d in deps):
                    ready.append(node)
            return ready
        except Exception as exc:
            logger.error(f"async_get_ready_nodes failed: {exc}")
            raise

    def __repr__(self) -> str:
        return (
            f"TaskGraph_v3(nodes={len(self.nodes)}, "
            f"edges={len(self.edges)}, intent={self.intent_id})"
        )


class ParseResult_v3(BaseModel):
    """v3.0 解析结果——IntentParser 的最终输出。

    当 ``is_actionable`` 为 False 时，``clarification_message`` 与
    ``suggestions`` 提供前端渲染所需的澄清信息。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    intent: Intent_v3
    task_graph: Optional[TaskGraph_v3] = None
    is_actionable: bool = False
    clarification_message: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)
    trace_log: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 认知与配置模型
# ═══════════════════════════════════════════════════════════════════════════════

class CognitiveProfile_v3(BaseModel):
    """v3.0 认知画像——Layer-1 认知特征（源自 PCR 输出）。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    metacognition: float = 0.0
    divergence: float = 0.0
    tracking_depth: float = 0.0
    stability: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典，兼容旧版调用。"""
        return self.model_dump(exclude_none=True)


class IntentContext_v3(BaseModel):
    """v3.0 意图上下文——Layer-1 控制信号（由 PCR 输出转换而来）。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    expectation: UserExpectation = UserExpectation.UNKNOWN
    noise_level: float = 0.0
    complexity_level: float = 0.0
    cognitive_profile: CognitiveProfile_v3 = Field(default_factory=CognitiveProfile_v3)
    execution_mode: str = "BALANCED"
    auto_resolve_threshold: float = 0.5
    max_ambiguities_before_ask: int = 3
    max_sub_intents: int = 5
    min_confidence_threshold: float = 0.4
    prompt_style: str = "BALANCED"
    noise_source: Optional[str] = None
    trace_log: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典，兼容旧版调用。"""
        return self.model_dump(exclude_none=True, by_alias=True)


class ParserConfig_v3(BaseModel):
    """v3.0 解析器运行时配置——支持动态调参（PCR 驱动）。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    enable_rule_engine: bool = True
    enable_llm_fallback: bool = True
    max_entities: int = 50
    min_confidence_threshold: float = 0.3
    auto_resolve_ambiguities: bool = True
    auto_resolve_threshold: float = 0.7
    max_ambiguities_before_ask: int = 3
    max_sub_intents: int = 5
    split_on_conjunctions: bool = True
    context_window_size: int = 10
    inherit_entities_from_context: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: float = 300.0
    fast_path_entity_threshold: float = 0.85
    fast_path_intent_threshold: float = 0.40
    verbose_logging: bool = False
    trace_every_step: bool = False
    enable_synonym_expansion: bool = False
    enable_topic_inheritance: bool = False
    prompt_style: str = "BALANCED"
    trace_log: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 服务层数据模型
# ═══════════════════════════════════════════════════════════════════════════════

class SessionState_v3(BaseModel):
    """v3.0 会话状态——支持多轮推理的持久化会话容器。

    设计用于服务层的内存缓存 + 持久化双写，状态变更后应立即写入 SQLite。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    process_name: Optional[str] = None
    pid: Optional[int] = None
    status: str = "active"  # active, paused, closed, error
    history: List[Intent_v3] = Field(default_factory=list)
    resolved_entities: Dict[str, Any] = Field(default_factory=dict)
    pending_clarifications: List[Ambiguity_v3] = Field(default_factory=list)
    current_task_graph: Optional[TaskGraph_v3] = None
    cognitive_profile: Optional[CognitiveProfile_v3] = None
    parser_config: Optional[ParserConfig_v3] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    async def async_close(self) -> None:
        """异步关闭会话，更新状态与时间戳。"""
        try:
            await asyncio.sleep(0)
            self.status = "closed"
            self.updated_at = time.time()
            logger.info(f"Session {self.session_id} closed asynchronously")
        except Exception as exc:
            logger.error(f"Failed to close session {self.session_id}: {exc}")
            raise

    async def async_add_intent(self, intent: Intent_v3) -> None:
        """异步添加意图并提取高置信度实体到 resolved_entities。"""
        try:
            await asyncio.sleep(0)
            self.history.append(intent)
            for e in intent.entities:
                if e.confidence >= 0.8:
                    self.resolved_entities[e.type.value] = e.value
            self.updated_at = time.time()
        except Exception as exc:
            logger.error(f"async_add_intent failed: {exc}")
            raise


class AgentMessage_v3(BaseModel):
    """v3.0 Agent 消息——服务层向下推送的标准消息结构。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str
    role: MessageRole = MessageRole.AGENT
    content: str
    intent: Optional[Intent_v3] = None
    task_graph: Optional[TaskGraph_v3] = None
    clarifications: List[Ambiguity_v3] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class UserMessage_v3(BaseModel):
    """v3.0 用户消息——服务层接收的标准输入结构。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str
    role: MessageRole = MessageRole.USER
    content: str
    raw_input: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket 事件模型
# ═══════════════════════════════════════════════════════════════════════════════

class WebSocketEvent(BaseModel):
    """WebSocket 标准事件——所有前端推送事件的统一包装。

    使用 EventBuilder 流式 API 构造：

    .. code-block:: python

        event = (
            WebSocketEvent.builder(EventType.MESSAGE, "sess-123")
            .with_payload("content", "hello")
            .build()
        )
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    event_type: EventType
    session_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    version: str = "3.0.0"

    @classmethod
    def builder(cls, event_type: EventType, session_id: str) -> "WebSocketEventBuilder":
        """获取事件构建器。"""
        return WebSocketEventBuilder(event_type, session_id)

    async def async_serialize(self) -> str:
        """异步序列化为 JSON 字符串。"""
        try:
            await asyncio.sleep(0)
            return self.model_dump_json(by_alias=True, exclude_none=False)
        except Exception as exc:
            logger.error(f"WebSocketEvent async_serialize failed: {exc}")
            raise


class WebSocketEventBuilder:
    """WebSocket 事件构建器——流式 API，支持链式调用。"""

    def __init__(self, event_type: EventType, session_id: str):
        self.event_type = event_type
        self.session_id = session_id
        self.payload: Dict[str, Any] = {}
        self.version: str = "3.0.0"

    def with_payload(self, key: str, value: Any) -> "WebSocketEventBuilder":
        """添加单个 payload 键值。"""
        self.payload[key] = value
        return self

    def with_payload_dict(self, data: Dict[str, Any]) -> "WebSocketEventBuilder":
        """批量合并 payload 字典。"""
        self.payload.update(data)
        return self

    def build(self) -> WebSocketEvent:
        """构建最终的 WebSocketEvent。"""
        return WebSocketEvent(
            event_type=self.event_type,
            session_id=self.session_id,
            payload=self.payload,
            version=self.version,
        )

    async def async_build(self) -> WebSocketEvent:
        """异步构建（支持 I/O 密集型 payload 准备）。"""
        try:
            await asyncio.sleep(0)
            return self.build()
        except Exception as exc:
            logger.error(f"WebSocketEventBuilder async_build failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════════
# 健康与监控模型
# ═══════════════════════════════════════════════════════════════════════════════

class ComponentHealth(BaseModel):
    """组件健康详情——用于 /health 端点的组件级诊断。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    component: ComponentType
    status: str  # ok, warn, error
    latency_ms: float = 0.0
    message: Optional[str] = None
    last_checked: float = Field(default_factory=time.time)


class HealthStatus(BaseModel):
    """整体健康状态——/health 端点的顶层响应模型。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    status: str  # healthy, degraded, unhealthy
    components: Dict[str, ComponentHealth] = Field(default_factory=dict)
    uptime_seconds: float = 0.0
    version: str = "3.0.0"
    timestamp: float = Field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════════
# 通用响应包装
# ═══════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    """API 标准响应包装——所有 REST 响应的统一结构。

    使用泛型参数 ``T`` 指定 ``data`` 字段的具体类型，便于 FastAPI 生成
    OpenAPI Schema。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    success: bool = True
    code: str = "ok"
    message: str = "success"
    data: Optional[T] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: float = Field(default_factory=time.time)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装——列表接口的统一分页结构。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    items: List[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# 异步工具函数
# ═══════════════════════════════════════════════════════════════════════════════

async def async_validate_model(model: BaseModel) -> None:
    """异步验证模型——触发子类 ``async_validate`` 钩子。

    在 FastAPI 依赖注入或 WebSocket 处理流程中调用，避免阻塞事件循环。
    """
    try:
        await asyncio.sleep(0)
        if hasattr(model, "async_validate") and callable(
            getattr(model, "async_validate")
        ):
            await model.async_validate()
    except Exception as exc:
        logger.error(f"async_validate_model failed: {exc}")
        raise


async def async_serialize_model(model: BaseModel) -> str:
    """异步序列化模型为 JSON 字符串。

    包装 Pydantic v2 的 ``model_dump_json()``，在序列化前让出事件循环，
    适合 I/O 密集型场景（如 WebSocket 广播）。
    """
    try:
        await asyncio.sleep(0)
        return model.model_dump_json(by_alias=True, exclude_none=False)
    except Exception as exc:
        logger.error(f"async_serialize_model failed: {exc}")
        raise


async def async_deserialize_model(model_cls: type, json_str: str) -> Any:
    """异步从 JSON 字符串反序列化模型。

    包装 Pydantic v2 的 ``model_validate_json()``，在反序列化前让出事件循环。
    """
    try:
        await asyncio.sleep(0)
        return model_cls.model_validate_json(json_str)
    except Exception as exc:
        logger.error(f"async_deserialize_model failed for {model_cls.__name__}: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# 前向引用解析（Pydantic v2 自动处理，显式调用以确保安全）
# ═══════════════════════════════════════════════════════════════════════════════
try:
    Intent_v3.model_rebuild()
    TaskGraph_v3.model_rebuild()
    ParseResult_v3.model_rebuild()
    SessionState_v3.model_rebuild()
    AgentMessage_v3.model_rebuild()
    UserMessage_v3.model_rebuild()
    WebSocketEvent.model_rebuild()
except Exception as _rebuild_err:
    logger.warning(f"Model rebuild warning (non-critical): {_rebuild_err}")


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检（模块可直接运行验证）
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        """内部自测函数——覆盖核心模型的创建、序列化、异步操作。"""
        logger.info("=== DialogMesh v3.0 data_models self-test ===")

        # 1. 实体测试
        entity = Entity_v3(type=EntityType.NUMERIC_VALUE, value=42, confidence=1.2)
        assert entity.confidence == 1.0, "Confidence should be clamped to 1.0"
        print(f"[PASS] Entity_v3: {entity}")

        # 2. 意图测试
        intent = Intent_v3(
            category=IntentCategory.SCAN_MEMORY,
            raw_input="scan memory for 100",
            entities=[entity],
        )
        assert intent.is_ambiguous() is False
        print(f"[PASS] Intent_v3: {intent.category.value}")

        # 3. 任务图测试
        tg = TaskGraph_v3()
        n1 = TaskNode_v3(name="scan", goal="find address")
        n2 = TaskNode_v3(name="verify", goal="check value")
        tg.add_node(n1)
        tg.add_node(n2)
        tg.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n2.id))
        assert len(tg.get_roots()) == 1
        assert len(tg.topological_order()) == 2
        print(f"[PASS] TaskGraph_v3: {tg}")

        # 4. 异步就绪节点测试
        n1.mark_success({"address": "0x1234"})
        ready = await tg.async_get_ready_nodes()
        assert len(ready) == 1 and ready[0].id == n2.id
        print(f"[PASS] async_get_ready_nodes: ready={len(ready)}")

        # 5. WebSocket 事件构建器测试
        event = (
            WebSocketEvent.builder(EventType.MESSAGE, "sess-123")
            .with_payload("content", "hello")
            .with_payload_dict({"seq": 1})
            .build()
        )
        assert event.payload["content"] == "hello"
        json_str = await event.async_serialize()
        assert "message" in json_str
        print(f"[PASS] WebSocketEvent: {event.event_type.value}")

        # 6. 序列化/反序列化测试
        serialized = await async_serialize_model(intent)
        deserialized = await async_deserialize_model(Intent_v3, serialized)
        assert deserialized.raw_input == intent.raw_input
        print(f"[PASS] async_serialize / async_deserialize")

        # 7. API 响应泛型测试
        resp = APIResponse(data=intent)
        assert resp.success is True
        print(f"[PASS] APIResponse[Intent_v3]")

        # 8. 会话测试
        session = SessionState_v3()
        await session.async_add_intent(intent)
        assert len(session.history) == 1
        print(f"[PASS] SessionState_v3: {session.session_id}")

        # 9. 健康状态测试
        comp = ComponentHealth(
            component=ComponentType.PARSER, status="ok", latency_ms=12.5
        )
        health = HealthStatus(
            status="healthy", components={"parser": comp}, uptime_seconds=3600
        )
        assert health.components["parser"].status == "ok"
        print(f"[PASS] HealthStatus")

        logger.info("=== All v3.0 data_models self-tests passed ===")

    asyncio.run(_self_test())
