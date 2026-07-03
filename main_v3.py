# -*- coding: utf-8 -*-
"""
main_v3.py
──────────
DialogMesh v3.0 主入口 — 生产级服务启动脚本。

用法:
  python main_v3.py                    # 默认加载 config/agent_config.yaml
  python main_v3.py --config ./custom_config.yaml
  python main_v3.py --host 0.0.0.0 --port 8000

特性：
- 使用 SystemBootstrap 执行 6 阶段启动流程
- 启动后创建 FastAPI 应用并绑定 WebSocket / HTTP 路由
- 支持 SIGINT/SIGTERM 优雅关闭
- 集成 uvicorn 作为 ASGI 服务器

配置优先级：
  1. 命令行参数
  2. 环境变量 (AGENT_*)
  3. 配置文件 (config/agent_config.yaml)
  4. 内置默认值

对应工程文档：
- ENGINEERING_INTEGRATION.md §4, §9
- ENGINEERING_SERVICE_LAYER.md

版本：3.0.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, Optional

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.agent.config.logging_setup import setup_logging
from core.agent.v3_0.system_bootstrap import SystemBootstrap, SystemStartupError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 全局系统实例（用于信号处理与生命周期管理）
# ═══════════════════════════════════════════════════════════════════════════════

_system_instance: Optional[Any] = None
_bootstrap_instance: Optional[SystemBootstrap] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 命令行参数
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="DialogMesh v3.0 Agent Service")
    parser.add_argument("--config", default=None, help="Path to agent_config.yaml")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--workers", type=int, default=1, help="Uvicorn workers")
    parser.add_argument("--reload", action="store_true", help="Auto reload (dev only)")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], help="Logging level")
    parser.add_argument("--no-service", action="store_true", help="Skip service layer, bootstrap only")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_signal(signum: int, frame: Any) -> None:
    """处理 SIGINT / SIGTERM，触发优雅关闭。"""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info(f"[Signal] Received {sig_name}, initiating graceful shutdown...")
    asyncio.create_task(_graceful_shutdown())


async def _graceful_shutdown() -> None:
    """执行优雅关闭。"""
    global _system_instance, _bootstrap_instance
    if _bootstrap_instance and _system_instance:
        try:
            await _bootstrap_instance.shutdown(_system_instance)
        except Exception as exc:
            logger.error(f"[Shutdown] Error during graceful shutdown: {exc}")
    logger.info("[Shutdown] Exiting")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 应用工厂
# ═══════════════════════════════════════════════════════════════════════════════

def _create_fastapi_app(system: Any) -> Any:
    """
    创建 FastAPI 应用并绑定所有 v3.0 路由。

    Args:
        system: DialogMeshSystem 实例

    Returns:
        FastAPI 应用实例
    """
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        logger.error(f"FastAPI not installed: {exc}")
        raise

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理：启动时系统已就绪，关闭时执行 cleanup。"""
        logger.info("[FastAPI] Lifespan startup")
        yield
        logger.info("[FastAPI] Lifespan shutdown")
        if _bootstrap_instance and _system_instance:
            await _bootstrap_instance.shutdown(_system_instance)

    app = FastAPI(
        title="DialogMesh v3.0",
        version="3.0.0",
        lifespan=lifespan,
    )

    # CORS — 显式列出允许来源，避免 WebSocket 握手 403
    # Starlette CORS 中间件: allow_origins=["*"] + allow_credentials=True 不兼容
    service_cfg = getattr(system, "service_layer", None)
    cors_origins = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    if service_cfg and hasattr(service_cfg, "config"):
        cfg_origins = service_cfg.config.get("cors_origins")
        if cfg_origins:
            cors_origins = cfg_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── v3 HTTP 路由（与前端 api.ts 对齐）────────────────────────────────

    @app.get("/v3/health")
    async def v3_health() -> dict:
        """v3 健康检查端点。"""
        health_status = getattr(system, "health", None)
        if health_status:
            return {
                "status": health_status.status,
                "version": health_status.version,
                "uptime_seconds": system.uptime_seconds if hasattr(system, "uptime_seconds") else 0,
                "components": {
                    k: {"status": v.status, "latency_ms": v.latency_ms, "message": v.message}
                    for k, v in health_status.components.items()
                },
            }
        return {"status": "ok", "version": "3.0.0"}

    @app.post("/v3/session")
    async def v3_create_session() -> dict:
        """v3 创建新会话。"""
        ctx_mgr = getattr(system, "context_manager", None)
        if ctx_mgr and hasattr(ctx_mgr, "create_session"):
            session = await ctx_mgr.create_session()
            session_id = getattr(session, "session_id", str(session))
            return {"session_id": session_id, "created_at": session.created_at if hasattr(session, "created_at") else ""}
        import uuid, time
        sid = str(uuid.uuid4())
        return {"session_id": sid, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}

    @app.post("/v3/session/{session_id}/message")
    async def v3_send_message(session_id: str, message: dict) -> dict:
        """v3 发送消息并获取回复。"""
        orch = getattr(system, "orchestrator", None)
        if not orch:
            return {"error": "orchestrator not available"}
        from core.agent.v3_0.data_models import UserMessage_v3
        user_msg = UserMessage_v3(session_id=session_id, content=message.get("content", ""))
        result = await orch.process_request(user_msg)
        return {
            "message_id": getattr(result, "message_id", ""),
            "status": getattr(result, "status", "ok"),
            "answer": result.answer,
            "latency_ms": result.latency_ms,
            "trace_log": result.trace_log,
        }

    @app.post("/v3/session/{session_id}/clarify")
    async def v3_clarify(session_id: str, req: dict) -> dict:
        """v3 提交澄清回复。"""
        orch = getattr(system, "orchestrator", None)
        if not orch:
            return {"error": "orchestrator not available"}
        return {"status": "ok", "session_id": session_id}

    @app.get("/v3/session/{session_id}/history")
    async def v3_history(session_id: str, limit: int = 50, offset: int = 0) -> dict:
        """v3 获取对话历史。"""
        ctx_mgr = getattr(system, "context_manager", None)
        if ctx_mgr and hasattr(ctx_mgr, "get_history"):
            history = await ctx_mgr.get_history(session_id, limit=limit, offset=offset)
            return {"session_id": session_id, "messages": history or [], "has_more": False}
        return {"session_id": session_id, "messages": [], "has_more": False}

    @app.get("/v3/session/{session_id}/status")
    async def v3_status(session_id: str) -> dict:
        """v3 获取会话状态。"""
        ctx_mgr = getattr(system, "context_manager", None)
        if ctx_mgr and hasattr(ctx_mgr, "get_status"):
            status = await ctx_mgr.get_status(session_id)
            if status:
                return {
                    "session_id": session_id,
                    "state": getattr(status, "state", "active"),
                    "current_turn": getattr(status, "current_turn", 0),
                    "pending_clarification": getattr(status, "pending_clarification", None),
                    "last_activity_at": getattr(status, "last_activity_at", ""),
                    "expires_at": getattr(status, "expires_at", ""),
                }
        return {
            "session_id": session_id,
            "state": "active",
            "current_turn": 0,
            "pending_clarification": None,
            "last_activity_at": "",
            "expires_at": "",
        }

    # ── v3 代理路由（LM Studio / Ollama / OpenAI 兼容）────────────────────

    @app.post("/v3/proxy/chat/completions")
    async def v3_proxy_chat_completions(request: dict) -> dict:
        """
        v3 OpenAI 兼容代理端点 — 转发到外部 LLM Provider。
        支持 LM Studio、Ollama、OpenAI 等。
        """
        import httpx
        from fastapi import HTTPException

        provider_url = request.get("_provider_url", "")
        api_key = request.get("_api_key", "")

        if not provider_url:
            raise HTTPException(status_code=400, detail="Missing _provider_url")

        # 剥离内部字段，保留标准 OpenAI API 格式
        payload = {k: v for k, v in request.items() if not k.startswith("_")}

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                resp = await client.post(
                    f"{provider_url.rstrip('/')}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"[Proxy] HTTP error from provider: {exc.response.status_code} {exc.response.text[:200]}")
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text[:500])
        except httpx.RequestError as exc:
            logger.error(f"[Proxy] Request error: {exc}")
            raise HTTPException(status_code=502, detail=f"Provider unreachable: {exc}")

    @app.get("/v3/proxy/models")
    async def v3_proxy_models(provider_url: str = "", api_key: str = "") -> dict:
        """v3 获取外部 Provider 的模型列表。"""
        import httpx
        from fastapi import HTTPException

        if not provider_url:
            raise HTTPException(status_code=400, detail="Missing provider_url query param")

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.get(
                    f"{provider_url.rstrip('/')}/v1/models",
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text[:500])
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Provider unreachable: {exc}")

    # ── v3 WebSocket 路由（与前端 api.ts 对齐）────────────────────────────

    @app.websocket("/v3/ws/{session_id}")
    async def v3_websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
        """v3 WebSocket 连接端点 — 支持实时消息流。"""
        await websocket.accept()
        logger.info(f"[WebSocket] Client connected: {session_id}")
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
                    continue

                if msg_type == "message":
                    content = data.get("content", "")
                    from core.agent.v3_0.data_models import UserMessage_v3
                    user_msg = UserMessage_v3(session_id=session_id, content=content)
                    orch = getattr(system, "orchestrator", None)
                    if orch and hasattr(orch, "process_request_stream"):
                        async for event in orch.process_request_stream(user_msg, session_id):
                            await websocket.send_json({
                                "type": event.event_type.value,
                                "payload": event.payload,
                                "timestamp": event.timestamp,
                            })
                    elif orch and hasattr(orch, "process_request"):
                        result = await orch.process_request(user_msg)
                        await websocket.send_json({
                            "type": "message",
                            "payload": {"answer": result.answer, "latency_ms": result.latency_ms},
                        })
                    else:
                        await websocket.send_json({"type": "error", "message": "orchestrator not available"})

                elif msg_type == "heartbeat":
                    pass

                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

        except WebSocketDisconnect:
            logger.info(f"[WebSocket] Client disconnected: {session_id}")
        except Exception as exc:
            logger.error(f"[WebSocket] Error for {session_id}: {exc}")
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    # ── 旧版兼容路由（保留）──────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict:
        """健康检查端点。"""
        health_status = getattr(system, "health", None)
        if health_status:
            return {
                "status": health_status.status,
                "version": health_status.version,
                "uptime_seconds": system.uptime_seconds if hasattr(system, "uptime_seconds") else 0,
                "components": {
                    k: {"status": v.status, "latency_ms": v.latency_ms, "message": v.message}
                    for k, v in health_status.components.items()
                },
            }
        return {"status": "unknown", "version": "3.0.0"}

    @app.get("/api/v1/status")
    async def api_status() -> dict:
        """API 状态端点。"""
        return {
            "name": "DialogMesh",
            "version": "3.0.0",
            "status": "running",
            "uptime_seconds": system.uptime_seconds if hasattr(system, "uptime_seconds") else 0,
        }

    @app.post("/api/v1/sessions")
    async def create_session() -> dict:
        """创建新会话。"""
        ctx_mgr = getattr(system, "context_manager", None)
        if ctx_mgr and hasattr(ctx_mgr, "create_session"):
            session = await ctx_mgr.create_session()
            return {"session_id": getattr(session, "session_id", str(session))}
        return {"error": "context_manager not available"}

    @app.post("/api/v1/sessions/{session_id}/messages")
    async def send_message(session_id: str, message: dict) -> dict:
        """发送消息并获取回复。"""
        orch = getattr(system, "orchestrator", None)
        if not orch:
            return {"error": "orchestrator not available"}

        from core.agent.v3_0.data_models import UserMessage_v3

        user_msg = UserMessage_v3(
            session_id=session_id,
            content=message.get("content", ""),
        )
        result = await orch.process_request(user_msg)
        return {
            "answer": result.answer,
            "latency_ms": result.latency_ms,
            "trace_log": result.trace_log,
        }

    # ── WebSocket 路由 ──────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket 连接端点 — 支持实时消息流。"""
        await websocket.accept()
        session_id = None
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "init":
                    session_id = data.get("session_id")
                    if not session_id:
                        ctx_mgr = getattr(system, "context_manager", None)
                        if ctx_mgr and hasattr(ctx_mgr, "create_session"):
                            sess = await ctx_mgr.create_session()
                            session_id = getattr(sess, "session_id", str(sess))
                    await websocket.send_json({
                        "type": "session_created",
                        "session_id": session_id,
                    })
                    continue

                if msg_type == "message" and session_id:
                    content = data.get("content", "")
                    from core.agent.v3_0.data_models import UserMessage_v3

                    user_msg = UserMessage_v3(session_id=session_id, content=content)
                    orch = getattr(system, "orchestrator", None)
                    if orch and hasattr(orch, "process_request_stream"):
                        async for event in orch.process_request_stream(user_msg, session_id):
                            await websocket.send_json({
                                "type": event.event_type.value,
                                "payload": event.payload,
                                "timestamp": event.timestamp,
                            })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "orchestrator not available",
                        })

        except WebSocketDisconnect:
            logger.info(f"[WebSocket] Client disconnected: {session_id}")
        except Exception as exc:
            logger.error(f"[WebSocket] Error: {exc}")
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    """DialogMesh v3.0 异步主入口。"""
    args = parse_args()

    if args.version:
        print("DialogMesh v3.0.0")
        sys.exit(0)

    # 设置日志
    setup_logging(level=args.log_level.upper())
    logger.info("=" * 50)
    logger.info("DialogMesh v3.0 Starting...")
    logger.info(f"  Config: {args.config or 'config/agent_config.yaml'}")
    logger.info(f"  Host: {args.host}:{args.port}")
    logger.info(f"  Workers: {args.workers}")
    logger.info("=" * 50)

    # 注册信号处理
    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    # 6 阶段启动
    global _system_instance, _bootstrap_instance
    bootstrap = SystemBootstrap(config_path=args.config)
    _bootstrap_instance = bootstrap

    try:
        system = await bootstrap.start()
        _system_instance = system
    except SystemStartupError as exc:
        logger.error(f"[Fatal] System startup failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"[Fatal] Unexpected startup error: {exc}", exc_info=True)
        sys.exit(1)

    # 如果指定 --no-service，仅启动系统后进入 idle 循环
    if args.no_service:
        logger.info("[Mode] Bootstrap only, no service layer. Press Ctrl+C to exit.")
        while True:
            await asyncio.sleep(3600)
        return

    # 创建 FastAPI 应用
    try:
        app = _create_fastapi_app(system)
    except Exception as exc:
        logger.error(f"[Fatal] FastAPI app creation failed: {exc}")
        await bootstrap.shutdown(system)
        sys.exit(1)

    # 启动 uvicorn — 使用 Server + Config 避免嵌套 asyncio.run()
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Install with: pip install uvicorn[standard]")
        await bootstrap.shutdown(system)
        sys.exit(1)

    logger.info(f"[Service] Starting HTTP server on {args.host}:{args.port}")
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level=args.log_level,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
