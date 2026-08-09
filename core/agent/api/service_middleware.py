# -*- coding: utf-8 -*-
"""B4-1-P1: v6_app 薄中间件层 — rate_limiter/request_queue/session_manager。

服务层从"整层"降级为"组件库 + 协议资产"后，缓冲能力由 v6_app 内聚接入
（事实轻服务层）：
  - RateLimitMiddleware : 双层令牌桶限流（租户 + 会话），超限 429 + Retry-After
    （2026-08-07: 默认关闭 — 单机模式限流是噪音；DM_SERVICE_ENABLE_RATE_LIMIT=1
      开启，多租户/分布式部署（G5 触发条件）时再启用）
  - QueueGuardMiddleware : 请求队列背压（饱和 503 + Retry-After）
  - SessionMiddleware    : 会话归置（X-Session-Id → SessionManager 触达/TTL）
  - /v6/service/*        : 会话创建/状态/关闭 + 监控统计（A18 可观测）

默认宽松（不破坏现有直连语义），阈值可通过 DM_SERVICE_* env 收紧。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class ServiceLayer:
    """轻服务层组件库 — v6_app 内聚的缓冲能力集合。"""

    def __init__(
        self,
        rate_limiter=None,
        session_manager=None,
        request_queue=None,
    ):
        from core.agent.service.rate_limiter import RateLimiter
        from core.agent.service.session_manager import SessionManager
        from core.agent.service.request_queue import RequestQueue

        self.rate_limiter = rate_limiter or RateLimiter(
            default_tenant_rps=_env_float("DM_SERVICE_TENANT_RPS", 100.0),
            # B5 (2026-08-07): 默认宽松 — 前端页面加载瞬时 10+ 并发请求
            # （health/profile/trace/abc/mind/graph/tree/objects），burst=20 连
            # 一次页面加载都撑不住 → 429 被前端 catch(null) 吞掉 → 图谱/任务
            # 页"一直空"。提到 60（refill 仍 1/s，防刷屏语义不变）。
            session_burst=_env_int("DM_SERVICE_SESSION_BURST", 60),
            queue_max_depth=_env_int("DM_SERVICE_QUEUE_MAX", 100),
        )
        self.session_manager = session_manager or SessionManager(
            ttl_seconds=_env_int("DM_SERVICE_SESSION_TTL", 3600),
        )
        self.request_queue = request_queue or RequestQueue(
            max_global_depth=_env_int("DM_SERVICE_QUEUE_MAX", 100),
            per_session_max_depth=_env_int("DM_SERVICE_SESSION_QUEUE_MAX", 10),
            default_timeout_seconds=_env_float("DM_SERVICE_TIMEOUT", 30.0),
        )
        self._blocked: int = 0        # 429 计数（监控）
        self._saturated: int = 0      # 503 计数（监控）
        self._sessions_seen: int = 0

    # ── 中间件行为 ────────────────────────────────────────────────────────

    def check_rate(self, request: Request) -> Optional[float]:
        """限流检查. 返回 retry_after_seconds（None = 放行）。"""
        tenant = request.headers.get("x-tenant-id", "default")
        session = request.headers.get("x-session-id", "anonymous")
        allowed, retry_after, reason = self.rate_limiter.check(tenant, session)
        if allowed:
            return None
        self._blocked += 1
        logger.info("rate-limited: tenant=%s session=%s reason=%s",
                    tenant, session[:12], reason)
        return retry_after if retry_after else 1.0

    async def check_queue(self) -> Optional[float]:
        """队列背压检查. 返回 retry_after_seconds（None = 放行）。"""
        try:
            stats = await self.request_queue.get_stats()
            if stats["global_depth"] >= self.request_queue.max_global_depth:
                self._saturated += 1
                return 1.0
        except Exception as e:
            logger.debug("queue check skipped: %s", e)
        return None

    def ensure_session(self, request: Request) -> None:
        """会话归置: 有 X-Session-Id 则触达/TTL 刷新；无则置 anonymous。"""
        session_id = request.headers.get("x-session-id", "").strip()
        request.state.service_session_id = None
        if not session_id:
            return
        try:
            sess = self.session_manager.get_session(session_id)
            if sess is None:
                # 未知会话 — 不隐式创建（创建走 /v6/service/session）
                return
            request.state.service_session_id = sess.session_id
            self._sessions_seen += 1
        except Exception as e:
            logger.debug("session ensure skipped: %s", e)

    # ── 统计（A18 可观测）────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        rate_stats = self.rate_limiter.get_stats()
        return {
            "rate_limiter": {
                "tenant_buckets": len(rate_stats.get("tenant_buckets", {})),
                "session_buckets": len(rate_stats.get("session_buckets", {})),
            },
            "blocked_429": self._blocked,
            "saturated_503": self._saturated,
            "sessions_seen": self._sessions_seen,
            "session_ttl_seconds": self.session_manager.ttl_seconds,
            "queue_max_depth": self.request_queue.max_global_depth,
        }


_service_layer: Optional[ServiceLayer] = None


def get_service_layer() -> ServiceLayer:
    global _service_layer
    if _service_layer is None:
        _service_layer = ServiceLayer()
    return _service_layer


def reset_service_layer(layer: Optional[ServiceLayer] = None) -> None:
    """测试用：重置单例（可注入自定义 layer）。"""
    global _service_layer
    _service_layer = layer


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 中间件
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimitMiddleware:
    """HTTP 限流中间件（双层令牌桶）。

    默认关闭（单机模式无意义，反而把页面加载的并发请求打成 429）；
    通过 env DM_SERVICE_ENABLE_RATE_LIMIT=1 或 enabled=True 开启。
    """

    def __init__(
        self,
        app,
        service_layer: Optional[ServiceLayer] = None,
        enabled: Optional[bool] = None,
    ):
        self.app = app
        self.layer = service_layer or get_service_layer()
        if enabled is None:
            enabled = os.environ.get("DM_SERVICE_ENABLE_RATE_LIMIT", "0") == "1"
        self.enabled = enabled

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not self.enabled:
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request
        request = Request(scope, receive)
        retry_after = self.layer.check_rate(request)
        if retry_after is not None:
            await _send_json(scope, send, 429, {
                "error": "rate_limited",
                "retry_after": retry_after,
            }, {"Retry-After": str(int(retry_after))})
            return
        await self.app(scope, receive, send)


class QueueGuardMiddleware:
    """请求队列背压中间件（饱和 503）。"""

    def __init__(self, app, service_layer: Optional[ServiceLayer] = None):
        self.app = app
        self.layer = service_layer or get_service_layer()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        retry_after = await self.layer.check_queue()
        if retry_after is not None:
            await _send_json(scope, send, 503, {
                "error": "queue_saturated",
                "retry_after": retry_after,
            }, {"Retry-After": str(int(retry_after))})
            return
        await self.app(scope, receive, send)


class SessionMiddleware:
    """会话归置中间件（X-Session-Id → request.state.service_session_id）。"""

    def __init__(self, app, service_layer: Optional[ServiceLayer] = None):
        self.app = app
        self.layer = service_layer or get_service_layer()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request
        request = Request(scope, receive)
        self.layer.ensure_session(request)
        await self.app(scope, receive, send)


async def _send_json(scope, send, status_code: int, payload: dict,
                     headers: Optional[dict] = None) -> None:
    """纯 ASGI JSON 响应（避免依赖 BaseHTTPMiddleware 流式坑）。"""
    import json as _json
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response_headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    for k, v in (headers or {}).items():
        response_headers.append((k.encode("latin-1"), str(v).encode("latin-1")))
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": response_headers,
    })
    await send({"type": "http.response.body", "body": body})


# ═══════════════════════════════════════════════════════════════════════════════
# /v6/service/* 路由（会话归置 + 监控）
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/v6/service", tags=["service-layer"])


@router.get("/stats")
async def service_stats(layer: ServiceLayer = Depends(get_service_layer)):
    """轻服务层监控统计（限流桶/429/503/会话）。"""
    return layer.stats()


@router.post("/session")
async def create_service_session(
    request: Request,
    layer: ServiceLayer = Depends(get_service_layer),
):
    """创建服务会话（返回 session_id 供 X-Session-Id 使用）。"""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    user_id = body.get("user_id")
    tenant_id = request.headers.get("x-tenant-id", "default")
    sess = layer.session_manager.create_session(
        tenant_id=tenant_id, user_id=user_id)
    return {"session_id": sess.session_id, "status": "active",
            "expires_at": sess.expires_at}


@router.get("/session/{session_id}")
async def service_session_status(
    session_id: str,
    layer: ServiceLayer = Depends(get_service_layer),
):
    sess = layer.session_manager.get_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": sess.session_id,
        "tenant_id": sess.tenant_id,
        "user_id": sess.user_id,
        "expires_at": sess.expires_at,
        "active": time.time() < sess.expires_at,
    }


@router.post("/session/{session_id}/close")
async def close_service_session(
    session_id: str,
    layer: ServiceLayer = Depends(get_service_layer),
):
    """关闭会话并释放限流桶资源。"""
    layer.session_manager.close_session(session_id)
    layer.rate_limiter.release_session(session_id)
    return {"session_id": session_id, "status": "closed"}


def install_service_middleware(
    app,
    service_layer: Optional[ServiceLayer] = None,
    enable_rate_limit: Optional[bool] = None,
) -> ServiceLayer:
    """将薄中间件层挂到 FastAPI app（协议顺序: 限流 → 背压 → 会话）。

    enable_rate_limit: None=读 env DM_SERVICE_ENABLE_RATE_LIMIT（默认关）,
    True/False=显式覆盖（测试用）。
    """
    layer = service_layer or get_service_layer()
    # Starlette: 后 add 的在外层 — 先加会话，再加背压，最后加限流
    app.add_middleware(SessionMiddleware, service_layer=layer)
    app.add_middleware(QueueGuardMiddleware, service_layer=layer)
    app.add_middleware(RateLimitMiddleware, service_layer=layer, enabled=enable_rate_limit)
    return layer
