# -*- coding: utf-8 -*-
"""
service/api/middleware.py
────────────────────────
DialogMesh FastAPI 中间件栈。

挂载顺序（由 main.py 控制）：
    ErrorHandler → CORS(fastapi内置) → TenantID → RateLimiter → RequestLogging
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Token Bucket (限流内部实现)
# ═══════════════════════════════════════════════════════════════════════════════

class _TokenBucket:
    """线程/协程安全的令牌桶（外部需加锁）。"""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.time()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# ErrorHandlerMiddleware — 最外层异常捕获
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """捕获所有未处理异常，返回标准化 JSON 错误响应。"""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.exception("Unhandled exception in request: %s", exc)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "retryable": True,
                    }
                },
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TenantIDMiddleware — 提取多租户标识
# ═══════════════════════════════════════════════════════════════════════════════

class TenantIDMiddleware(BaseHTTPMiddleware):
    """从请求头提取 X-Tenant-ID，默认 "default"，存入 request.state。"""

    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-ID", "default")
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response


# ═══════════════════════════════════════════════════════════════════════════════
# RateLimiterMiddleware — 令牌桶限流
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    令牌桶限流中间件。

    - 每个 tenant 默认 10 RPS
    - 每个 session 突发 5 条
    - 超限返回 429 + Retry-After 头
    """

    DEFAULT_TENANT_RPS: float = 10.0
    DEFAULT_SESSION_BURST: float = 5.0

    def __init__(
        self,
        app,
        tenant_rps: float = DEFAULT_TENANT_RPS,
        session_burst: float = DEFAULT_SESSION_BURST,
    ) -> None:
        super().__init__(app)
        self.tenant_rps = tenant_rps
        self.session_burst = session_burst
        self._tenant_buckets: Dict[str, _TokenBucket] = {}
        self._session_buckets: Dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        # 只限流 /v1/ 和 /ws/ 前缀的 API 路径
        path = request.url.path
        if not (path.startswith("/v1/") or path.startswith("/ws/")):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "default")
        session_id = request.path_params.get("session_id", "global")

        async with self._lock:
            if tenant_id not in self._tenant_buckets:
                self._tenant_buckets[tenant_id] = _TokenBucket(
                    self.tenant_rps, self.tenant_rps
                )
            if session_id not in self._session_buckets:
                self._session_buckets[session_id] = _TokenBucket(
                    self.session_burst, self.session_burst
                )

            tenant_ok = self._tenant_buckets[tenant_id].consume(1.0)
            session_ok = self._session_buckets[session_id].consume(1.0)

        if not tenant_ok or not session_ok:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "1"},
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please retry later.",
                        "retryable": True,
                        "retry_after_ms": 1000,
                    }
                },
            )

        return await call_next(request)


# ═══════════════════════════════════════════════════════════════════════════════
# RequestLoggingMiddleware — 请求日志与延迟记录
# ═══════════════════════════════════════════════════════════════════════════════

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的方法、路径、tenant、session、延迟、状态码。"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        method = request.method
        path = request.url.path
        tenant_id = getattr(request.state, "tenant_id", "default")
        session_id = request.path_params.get("session_id", "-")

        try:
            response = await call_next(request)
            latency_ms = (time.time() - start) * 1000
            logger.info(
                "[HTTP] %s %s tenant=%s session=%s status=%d latency=%.2fms",
                method, path, tenant_id, session_id, response.status_code, latency_ms,
            )
            # 注入响应头（调试用）
            response.headers["X-Response-Time-Ms"] = f"{latency_ms:.2f}"
            return response
        except Exception as exc:
            latency_ms = (time.time() - start) * 1000
            logger.error(
                "[HTTP] %s %s tenant=%s session=%s ERROR latency=%.2fms exc=%s",
                method, path, tenant_id, session_id, latency_ms, exc,
            )
            raise
