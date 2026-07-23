# -*- coding: utf-8 -*-
"""
tests/test_websocket.py
───────────────────────
DialogMesh WebSocket real-time push testing (Phase 6).

Uses TestClient (sync) for WebSocket connections because httpx.AsyncClient
does not support WebSocket.  All WebSocket interactions run inside the
ASGI app's event loop via TestClient's anyio portal.
"""

from __future__ import annotations

import time
from typing import List

import pytest

from fastapi.testclient import TestClient

from service.protocol.events import EventBuilder, EventSerializer, WebSocketEvent, ErrorPayload
from service.protocol.task_graph import TaskGraphPayload, TaskNodePayload, NodeStatus, NodeType


@pytest.mark.asyncio
async def test_websocket_connect(app):
    """WebSocket connection to /ws/{session_id} is accepted."""
    # Create session via HTTP first
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "ws-user"})
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            ws.send_text(EventSerializer.serialize(EventBuilder.ping()))
            data = ws.receive_text()
            event = EventSerializer.deserialize(data)
            assert event.event_type == "pong"


@pytest.mark.asyncio
async def test_websocket_heartbeat(app):
    """Manual ping/pong round-trip is served."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "hb-user"})
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            ping = EventBuilder.ping()
            ws.send_text(EventSerializer.serialize(ping))
            data = ws.receive_text()
            event = EventSerializer.deserialize(data)
            assert event.event_type == "pong"
            assert "server_time" in event.payload


@pytest.mark.asyncio
async def test_websocket_intent_result(app, agent_service):
    """Sending a message broadcasts intent_result via WebSocket."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "ir-user"})
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            # Send HTTP message
            msg_resp = tc.post(
                f"/v1/session/{session_id}/message",
                json={"message_id": "ir-001", "modality": "text", "content": "scan 0x100"},
            )
            assert msg_resp.status_code == 200

            # Read broadcast event on WebSocket
            data = ws.receive_text()
            event = EventSerializer.deserialize(data)
            assert event.event_type == "intent_result"
            assert event.session_id == session_id
            assert event.payload.get("status") == "actionable"


@pytest.mark.asyncio
async def test_websocket_clarification(app, agent_service):
    """Ambiguous message broadcasts clarification event via WebSocket."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "cl-user"})
        session_id = resp.json()["session_id"]

        # Swap to ambiguous parser
        original_parser = agent_service.parser
        agent_service.parser = __import__(
            "tests.conftest", fromlist=["MockAmbiguousParser"]
        ).MockAmbiguousParser()

        try:
            with tc.websocket_connect(f"/ws/{session_id}") as ws:
                msg_resp = tc.post(
                    f"/v1/session/{session_id}/message",
                    json={"message_id": "cl-001", "modality": "text", "content": "scan that thing"},
                )
                assert msg_resp.status_code == 200

                data = ws.receive_text()
                event = EventSerializer.deserialize(data)
                assert event.event_type == "clarification"
                assert event.session_id == session_id
                assert "clarification_id" in event.payload
        finally:
            agent_service.parser = original_parser


@pytest.mark.asyncio
async def test_websocket_taskgraph_update(app, agent_service):
    """TaskGraph update event is broadcast and received."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "tg-user"})
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            # Manually broadcast a taskgraph_update event
            tg_payload = TaskGraphPayload(
                task_graph_id="tg-001",
                nodes=[
                    TaskNodePayload(
                        node_id="n1",
                        name="Scan",
                        status=NodeStatus.RUNNING,
                        progress_pct=50.0,
                        node_type=NodeType.SCAN,
                    )
                ],
                overall_status="running",
                progress_pct=50.0,
            )
            event = EventBuilder.taskgraph_update(session_id, tg_payload.model_dump())
            await agent_service.ws_manager.broadcast(session_id, event)

            data = ws.receive_text()
            received = EventSerializer.deserialize(data)
            assert received.event_type == "taskgraph_update"
            assert received.payload.get("overall_status") == "running"
            assert received.payload["nodes"][0]["node_id"] == "n1"


@pytest.mark.asyncio
async def test_websocket_error(app, agent_service):
    """Error event broadcast is received on WebSocket."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "err-user"})
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            error_payload = ErrorPayload(
                code="SESSION_EXPIRED",
                message="Session has expired",
                retryable=False,
            )
            event = EventBuilder.error(session_id, error_payload.model_dump())
            await agent_service.ws_manager.broadcast(session_id, event)

            data = ws.receive_text()
            received = EventSerializer.deserialize(data)
            assert received.event_type == "error"
            assert received.payload.get("code") == "SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_websocket_multiple_connections(app, agent_service):
    """Multiple WebSocket connections for the same session all receive broadcasts."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "mc-user"})
        session_id = resp.json()["session_id"]

        with tc.websocket_connect(f"/ws/{session_id}") as ws1:
            with tc.websocket_connect(f"/ws/{session_id}") as ws2:
                # Broadcast state_change
                event = EventBuilder.state_change(session_id, "START", "PARSING")
                await agent_service.ws_manager.broadcast(session_id, event)

                data1 = ws1.receive_text()
                data2 = ws2.receive_text()
                ev1 = EventSerializer.deserialize(data1)
                ev2 = EventSerializer.deserialize(data2)
                assert ev1.event_type == "state_change"
                assert ev2.event_type == "state_change"
                assert ev1.payload["new_state"] == "PARSING"
                assert ev2.payload["new_state"] == "PARSING"


@pytest.mark.asyncio
async def test_websocket_disconnect(app, agent_service):
    """Disconnection reduces the session connection count."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "dc-user"})
        session_id = resp.json()["session_id"]

        assert agent_service.ws_manager.get_connection_count(session_id) == 0

        with tc.websocket_connect(f"/ws/{session_id}") as ws:
            assert agent_service.ws_manager.get_connection_count(session_id) == 1

        # After context exit, connection should be closed
        # Note: TestClient may not synchronously reflect disconnect;
        # give a tiny grace and assert via manager internals.
        import asyncio
        await asyncio.sleep(0.05)
        assert agent_service.ws_manager.get_connection_count(session_id) == 0


@pytest.mark.asyncio
async def test_websocket_reconnect(app, agent_service):
    """Reconnection recovers and receives new events."""
    with TestClient(app) as tc:
        resp = tc.post("/v1/session/create", json={"user_id": "rc-user"})
        session_id = resp.json()["session_id"]

        # First connection
        with tc.websocket_connect(f"/ws/{session_id}") as ws1:
            event = EventBuilder.ping()
            await agent_service.ws_manager.broadcast(session_id, event)
            data1 = ws1.receive_text()
            ev1 = EventSerializer.deserialize(data1)
            assert ev1.event_type == "ping"

        # Reconnect
        with tc.websocket_connect(f"/ws/{session_id}") as ws2:
            event2 = EventBuilder.pong()
            await agent_service.ws_manager.broadcast(session_id, event2)
            data2 = ws2.receive_text()
            ev2 = EventSerializer.deserialize(data2)
            assert ev2.event_type == "pong"

        assert agent_service.ws_manager.get_connection_count(session_id) == 0
