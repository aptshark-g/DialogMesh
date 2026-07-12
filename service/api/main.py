# -*- coding: utf-8 -*-
"""
service/api/main.py
───────────────────
DialogMesh FastAPI 应用入口（工厂模式）。

- create_app() 支持 override_dependencies 用于测试注入
- 生命周期：startup 初始化所有单例，shutdown 优雅关闭
- 中间件顺序：Error → CORS → Tenant → RateLimit → Logging
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Dict, Any, Callable

from fastapi import FastAPI, Request, WebSocket, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from service.api.routes import router as v1_router
from service.api.dependencies import (
    init_dependencies,
    get_session_manager,
    get_websocket_manager,
    get_agent_service,
)
from service.api.middleware import (
    ErrorHandlerMiddleware,
    TenantIDMiddleware,
    RateLimiterMiddleware,
    RequestLoggingMiddleware,
)
from service.api.websocket import WebSocketManager
from service.async_session_manager import AsyncSessionManager

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser

logger = logging.getLogger(__name__)

# SQLite store 为可选依赖（未安装 aiosqlite 时回退到内存）
try:
    from service.stores.async_sqlite import AsyncSQLiteSessionStore
    _HAS_SQLITE = True
except ImportError:  # pragma: no cover
    _HAS_SQLITE = False


# ═══════════════════════════════════════════════════════════════════════════════
# create_app 工厂
# ═══════════════════════════════════════════════════════════════════════════════

def create_app(
    override_dependencies: Optional[Dict[Callable, Callable]] = None,
    db_path: Optional[str] = None,
) -> FastAPI:
    """
    DialogMesh FastAPI 应用工厂。

    Args:
        override_dependencies: FastAPI dependency_overrides 字典，用于测试注入。
        db_path: SQLite 数据库路径，默认项目根目录 data/sessions.db。
    """
    app = FastAPI(
        title="DialogMesh API",
        version="2.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 测试依赖覆盖
    if override_dependencies:
        for dep, override in override_dependencies.items():
            app.dependency_overrides[dep] = override

    # ── Startup / Shutdown ───────────────────────────────────────────────────

    @app.on_event("startup")
    async def startup_event():
        logger.info("DialogMesh API starting up...")

        # 初始化持久化存储
        _db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "sessions.db",
        )
        os.makedirs(os.path.dirname(_db_path), exist_ok=True)

        if _HAS_SQLITE:
            store = AsyncSQLiteSessionStore(db_path=_db_path)
        else:
            store = None
            logger.warning("aiosqlite not installed, running without persistent store")

        # 初始化会话管理器
        session_manager = AsyncSessionManager(store=store)
        await session_manager.start()

        # 初始化核心引擎
        pcr = RuleBasedPCR()
        pcr.warm_up({})
        parser = IntentParser()

        # 初始化 WebSocket 管理器
        ws_manager = WebSocketManager()
        await ws_manager.start()

        # 注入全局单例
        init_dependencies(pcr, parser, session_manager, ws_manager)

        logger.info("DialogMesh API startup complete")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("DialogMesh API shutting down...")

        # 关闭 WebSocket 管理器
        try:
            ws_manager = get_websocket_manager()
            await ws_manager.stop()
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning("WebSocketManager shutdown error: %s", exc)

        # 关闭会话管理器
        try:
            session_manager = get_session_manager()
            await session_manager.stop()
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning("SessionManager shutdown error: %s", exc)

        # 关闭 PCR
        try:
            agent_service = get_agent_service()
            agent_service.pcr.shutdown()
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning("PCR shutdown error: %s", exc)

        logger.info("DialogMesh API shutdown complete")

    # ── Middleware stack（按顺序：Error → CORS → Tenant → RateLimit → Logging）───

    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantIDMiddleware)
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # ── Routes ───────────────────────────────────────────────────────────────

    app.include_router(v1_router)

    # ── WebSocket endpoint ───────────────────────────────────────────────────

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(
        websocket: WebSocket,
        session_id: str,
        ws_manager: WebSocketManager = Depends(get_websocket_manager),
    ):
        conn_id = await ws_manager.connect(session_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    from service.protocol.events import EventSerializer, EventBuilder
                    event = EventSerializer.deserialize(data)
                    if event.event_type == "pong":
                        ws_manager.update_pong(conn_id)
                    elif event.event_type == "ping":
                        await ws_manager.send_to_connection(
                            conn_id, EventBuilder.pong(),
                        )
                    elif event.event_type == "get_status":
                        try:
                            agent_service = get_agent_service()
                            session = await agent_service.session_manager.get_session(
                                session_id
                            )
                            if session:
                                await ws_manager.send_to_connection(
                                    conn_id,
                                    EventBuilder.state_change(
                                        session_id, "", session.state,
                                    ),
                                )
                        except Exception as exc:
                            logger.warning("WS get_status error: %s", exc)
                except Exception as exc:
                    logger.warning("WS message handling error: %s", exc)
        except Exception as exc:
            # WebSocketDisconnect or other close events
            logger.debug("WebSocket connection closed: %s", exc)
        finally:
            await ws_manager.disconnect_by_id(conn_id)

    # ── Health endpoint (without /v1/ prefix) ────────────────────────────────

    @app.get("/health")
    async def root_health():
        return {"status": "ok", "version": "2.4.0"}

    # ── Global exception handler ─────────────────────────────────────────────

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
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

    return app
