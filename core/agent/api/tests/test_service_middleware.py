# -*- coding: utf-8 -*-
"""B4-1-P1: v6_app 薄中间件层测试 — 限流/背压/会话归置/监控路由."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from core.agent.api.service_middleware import (
    RateLimitMiddleware,
    QueueGuardMiddleware,
    SessionMiddleware,
    ServiceLayer,
    install_service_middleware,
    reset_service_layer,
    router as service_router,
)


@pytest.fixture
def layer():
    from core.agent.service.rate_limiter import RateLimiter
    from core.agent.service.session_manager import SessionManager
    from core.agent.service.request_queue import RequestQueue
    sl = ServiceLayer(
        rate_limiter=RateLimiter(default_tenant_rps=2.0, session_burst=2),
        session_manager=SessionManager(ttl_seconds=3600),
        request_queue=RequestQueue(max_global_depth=2, per_session_max_depth=1),
    )
    reset_service_layer(sl)
    yield sl
    reset_service_layer(None)


@pytest.fixture
def app(layer):
    app = FastAPI()
    install_service_middleware(app, service_layer=layer)
    app.include_router(service_router)

    @app.get("/ping")
    async def ping():
        return {"pong": True}
    return app


def test_ping_passes_through(app, layer):
    with TestClient(app) as tc:
        resp = tc.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"pong": True}


def test_rate_limit_disabled_by_default(app, layer):
    """单机模式默认关闭限流（2026-08-07）— 快速连打不 429."""
    with TestClient(app) as tc:
        for _ in range(10):
            assert tc.get("/ping").status_code == 200
        assert layer._blocked == 0


def test_rate_limit_429_and_retry_after(app, layer):
    # 限流中间件默认关闭（单机模式）→ 本测试显式开启
    from fastapi import FastAPI
    rate_app = FastAPI()
    install_service_middleware(rate_app, service_layer=layer, enable_rate_limit=True)

    @rate_app.get("/ping")
    async def ping():
        return {"pong": True}
    with TestClient(rate_app) as tc:
        # burst=2 → 第 3 个请求应 429
        assert tc.get("/ping").status_code == 200
        assert tc.get("/ping").status_code == 200
        resp = tc.get("/ping")
        assert resp.status_code == 429
        assert "retry-after" in {k.lower() for k in resp.headers}
        assert resp.json()["error"] == "rate_limited"
        assert layer._blocked == 1


def test_rate_limit_per_session_bucket(app, layer):
    """不同会话独立限流桶 — 会话 A 打满不影响会话 B."""
    from fastapi import FastAPI
    rate_app = FastAPI()
    install_service_middleware(rate_app, service_layer=layer, enable_rate_limit=True)

    @rate_app.get("/ping")
    async def ping():
        return {"pong": True}
    headers_a = {"x-session-id": "sess-a"}
    headers_b = {"x-session-id": "sess-b"}
    with TestClient(rate_app) as tc:
        assert tc.get("/ping", headers=headers_a).status_code == 200
        assert tc.get("/ping", headers=headers_a).status_code == 200
        assert tc.get("/ping", headers=headers_a).status_code == 429
        assert tc.get("/ping", headers=headers_b).status_code == 200
        assert tc.get("/ping", headers=headers_b).status_code == 200


def test_service_session_roundtrip(app, layer):
    # 连续 3 个请求会打满匿名桶(burst=2) → 用宽松限流层测会话生命周期
    from core.agent.service.rate_limiter import RateLimiter
    from core.agent.service.session_manager import SessionManager
    from core.agent.service.request_queue import RequestQueue
    permissive = ServiceLayer(
        rate_limiter=RateLimiter(default_tenant_rps=1000.0, session_burst=1000),
        session_manager=SessionManager(ttl_seconds=3600),
        request_queue=RequestQueue(max_global_depth=1000),
    )
    reset_service_layer(permissive)
    app = FastAPI()
    install_service_middleware(app, service_layer=permissive)
    app.include_router(service_router)
    with TestClient(app) as tc:
        created = tc.post("/v6/service/session", json={"user_id": "u1"})
        assert created.status_code == 200
        sid = created.json()["session_id"]

        status = tc.get(f"/v6/service/session/{sid}")
        assert status.status_code == 200
        assert status.json()["active"] is True

        closed = tc.post(f"/v6/service/session/{sid}/close")
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

        gone = tc.get(f"/v6/service/session/{sid}")
        assert gone.status_code == 404


def test_session_middleware_attaches_state(app, layer):
    """X-Session-Id 已知会话 → request.state.service_session_id 有值."""
    seen = {}

    app = FastAPI()
    install_service_middleware(app, service_layer=layer)

    @app.get("/check-session")
    async def check_session(request: Request):
        seen["sid"] = getattr(request.state, "service_session_id", None)
        return {"ok": True}
    app.include_router(service_router)

    with TestClient(app) as tc:
        created = tc.post("/v6/service/session").json()["session_id"]
        tc.get("/check-session", headers={"x-session-id": created})
        assert seen["sid"] == created
        # 未知会话 → None（不隐式创建）
        tc.get("/check-session", headers={"x-session-id": "nope-123"})
        assert seen["sid"] is None


def test_stats_endpoint(layer):
    app = FastAPI()
    install_service_middleware(app, service_layer=layer, enable_rate_limit=True)

    @app.get("/ping")
    async def ping():
        return {"ok": True}
    app.include_router(service_router)

    with TestClient(app) as tc:
        tc.get("/ping")
        stats = tc.get("/v6/service/stats").json()
        assert stats["rate_limiter"]["tenant_buckets"] >= 1
        assert stats["blocked_429"] == 0
        assert "queue_max_depth" in stats


def test_queue_guard_503_when_saturated(layer):
    """队列满 → 503 + Retry-After（不破坏 200 正常路径）. """
    app = FastAPI()
    app.add_middleware(QueueGuardMiddleware, service_layer=layer)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    # 手动塞满队列（不启动 worker）
    import asyncio
    from core.agent.service.request_queue import QueuedRequest

    async def _fill():
        layer.request_queue._ensure_queue()
        for i in range(layer.request_queue.max_global_depth):
            await layer.request_queue._queue.put(QueuedRequest(
                priority=1, timestamp=0, session_id=f"s{i}",
                request_id=f"r{i}", payload={},
                future=asyncio.get_running_loop().create_future(),
            ))

    with TestClient(app) as tc:
        # TestClient portal 事件循环内填充（与请求同 loop，避免跨 loop 竞态）
        tc.portal.call(_fill)
        resp = tc.get("/ping")
        assert resp.status_code == 503
        assert resp.json()["error"] == "queue_saturated"
        assert "retry-after" in {k.lower() for k in resp.headers}
        assert layer._saturated == 1


def test_middleware_ordering_rate_before_queue(layer):
    """限流先于背压: 双重饱和时返回 429（限流在外层）. """
    app = FastAPI()
    install_service_middleware(app, service_layer=layer, enable_rate_limit=True)
    layer._blocked = 0

    @app.get("/ping")
    async def ping():
        return {"ok": True}
    app.include_router(service_router)

    with TestClient(app) as tc:
        tc.get("/ping")
        tc.get("/ping")
        resp = tc.get("/ping")  # burst=2 已耗尽 → 429（外层次序）
        assert resp.status_code == 429
