# -*- coding: utf-8 -*-
"""
tests/test_protocol.py
──────────────────────
DialogMesh front-end protocol layer testing (Phase 6).

Covers UI Schema, FSM, Events, Pydantic Schemas, and TaskGraph payload.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

import pytest

from service.protocol.ui_schema import (
    ClarificationUISchema,
    UIComponent,
    UIOption,
    UIValidation,
    SINGLE_SELECT,
    TEXT_INPUT,
    SHOW_INFO,
)
from service.protocol.fsm import (
    ClarificationFSM,
    ClarificationFSMContext,
    ClarificationState,
    ClarificationEvent,
    TRANSITIONS,
)
from service.protocol.events import (
    WebSocketEvent,
    EventBuilder,
    EventSerializer,
    ParseProgressEvent,
    ErrorPayload,
)
from service.protocol.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    ClarifyRequest,
    ClarifyResponse,
    MessageRecord,
    HistoryResponse,
    SessionStatusResponse,
    HealthResponse,
    ComponentHealth,
    CognitiveProfilePayload,
    ErrorAction,
    ErrorUIPayload,
    MultimodalInputRequest,
    IntentResult,
    ClarificationPayload,
    EntityPayload,
)
from service.protocol.task_graph import (
    TaskGraphPayload,
    TaskNodePayload,
    TaskEdgePayload,
    NodeStatus,
    NodeType,
    EdgeType,
    TaskGraphUpdateEvent,
    NodeStatusUpdate,
)


# ═══════════════════════════════════════════════════════════════════════════════
# UI Schema
# ═══════════════════════════════════════════════════════════════════════════════

def test_clarification_ui_schema():
    """ClarificationUISchema serializes and deserializes correctly."""
    schema = ClarificationUISchema(
        version="1.0",
        message_style="warning",
        components=[
            UIComponent(
                type=TEXT_INPUT,
                id="addr_input",
                label="Memory Address",
                placeholder="0x00401000",
                validation=UIValidation(
                    type="regex",
                    pattern=r"^0x[0-9A-Fa-f]+",
                    error_message="Invalid hex address",
                ),
            ),
            UIComponent(
                type=SHOW_INFO,
                id="info_1",
                label="Hint",
            ),
        ],
        allow_free_text=True,
        allow_skip=False,
    )

    d = schema.model_dump()
    assert d["version"] == "1.0"
    assert d["message_style"] == "warning"
    assert len(d["components"]) == 2
    assert d["components"][0]["type"] == TEXT_INPUT
    assert d["components"][0]["validation"]["pattern"] == r"^0x[0-9A-Fa-f]+"

    restored = ClarificationUISchema.model_validate(d)
    assert restored.version == "1.0"
    assert len(restored.components) == 2
    assert restored.components[0].type == TEXT_INPUT


def test_ui_component_validation():
    """UIValidation regex validation is stored correctly."""
    v = UIValidation(
        type="regex",
        pattern=r"^\d+$",
        error_message="Must be numeric",
    )
    assert v.type == "regex"
    assert v.pattern == r"^\d+$"
    assert v.error_message == "Must be numeric"

    # Serialize
    d = v.model_dump()
    assert d["pattern"] == r"^\d+$"


# ═══════════════════════════════════════════════════════════════════════════════
# FSM
# ═══════════════════════════════════════════════════════════════════════════════

def test_fsm_transitions():
    """All legal state transitions succeed and update state correctly."""
    ctx = ClarificationFSMContext(session_id="sess-123")
    fsm = ClarificationFSM(ctx)

    assert fsm.context.current_state == ClarificationState.START

    # START → USER_MESSAGE → PARSING
    new_state, _ = fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    assert new_state == ClarificationState.PARSING

    # PARSING → PARSE_COMPLETE_NO_AMBIGUITY → ACTIONABLE
    new_state, payload = fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY, {"intent": "scan"})
    assert new_state == ClarificationState.ACTIONABLE
    assert payload["previous_state"] == ClarificationState.PARSING
    assert payload["new_state"] == ClarificationState.ACTIONABLE

    # ACTIONABLE → USER_MESSAGE → PARSING
    new_state, _ = fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    assert new_state == ClarificationState.PARSING

    # PARSING → PARSE_COMPLETE_HAS_AMBIGUITY → CLARIFYING
    new_state, _ = fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    assert new_state == ClarificationState.CLARIFYING
    assert fsm.context.clarification_count == 1

    # CLARIFYING → USER_CLARIFY → RE_PARSING
    new_state, _ = fsm.handle_event(ClarificationEvent.USER_CLARIFY)
    assert new_state == ClarificationState.RE_PARSING

    # RE_PARSING → REPARSE_COMPLETE_NO_AMBIGUITY → ACTIONABLE
    new_state, _ = fsm.handle_event(ClarificationEvent.REPARSE_COMPLETE_NO_AMBIGUITY)
    assert new_state == ClarificationState.ACTIONABLE

    # ACTIONABLE → CLOSE → CLOSED
    new_state, _ = fsm.handle_event(ClarificationEvent.CLOSE)
    assert new_state == ClarificationState.CLOSED


def test_fsm_illegal_transition():
    """Illegal transitions keep the current state and return an error payload."""
    ctx = ClarificationFSMContext(session_id="sess-456")
    fsm = ClarificationFSM(ctx)

    # START → ACTIONABLE is illegal
    new_state, payload = fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)
    assert new_state == ClarificationState.START  # unchanged
    assert "error" in payload
    assert "非法状态转换" in payload["error"]

    # Verify allowed_events are returned
    assert "allowed_events" in payload
    assert ClarificationEvent.USER_MESSAGE in payload["allowed_events"]


def test_fsm_timeout():
    """Timeout detection works when CLARIFYING exceeds timeout_seconds."""
    ctx = ClarificationFSMContext(session_id="sess-789", timeout_seconds=2)
    fsm = ClarificationFSM(ctx)

    # Move to CLARIFYING
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    assert fsm.context.current_state == ClarificationState.CLARIFYING

    # Not expired yet
    assert fsm.is_expired() is False

    # Mock last_transition_at to be in the past
    fsm.context.last_transition_at = time.time() - 5
    assert fsm.is_expired() is True


def test_fsm_max_clarifications():
    """After 5 rounds of clarification, further ambiguity forces EXPIRED."""
    ctx = ClarificationFSMContext(session_id="sess-max", max_clarifications=5)
    fsm = ClarificationFSM(ctx)

    # Initial cycle: START → PARSING → CLARIFYING (count=1)
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    assert fsm.context.current_state == ClarificationState.CLARIFYING
    assert fsm.context.clarification_count == 1

    # Cycles 2–4 from CLARIFYING: each adds 1 to count
    for i in range(3):
        fsm.handle_event(ClarificationEvent.USER_CLARIFY)
        fsm.handle_event(ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY)
        assert fsm.context.current_state == ClarificationState.CLARIFYING

    assert fsm.context.clarification_count == 4
    assert fsm.can_clarify_more() is True

    # 5th cycle: count reaches 5 → forced EXPIRED
    fsm.handle_event(ClarificationEvent.USER_CLARIFY)
    new_state, payload = fsm.handle_event(ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY)
    assert new_state == ClarificationState.EXPIRED
    assert payload.get("reason") == "max_clarifications_reached"
    assert fsm.context.clarification_count == 5
    assert fsm.can_clarify_more() is False


def test_fsm_persistence():
    """FSM round-trips through to_dict / from_dict without data loss."""
    ctx = ClarificationFSMContext(
        session_id="sess-persist",
        current_state=ClarificationState.CLARIFYING,
        clarification_count=2,
        max_clarifications=5,
        timeout_seconds=120,
    )
    fsm = ClarificationFSM(ctx)

    d = fsm.to_dict()
    assert d["context"]["session_id"] == "sess-persist"
    assert d["current_state"] == ClarificationState.CLARIFYING
    assert d["clarification_count"] == 2

    restored = ClarificationFSM.from_dict(d)
    assert restored.context.session_id == "sess-persist"
    assert restored.context.current_state == ClarificationState.CLARIFYING
    assert restored.context.clarification_count == 2
    assert restored.context.max_clarifications == 5
    assert restored.context.timeout_seconds == 120


# ═══════════════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════════════

def test_event_builder():
    """All EventBuilder factory methods produce valid WebSocketEvents."""
    session_id = "sess-events"

    e1 = EventBuilder.intent_result(session_id, {"expectation": "TOOL"})
    assert e1.event_type == "intent_result"
    assert e1.session_id == session_id

    e2 = EventBuilder.clarification(session_id, {"clarification_id": "c1"})
    assert e2.event_type == "clarification"

    e3 = EventBuilder.progress(session_id, {"stage": "pcr", "status": "completed"})
    assert e3.event_type == "progress"

    e4 = EventBuilder.taskgraph_update(session_id, {"nodes": []})
    assert e4.event_type == "taskgraph_update"

    e5 = EventBuilder.error(session_id, {"code": "ERR"})
    assert e5.event_type == "error"

    e6 = EventBuilder.state_change(session_id, "START", "PARSING")
    assert e6.event_type == "state_change"
    assert e6.payload["old_state"] == "START"
    assert e6.payload["new_state"] == "PARSING"

    e7 = EventBuilder.ping()
    assert e7.event_type == "ping"
    assert e7.session_id is None

    e8 = EventBuilder.pong(server_time=1234567890.0)
    assert e8.event_type == "pong"
    assert e8.payload["server_time"] == 1234567890.0


def test_event_serializer():
    """JSON serialization and deserialization round-trip preserves data."""
    original = EventBuilder.intent_result(
        "sess-serial",
        {"message_id": "m1", "status": "actionable", "latency_ms": 12.5},
    )
    json_str = EventSerializer.serialize(original)
    assert isinstance(json_str, str)

    restored = EventSerializer.deserialize(json_str)
    assert restored.event_type == "intent_result"
    assert restored.session_id == "sess-serial"
    assert restored.payload["message_id"] == "m1"
    assert restored.payload["latency_ms"] == 12.5

    # Also test that it is valid JSON
    parsed = json.loads(json_str)
    assert parsed["event_type"] == "intent_result"


# ═══════════════════════════════════════════════════════════════════════════════
# TaskGraph
# ═══════════════════════════════════════════════════════════════════════════════

def test_task_graph_payload():
    """TaskGraphPayload construction and node status updates are correct."""
    tg = TaskGraphPayload(
        task_graph_id="tg-001",
        nodes=[
            TaskNodePayload(
                node_id="n1",
                name="First Scan",
                status=NodeStatus.PENDING,
                node_type=NodeType.SCAN,
            ),
            TaskNodePayload(
                node_id="n2",
                name="Read Memory",
                status=NodeStatus.PENDING,
                node_type=NodeType.READ,
            ),
        ],
        edges=[
            TaskEdgePayload(
                source_id="n1",
                target_id="n2",
                edge_type=EdgeType.SEQUENTIAL,
            ),
        ],
        overall_status="pending",
    )

    assert len(tg.nodes) == 2
    assert len(tg.edges) == 1
    assert tg.nodes[0].status == NodeStatus.PENDING

    # Simulate node status update
    tg.nodes[0].status = NodeStatus.RUNNING
    tg.nodes[0].progress_pct = 50.0
    assert tg.nodes[0].status == NodeStatus.RUNNING
    assert tg.nodes[0].progress_pct == 50.0

    # Serialize round-trip
    d = tg.model_dump()
    restored = TaskGraphPayload.model_validate(d)
    assert restored.nodes[0].status == NodeStatus.RUNNING
    assert restored.overall_status == "pending"


def test_error_payload():
    """ErrorPayload construction and retry logic fields are correct."""
    err = ErrorPayload(
        code="RATE_LIMITED",
        message="Too many requests",
        retryable=True,
        retry_after_ms=1500,
    )
    assert err.code == "RATE_LIMITED"
    assert err.retryable is True
    assert err.retry_after_ms == 1500

    d = err.model_dump()
    assert d["retryable"] is True
    assert d["retry_after_ms"] == 1500

    # Non-retryable error
    err2 = ErrorPayload(
        code="SESSION_EXPIRED",
        message="Session expired",
        retryable=False,
    )
    assert err2.retryable is False
    assert err2.retry_after_ms is None


def test_multimodal_input_request():
    """MultimodalInputRequest validates modality and required fields."""
    # Valid TEXT request
    req = MultimodalInputRequest(
        modality="text",
        text_content="hello",
        client_sequence=0,
    )
    assert req.modality == "text"
    assert req.text_content == "hello"

    # Valid IMAGE request
    req2 = MultimodalInputRequest(
        modality="image",
        image_url="http://example.com/img.png",
        client_sequence=1,
    )
    assert req2.modality == "image"
    assert req2.image_url == "http://example.com/img.png"

    # Invalid: negative sequence (ge=0 should reject, but Pydantic validates on creation)
    with pytest.raises(Exception):
        MultimodalInputRequest(
            modality="text",
            client_sequence=-1,
        )
