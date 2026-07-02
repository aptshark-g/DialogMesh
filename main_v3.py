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

    # CORS
    service_cfg = getattr(system, "service_layer", None)
    cors_origins = ["*"]
    if service_cfg and hasattr(service_cfg, "config"):
        cors_origins = service_cfg.config.get("cors_origins", ["*"])

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── HTTP 路由 ───────────────────────────────────────────────────────

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

    # 启动 uvicorn
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Install with: pip install uvicorn[standard]")
        await bootstrap.shutdown(system)
        sys.exit(1)

    logger.info(f"[Service] Starting HTTP server on {args.host}:{args.port}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    asyncio.run(main())
