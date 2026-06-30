# -*- coding: utf-8 -*-
"""
core/agent/frontend — 前端交互协议层（Layer 3）
"""

from __future__ import annotations

from core.agent.frontend.clarification_ui import (
    ClarificationUISchema,
    UIComponent,
    UIOption,
    UIValidation,
    ClarificationUIFactory,
    ClarificationUICompat,
)
from core.agent.frontend.taskgraph_viz import (
    TaskNodePayload,
    TaskEdgePayload,
    TaskGraphPayload,
    TaskGraphUpdateEvent,
)
from core.agent.frontend.clarification_fsm import (
    ClarificationFSM,
    ClarificationFSMContext,
    ClarificationState,
    ClarificationEvent,
    StateTransitionLog,
)
from core.agent.frontend.websocket_events import (
    EventType,
    WebSocketEvent,
    EventBuilder,
    EventSerializer,
)
from core.agent.frontend.multimodal import (
    MediaAttachment,
    PreprocessedContent,
    ImagePreprocessor,
    AudioPreprocessor,
    DocumentPreprocessor,
    MultimodalPipeline,
    MockOCREngine,
    MockASREngine,
)

__all__ = [
    "ClarificationUISchema",
    "UIComponent",
    "UIOption",
    "UIValidation",
    "ClarificationUIFactory",
    "ClarificationUICompat",
    "TaskNodePayload",
    "TaskEdgePayload",
    "TaskGraphPayload",
    "TaskGraphUpdateEvent",
    "ClarificationFSM",
    "ClarificationFSMContext",
    "ClarificationState",
    "ClarificationEvent",
    "StateTransitionLog",
    "EventType",
    "WebSocketEvent",
    "EventBuilder",
    "EventSerializer",
    "MediaAttachment",
    "PreprocessedContent",
    "ImagePreprocessor",
    "AudioPreprocessor",
    "DocumentPreprocessor",
    "MultimodalPipeline",
    "MockOCREngine",
    "MockASREngine",
]
