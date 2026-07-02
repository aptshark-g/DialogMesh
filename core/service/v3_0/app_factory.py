# -*- coding: utf-8 -*-
"""
core/service/v3_0/app_factory.py
────────────────────────────────
DialogMesh Service Layer v3.0 — FastAPI 应用工厂。

用途：
- 组装所有 v3.0 组件（AgentService、SessionManager、WebSocketManager、API路由）。
- 提供 create_app_v3() 工厂函数，一键创建可运行的 FastAPI 应用。
- 支持配置注入（ServiceConfig）和生命周期管理（startup/shutdown）。

设计原则：
- 工厂函数接收可选依赖，便于测试时 mock。
- 如果没有 FastAPI，抛出清晰的 ImportError。
- startup/shutdown 事件处理所有组件的异步启动与清理。

版本：3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Optional

try:
    from fastapi import FastAPI
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None

from core.agent.v3_0.context_manager.manager import ContextManager
from core.agent.v3_0.context_manager.store import InMemoryContextStore
from core.service.v3_0.data_models import ServiceConfig
from core.service.v3_0.agent_service import AgentService_v3
from core.service.v3_0.session_manager import SessionManager_v3
from core.service.v3_0.websocket_manager import WebSocketManager_v3
from core.service.v3_0.api import DialogMeshAPI_v3
from core.service.v3_0.middleware import setup_middleware

logger = logging.getLogger(__name__)


def create_app_v3(
    config: Optional[ServiceConfig] = None,
    context_manager: Optional[ContextManager] = None,
    provider_manager: Optional[Any] = None,
) -> FastAPI:
    """
    创建 DialogMesh v3.0 FastAPI 应用实例。

    Args:
        config: 服务配置。默认使用 ServiceConfig()。
        context_manager: 自定义 ContextManager。默认使用 InMemoryContextStore。
        provider_manager: 自定义 LLM ProviderManager。默认 None。

    Returns:
        已注册所有路由和中间件的 FastAPI 应用。

    Raises:
        ImportError: 如果 FastAPI 未安装。
    """
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required for DialogMesh Service v3.0. "
            "Install with: pip install fastapi uvicorn"
        )

    cfg = config or ServiceConfig()

    # 1. 创建底层组件
    if context_manager is None:
        context_manager = ContextManager(store=InMemoryContextStore())

    session_manager = SessionManager_v3(
        context_manager=context_manager,
        ttl_seconds=cfg.session_ttl_seconds,
        eviction_interval_seconds=cfg.eviction_interval_seconds,
    )

    websocket_manager = WebSocketManager_v3(
        heartbeat_interval_seconds=cfg.ws_heartbeat_interval_seconds,
        max_connections_per_session=cfg.ws_max_connections_per_session,
    )

    agent_service = AgentService_v3(
        session_manager=session_manager,
        provider_manager=provider_manager,
    )

    # 2. 创建 FastAPI 应用
    app = FastAPI(
        title="DialogMesh API v3.0",
        description="DialogMesh Service Layer v3.0 — FastAPI + WebSocket",
        version="3.0.0",
    )

    # 3. 注册中间件
    setup_middleware(
        app,
        enable_cors=cfg.enable_cors,
        cors_origins=cfg.cors_origins,
    )

    # 4. 注册 API 路由
    api = DialogMeshAPI_v3(
        agent_service=agent_service,
        websocket_manager=websocket_manager,
    )
    api.register(app)

    # 5. 生命周期事件
    @app.on_event("startup")
    async def startup() -> None:
        logger.info("DialogMesh v3.0 startup (host=%s, port=%d)", cfg.host, cfg.port)
        await agent_service.start()
        await websocket_manager.start()
        logger.info("DialogMesh v3.0 startup complete")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("DialogMesh v3.0 shutdown...")
        await websocket_manager.stop()
        await agent_service.stop()
        logger.info("DialogMesh v3.0 shutdown complete")

    # 6. 根路由
    @app.get("/")
    async def root() -> dict:
        return {
            "name": "DialogMesh API v3.0",
            "version": "3.0.0",
            "docs": "/docs",
            "health": "/v3/health",
            "metrics": "/v3/metrics",
        }

    logger.info("DialogMesh v3.0 FastAPI app created")
    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== app_factory self-test ===")
        try:
            app = create_app_v3()
            assert app is not None
            print("[PASS] create_app_v3 returned FastAPI instance")
        except ImportError:
            print("[SKIP] FastAPI not installed, skipping app_factory test")
        logger.info("=== app_factory self-test passed ===")

    asyncio.run(_self_test())
