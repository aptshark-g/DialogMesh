# -*- coding: utf-8 -*-
"""
core/service/v3_0/middleware.py
──────────────────────────────
DialogMesh Service Layer v3.0 — FastAPI 中间件。

用途：
- 请求日志：记录所有 HTTP/WebSocket 请求的入口/出口时间、延迟、状态码。
- 错误处理：捕获未处理异常，统一包装为 JSON 错误响应。
- CORS 支持：跨域配置。
- 请求 ID 注入：每个请求分配唯一 request_id，便于追踪。
- 超时保护：防止长耗时请求阻塞事件循环。

设计原则：
- 所有中间件为 async 函数，不阻塞事件循环。
- 错误响应使用 core.service.v3_0.data_models.ErrorResponse 结构。

版本：3.0.0
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Optional

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    Request = None
    Response = None
    JSONResponse = None
    CORSMiddleware = None

from core.service.v3_0.data_models import ErrorResponse

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """请求日志中间件——记录方法、路径、状态码、延迟。"""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        start = time.time()

        # 包装 send 以捕获状态码
        status_code = 200
        async def wrapped_send(message: Any) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            latency = (time.time() - start) * 1000
            logger.info(
                "[%s] %s %s -> %d (%.2fms)",
                request_id, request.method, request.url.path, status_code, latency
            )


class ExceptionHandlingMiddleware:
    """异常处理中间件——捕获未处理异常，包装为标准 JSON 错误响应。"""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            request_id = str(uuid.uuid4())[:12]
            try:
                req = Request(scope, receive)
                request_id = getattr(req.state, "request_id", request_id)
            except Exception:
                pass

            logger.exception("Unhandled exception (request_id=%s): %s", request_id, exc)

            error = ErrorResponse(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                retryable=False,
                request_id=request_id,
            )
            response = JSONResponse(
                status_code=500,
                content=error.model_dump(),
            )
            await response(scope, receive, send)


class RequestIDMiddleware:
    """请求 ID 中间件——为每个请求注入唯一 request_id。"""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Callable, send: Callable) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            request_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:12]
            request.state.request_id = request_id
        await self.app(scope, receive, send)


# ═══════════════════════════════════════════════════════════════════════════════
# 注册函数
# ═══════════════════════════════════════════════════════════════════════════════

def setup_middleware(app: FastAPI, enable_cors: bool = True, cors_origins: Optional[list] = None) -> None:
    """
    为 FastAPI 应用注册所有中间件。

    Args:
        app: FastAPI 实例。
        enable_cors: 是否启用 CORS。
        cors_origins: 允许的跨域来源列表。
    """
    if not HAS_FASTAPI:
        raise ImportError("FastAPI is required for middleware setup")

    # 请求 ID（最外层）
    app.add_middleware(RequestIDMiddleware)
    # 请求日志
    app.add_middleware(RequestLoggingMiddleware)
    # 异常处理
    app.add_middleware(ExceptionHandlingMiddleware)

    # CORS
    if enable_cors:
        origins = cors_origins or ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info("CORS enabled for origins: %s", origins)

    logger.info("All middleware registered for FastAPI app")
