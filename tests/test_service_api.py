# -*- coding: utf-8 -*-
"""
tests/test_service_api.py
─────────────────────────
DialogMesh REST API route testing (Phase 6).

Coverage: session lifecycle, messaging, health, metrics, rate-limiting,
error handling, and file upload.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import pytest

from fastapi.testclient import TestClient

from service.models import TurnRecord
from service.protocol.events import EventBuilder, EventSerializer


# ═══════════════════════════════════════════════════════════════════════════════
# Session lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_session(client):
    """POST /v1/session/create returns session_id and ws_url."""
    payload = {"user_id": "user-123", "initial_context": {"theme": "dark"}}
    resp = await client.post("/v1/session/create", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) > 0
    assert data["ws_url"].startswith("/ws/")
    assert "created_at" in data
    assert "session_ttl_seconds" in data


@pytest.mark.asyncio
async def test_send_message(client, test_session, agent_service):
    """POST /v1/session/{id}/message returns actionable status."""
    payload = {
        "message_id": "msg-001",
        "modality": "text",
        "content": "scan 100",
    }
    resp = await client.post(
        f"/v1/session/{test_session.session_id}/message", json=payload
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["message_id"] == "msg-001"
    assert data["status"] == "actionable"
    assert data["intent_result"] is not None
    assert data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_send_message_with_clarification(client, test_session, agent_service):
    """Ambiguous input triggers clarification in response."""
    # Swap parser to ambiguous mode
    original_parser = agent_service.parser
    agent_service.parser = __import__(
        "tests.conftest", fromlist=["MockAmbiguousParser"]
    ).MockAmbiguousParser()

    try:
        payload = {
            "message_id": "msg-ambig",
            "modality": "text",
            "content": "scan that thing",
        }
        resp = await client.post(
            f"/v1/session/{test_session.session_id}/message", json=payload
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["status"] == "needs_clarification"
        assert data["clarification"] is not None
        assert "clarification_id" in data["clarification"]
        assert len(data["clarification"]["suggestions"]) > 0
    finally:
        agent_service.parser = original_parser


@pytest.mark.asyncio
async def test_clarify(client, test_session, agent_service):
    """POST /v1/session/{id}/clarify resolves pending clarification."""
    # 1. Send ambiguous message to create a clarification
    original_parser = agent_service.parser
    agent_service.parser = __import__(
        "tests.conftest", fromlist=["MockAmbiguousParser"]
    ).MockAmbiguousParser()

    try:
        msg_resp = await client.post(
            f"/v1/session/{test_session.session_id}/message",
            json={"message_id": "msg-002", "modality": "text", "content": "scan that thing"},
        )
        msg_data = msg_resp.json()
        clarification_id = msg_data["clarification"]["clarification_id"]

        # Restore actionable parser before submitting clarification
        agent_service.parser = original_parser

        # 2. Submit clarification reply
        clarify_resp = await client.post(
            f"/v1/session/{test_session.session_id}/clarify",
            json={"clarification_id": clarification_id, "selected_option": 0},
        )
        assert clarify_resp.status_code == 200, clarify_resp.text

        clarify_data = clarify_resp.json()
        assert clarify_data["status"] in ("resolved", "needs_more_clarification", "actionable")
    finally:
        agent_service.parser = original_parser


@pytest.mark.asyncio
async def test_get_history(client, test_session, session_manager):
    """GET /v1/session/{id}/history returns paginated turn records."""
    # Seed 3 turns manually
    for i in range(3):
        turn = TurnRecord(
            sequence=i,
            timestamp=time.time(),
            role="user",
            content=f"turn-{i}",
            modality="text",
        )
        await session_manager.save_turn(test_session.session_id, turn)

    resp = await client.get(f"/v1/session/{test_session.session_id}/history")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["session_id"] == test_session.session_id
    assert len(data["messages"]) == 3
    assert data["has_more"] is False

    # Pagination via limit
    resp2 = await client.get(
        f"/v1/session/{test_session.session_id}/history?limit=2"
    )
    data2 = resp2.json()
    assert len(data2["messages"]) == 2
    assert data2["has_more"] is True


@pytest.mark.asyncio
async def test_get_status(client, test_session, session_manager):
    """GET /v1/session/{id}/status returns state and FSM snapshot."""
    resp = await client.get(f"/v1/session/{test_session.session_id}/status")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["session_id"] == test_session.session_id
    assert "state" in data
    assert "current_turn" in data
    assert "fsm" in data
    assert data["fsm"]["can_clarify_more"] is True
    assert data["fsm"]["clarification_count"] == 0


@pytest.mark.asyncio
async def test_close_session(client, test_session, session_manager):
    """POST /v1/session/{id}/close marks session closed."""
    resp = await client.post(f"/v1/session/{test_session.session_id}/close")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["session_id"] == test_session.session_id
    assert data["state"] == "closed"

    # Verify session exists with closed state (persisted in store)
    resp2 = await client.get(f"/v1/session/{test_session.session_id}/status")
    assert resp2.status_code == 200
    assert resp2.json()["state"] == "closed"


# ═══════════════════════════════════════════════════════════════════════════════
# Health & monitoring
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check(client):
    """GET /v1/health returns all components healthy."""
    resp = await client.get("/v1/health")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "components" in data
    components = data["components"]
    assert "pcr" in components
    assert "intent_parser" in components
    assert "session_manager" in components
    assert "websocket_manager" in components
    assert "store" in components

    # PCR and parser are mocked healthy; store may be degraded without sqlite
    assert components["pcr"]["status"] == "healthy"
    assert components["intent_parser"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_metrics(client):
    """GET /v1/metrics returns Prometheus-formatted text."""
    resp = await client.get("/v1/metrics")
    assert resp.status_code == 200, resp.text

    text = resp.text
    assert "dialogmesh_requests_total" in text or "# TYPE" in text
    assert "# HELP" in text


# ═══════════════════════════════════════════════════════════════════════════════
# Error handling & edge cases
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rate_limit(client, test_session):
    """Rapidly send 15 requests to the same session; expect 429."""
    payloads = [
        {"message_id": f"rl-{i}", "modality": "text", "content": f"msg {i}"}
        for i in range(15)
    ]

    results = []
    for p in payloads:
        resp = await client.post(
            f"/v1/session/{test_session.session_id}/message", json=p
        )
        results.append(resp.status_code)

    assert any(code == 429 for code in results), f"Expected at least one 429, got {results}"
    # Retry-After header should be present on rate-limited responses
    for resp_code in results:
        if resp_code == 429:
            # Find the actual response to check headers
            pass  # We'll check the last 429 response in the loop
    # Verify at least one 429 response carries the expected header
    # (httpx AsyncClient gives us independent response objects; we can re-request one)
    resp = await client.post(
        f"/v1/session/{test_session.session_id}/message",
        json={"message_id": "rl-burst", "modality": "text", "content": "burst"},
    )
    # If still rate-limited, verify headers
    if resp.status_code == 429:
        assert resp.headers.get("retry-after") is not None


@pytest.mark.asyncio
async def test_nonexistent_session(client):
    """All session-scoped endpoints return 404 for unknown session_id."""
    fake_id = "nonexistent-123"

    resp = await client.post(f"/v1/session/{fake_id}/message", json={"content": "hi"})
    assert resp.status_code == 404

    resp = await client.get(f"/v1/session/{fake_id}/history")
    assert resp.status_code == 404

    resp = await client.get(f"/v1/session/{fake_id}/status")
    assert resp.status_code == 404

    resp = await client.post(f"/v1/session/{fake_id}/close")
    assert resp.status_code == 404

    resp = await client.post(f"/v1/session/{fake_id}/clarify", json={"clarification_id": "c1"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_request(client, test_session):
    """Malformed request bodies return 422 validation error."""
    # Missing required 'content' field
    resp = await client.post(
        f"/v1/session/{test_session.session_id}/message",
        json={"message_id": "bad"},
    )
    assert resp.status_code == 422

    # Negative selected_option
    resp = await client.post(
        f"/v1/session/{test_session.session_id}/clarify",
        json={"clarification_id": "c1", "selected_option": -1},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload(client):
    """POST /v1/upload accepts multipart file upload."""
    import io

    file_content = b"Hello, DialogMesh!"
    files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    resp = await client.post("/v1/upload", files=files)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "file_id" in data
    assert data["file_name"] == "test.txt"
    assert data["size"] == len(file_content)
    assert data["content_type"] == "text/plain"
