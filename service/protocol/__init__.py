# -*- coding: utf-8 -*-
"""
service/protocol/__init__.py
────────────────────────────
DialogMesh 前端交互协议层（Phase 3）公共导出。

导出 Clarification UI 渲染协议、TaskGraph 可视化协议、
多轮澄清状态机、WebSocket 事件标准格式以及 FastAPI 响应模型。
"""

from .ui_schema import (
    SINGLE_SELECT,
    MULTI_SELECT,
    TEXT_INPUT,
    NUMBER_INPUT,
    ADDRESS_INPUT,
    CONFIRM_DANGEROUS,
    SHOW_INFO,
    PROGRESS_INDICATOR,
    TASKGRAPH_PREVIEW,
    UIOption,
    UIValidation,
    UIComponent,
    ClarificationUISchema,
)

from .task_graph import (
    NodeStatus,
    EdgeType,
    NodeType,
    TaskNodePayload,
    TaskEdgePayload,
    TaskGraphPayload,
    TaskGraphUpdateEvent,
    NodeStatusUpdate,
)

from .fsm import (
    ClarificationState,
    ClarificationEvent,
    TRANSITIONS,
    ClarificationFSMContext,
    ClarificationFSM,
)

from .events import (
    WebSocketEvent,
    EventBuilder,
    EventSerializer,
    ParseProgressEvent,
    ErrorPayload,
)

from .schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    ClarifyRequest,
    ClarifyResponse,
    HistoryResponse,
    MessageRecord,
    SessionStatusResponse,
    HealthResponse,
    ComponentHealth,
    IntentResult,
    ClarificationPayload,
    CognitiveProfilePayload,
    EntityPayload,
    ErrorUIPayload,
    ErrorAction,
    MultimodalInputRequest,
)

__all__ = [
    # ui_schema
    "SINGLE_SELECT",
    "MULTI_SELECT",
    "TEXT_INPUT",
    "NUMBER_INPUT",
    "ADDRESS_INPUT",
    "CONFIRM_DANGEROUS",
    "SHOW_INFO",
    "PROGRESS_INDICATOR",
    "TASKGRAPH_PREVIEW",
    "UIOption",
    "UIValidation",
    "UIComponent",
    "ClarificationUISchema",
    # task_graph
    "NodeStatus",
    "EdgeType",
    "NodeType",
    "TaskNodePayload",
    "TaskEdgePayload",
    "TaskGraphPayload",
    "TaskGraphUpdateEvent",
    "NodeStatusUpdate",
    # fsm
    "ClarificationState",
    "ClarificationEvent",
    "TRANSITIONS",
    "ClarificationFSMContext",
    "ClarificationFSM",
    # events
    "WebSocketEvent",
    "EventBuilder",
    "EventSerializer",
    "ParseProgressEvent",
    "ErrorPayload",
    # schemas
    "CreateSessionRequest",
    "CreateSessionResponse",
    "SendMessageRequest",
    "SendMessageResponse",
    "ClarifyRequest",
    "ClarifyResponse",
    "HistoryResponse",
    "MessageRecord",
    "SessionStatusResponse",
    "HealthResponse",
    "ComponentHealth",
    "IntentResult",
    "ClarificationPayload",
    "CognitiveProfilePayload",
    "EntityPayload",
    "ErrorUIPayload",
    "ErrorAction",
    "MultimodalInputRequest",
]
