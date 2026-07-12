"""pytest fixtures for MemoryGraph discourse block tree tests."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.api.main import create_app
from service.api.dependencies import (
    get_agent_service,
    get_session_manager,
    get_websocket_manager,
    AgentService,
)
from service.async_session_manager import AsyncSessionManager
from service.api.websocket import WebSocketManager
from service.models import Session, CognitiveProfile, AdaptiveThresholds, TurnRecord
from service.protocol.events import EventSerializer, WebSocketEvent, EventBuilder
from service.protocol.fsm import ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent
from service.protocol.schemas import (
    CreateSessionRequest, SendMessageRequest, ClarifyRequest,
    CreateSessionResponse, SendMessageResponse, ClarifyResponse,
    HistoryResponse, SessionStatusResponse, HealthResponse,
    ComponentHealth, CognitiveProfilePayload, ErrorAction, ErrorUIPayload,
    MultimodalInputRequest, IntentResult, ClarificationPayload, EntityPayload,
)
from service.protocol.ui_schema import (
    ClarificationUISchema, UIComponent, UIOption, UIValidation,
    SINGLE_SELECT, TEXT_INPUT, SHOW_INFO,
)
from service.protocol.task_graph import (
    TaskGraphPayload, TaskNodePayload, TaskEdgePayload,
    NodeStatus, NodeType, EdgeType, TaskGraphUpdateEvent, NodeStatusUpdate,
)
from service.stores.async_sqlite import AsyncSQLiteSessionStore

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1, CognitiveProfile_v1
from core.agent.pcr.interface import PCRHealthStatus
from core.agent.v3_common.models import (
    Intent, IntentCategory, ParseResult, TaskGraph, Entity, EntityType,
    Ambiguity, AmbiguityType, IntentContext, CognitiveProfile as ParserCognitiveProfile,
    UserExpectation, ParseContext,
)
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser

from core.agent.v3_common.discourse_integration import DiscoursePipeline


# ═══════════════════════════════════════════════════════════════════════════════
# Existing Discourse fixtures (preserved)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def discourse_pipeline() -> DiscoursePipeline:
    """Return a fresh DiscoursePipeline instance for each test."""
    return DiscoursePipeline()


@pytest.fixture(scope="function")
def disabled_pipeline() -> DiscoursePipeline:
    """Return a disabled DiscoursePipeline instance."""
    return DiscoursePipeline(enabled=False)


@pytest.fixture(scope="session")
def session_pipeline() -> DiscoursePipeline:
    """Return a DiscoursePipeline instance reused across the test session."""
    pipe = DiscoursePipeline()
    return pipe


# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh Phase 6 — Mock engines
# ═══════════════════════════════════════════════════════════════════════════════

class MockPCR:
    """Mock PCR that always returns TOOL expectation."""

    def __init__(self):
        self._health = PCRHealthStatus.HEALTHY

    @property
    def name(self) -> str:
        return "mock_pcr"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        self._health = PCRHealthStatus.HEALTHY

    def shutdown(self) -> None:
        self._health = PCRHealthStatus.UNHEALTHY

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        return PCROutput_v1.fast_execute_tool(
            query=input_data.query,
            latency_ms=1.0,
        )

    def get_health(self) -> PCRHealthStatus:
        return self._health

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "call_count": 0,
            "error_count": 0,
            "avg_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "cache_hit_rate": 0.0,
            "last_error": None,
            "health_history": [],
        }

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_expectations": ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"],
            "has_cognitive_profile": True,
            "has_noise_estimation": True,
            "has_complexity_estimation": True,
            "requires_llm": False,
            "latency_range_ms": [0, 10],
            "supports_hot_reload": False,
            "config_schema": {},
        }

    def get_schema(self) -> Dict[str, Any]:
        return {}


class MockParser:
    """Mock IntentParser that always returns actionable ParseResult."""

    def __init__(self, ambiguous: bool = False):
        self.ambiguous = ambiguous

    def parse(self, user_input: str, intent_context: IntentContext, parse_context: Any) -> ParseResult:
        if self.ambiguous:
            intent = Intent(
                category=IntentCategory.UNKNOWN,
                raw_input=user_input,
                normalized_input=user_input,
                confidence=0.3,
            )
            intent.ambiguities = [
                Ambiguity(
                    type=AmbiguityType.MISSING_ENTITY,
                    description="Missing address parameter",
                    suggestions=["0x00401000", "0x7FFE0000"],
                    auto_resolvable=False,
                )
            ]
            return ParseResult(
                intent=intent,
                is_actionable=False,
                clarification_message="Please provide the memory address",
                suggestions=["0x00401000", "0x7FFE0000"],
                trace_log=["mock_ambiguous"],
            )

        intent = Intent(
            category=IntentCategory.SCAN_MEMORY,
            raw_input=user_input,
            normalized_input=user_input,
            entities=[Entity(type=EntityType.NUMERIC_VALUE, value="100", raw_text="100", confidence=0.9)],
            confidence=0.95,
        )
        return ParseResult(
            intent=intent,
            task_graph=TaskGraph(),
            is_actionable=True,
            trace_log=["mock_actionable"],
        )


class MockAmbiguousParser(MockParser):
    """Mock IntentParser that always returns ambiguous ParseResult."""

    def __init__(self):
        super().__init__(ambiguous=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh Phase 6 — Core fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_pcr():
    """Mock PCR that always returns TOOL expectation."""
    return MockPCR()


@pytest.fixture
def mock_parser():
    """Mock IntentParser that always returns actionable ParseResult."""
    return MockParser()


@pytest_asyncio.fixture
async def session_manager():
    """AsyncSessionManager with in-memory SQLite store."""
    store = AsyncSQLiteSessionStore(db_path=":memory:")
    sm = AsyncSessionManager(store=store, ttl_seconds=60, eviction_interval_seconds=5)
    await sm.start()
    yield sm
    await sm.stop()


@pytest_asyncio.fixture
async def websocket_manager():
    """WebSocketManager instance with started heartbeat."""
    ws = WebSocketManager()
    await ws.start()
    yield ws
    await ws.stop()


@pytest_asyncio.fixture
async def agent_service(mock_pcr, mock_parser, session_manager, websocket_manager):
    """AgentService wired with mock PCR + parser + real managers."""
    svc = AgentService(mock_pcr, mock_parser, session_manager, websocket_manager)
    yield svc


@pytest_asyncio.fixture
async def app(agent_service, session_manager, websocket_manager):
    """FastAPI app factory with dependency overrides for testing."""
    _app = create_app()
    _app.dependency_overrides[get_agent_service] = lambda: agent_service
    _app.dependency_overrides[get_session_manager] = lambda: session_manager
    _app.dependency_overrides[get_websocket_manager] = lambda: websocket_manager
    yield _app


@pytest_asyncio.fixture
async def client(app):
    """httpx.AsyncClient for HTTP route testing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_session(session_manager):
    """Create a pre-seeded test session."""
    session = await session_manager.create_session(tenant_id="default", user_id="test_user")
    return session


@pytest.fixture
def event_collector():
    """Simple collector for WebSocket events."""
    collected: List[WebSocketEvent] = []

    class Collector:
        def __init__(self):
            self.events = collected

        def add(self, event: WebSocketEvent):
            collected.append(event)

        def clear(self):
            collected.clear()

        def find(self, event_type: str) -> Optional[WebSocketEvent]:
            for e in collected:
                if e.event_type == event_type:
                    return e
            return None

    return Collector()
