# -*- coding: utf-8 -*-
"""
core/service/v3_0/websocket_manager.py
──────────────────────────────────────
DialogMesh Service Layer v3.0 — WebSocket 连接管理器。

用途：
- 管理 session_id → WebSocket 连接的多对多映射（一个会话支持多个客户端连接）。
- 提供广播、单发、心跳检测、连接清理等异步操作。
- 封装所有 WebSocket 事件序列化与发送逻辑，隔离业务与传输层。
- 与 core.agent.v3_0.data_models.WebSocketEvent 深度集成，统一事件格式。

设计原则：
- 纯 asyncio，无线程锁。
- 自动清理断连 WebSocket，避免内存泄漏。
- 支持按 session 广播和按 connection 单发。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

try:
    from fastapi import WebSocket, WebSocketDisconnect
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    WebSocket = None
    WebSocketDisconnect = Exception

from core.agent.v3_0.data_models import WebSocketEvent, WebSocketEventBuilder, EventType

logger = logging.getLogger(__name__)


class WebSocketManager_v3:
    """
    WebSocket 连接管理器 v3.0。

    职责：
    1. 连接注册/注销：session_id → Set[WebSocket]。
    2. 事件广播：向某个会话的所有连接发送事件。
    3. 心跳维持：周期性发送 heartbeat 事件，检测僵尸连接。
    4. 自动清理：发送失败时自动移除连接。
    5. 全局统计：连接数、广播次数、失败次数。
    """

    def __init__(
        self,
        heartbeat_interval_seconds: float = 30.0,
        max_connections_per_session: int = 5,
    ) -> None:
        self.heartbeat_interval = heartbeat_interval_seconds
        self.max_connections_per_session = max_connections_per_session

        # session_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> session_id 反向映射
        self._session_map: Dict[WebSocket, str] = {}

        # 并发安全
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        # 统计
        self._total_broadcasts = 0
        self._total_failures = 0
        self._total_connections_accepted = 0
        self._total_connections_closed = 0

    # ── 生命周期 ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动心跳任务。"""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocketManager_v3 started (heartbeat=%.1fs)", self.heartbeat_interval)

    async def stop(self) -> None:
        """停止心跳任务，关闭所有连接。"""
        self._running = False
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # 关闭所有活跃连接
        async with self._lock:
            all_conns = list(self._session_map.keys())
        for ws in all_conns:
            try:
                await ws.close()
            except Exception:
                pass
        async with self._lock:
            self._connections.clear()
            self._session_map.clear()
        logger.info("WebSocketManager_v3 stopped, all connections closed")

    # ── 连接管理 ───────────────────────────────────────────────────────────

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """注册 WebSocket 连接到指定会话。"""
        if not HAS_FASTAPI:
            raise RuntimeError("FastAPI is required for WebSocket support")
        try:
            await websocket.accept()
            async with self._lock:
                if session_id not in self._connections:
                    self._connections[session_id] = set()
                # 限制单会话连接数
                if len(self._connections[session_id]) >= self.max_connections_per_session:
                    oldest = next(iter(self._connections[session_id]))
                    self._connections[session_id].discard(oldest)
                    self._session_map.pop(oldest, None)
                    logger.warning("Max connections reached for session %s, dropping oldest", session_id)
                self._connections[session_id].add(websocket)
                self._session_map[websocket] = session_id
                self._total_connections_accepted += 1
            logger.debug("WebSocket connected: session=%s, total_conns=%d", session_id, len(self._session_map))
        except Exception as exc:
            logger.error(f"connect failed for session {session_id}: {exc}")
            raise

    async def disconnect(self, websocket: WebSocket) -> None:
        """注销单个 WebSocket 连接。"""
        try:
            async with self._lock:
                session_id = self._session_map.pop(websocket, None)
                if session_id and session_id in self._connections:
                    self._connections[session_id].discard(websocket)
                    if not self._connections[session_id]:
                        del self._connections[session_id]
                self._total_connections_closed += 1
            logger.debug("WebSocket disconnected: session=%s", session_id)
        except Exception as exc:
            logger.error(f"disconnect failed: {exc}")

    async def disconnect_session(self, session_id: str) -> int:
        """注销会话的所有连接，返回关闭数量。"""
        try:
            async with self._lock:
                conns = self._connections.pop(session_id, set())
                for ws in conns:
                    self._session_map.pop(ws, None)
                count = len(conns)
                self._total_connections_closed += count
            # 在锁外关闭，避免持有锁时 I/O
            for ws in conns:
                try:
                    await ws.close()
                except Exception:
                    pass
            logger.info("Session %s disconnected, closed %d connections", session_id, count)
            return count
        except Exception as exc:
            logger.error(f"disconnect_session failed for {session_id}: {exc}")
            return 0

    # ── 事件发送 ───────────────────────────────────────────────────────────

    async def send_event(self, websocket: WebSocket, event: WebSocketEvent) -> bool:
        """向单个 WebSocket 发送事件，失败时返回 False。"""
        if not HAS_FASTAPI:
            return False
        try:
            raw = await event.async_serialize()
            await websocket.send_text(raw)
            return True
        except Exception as exc:
            logger.warning("send_event failed to single websocket: %s", exc)
            self._total_failures += 1
            return False

    async def broadcast_to_session(self, session_id: str, event: WebSocketEvent) -> int:
        """向会话的所有连接广播事件，返回成功发送数。"""
        if not HAS_FASTAPI:
            return 0
        try:
            async with self._lock:
                conns = list(self._connections.get(session_id, set()))
            if not conns:
                return 0

            raw = await event.async_serialize()
            dead: List[WebSocket] = []
            success = 0

            for ws in conns:
                try:
                    await ws.send_text(raw)
                    success += 1
                except Exception:
                    dead.append(ws)

            # 清理失效连接
            if dead:
                async with self._lock:
                    for ws in dead:
                        self._session_map.pop(ws, None)
                        if session_id in self._connections:
                            self._connections[session_id].discard(ws)
                    if session_id in self._connections and not self._connections[session_id]:
                        del self._connections[session_id]
                self._total_failures += len(dead)

            self._total_broadcasts += 1
            logger.debug("Broadcast to session %s: sent=%d, dead=%d", session_id, success, len(dead))
            return success
        except Exception as exc:
            logger.error(f"broadcast_to_session failed for {session_id}: {exc}")
            self._total_failures += 1
            return 0

    async def send_to_session(
        self,
        session_id: str,
        event_type: EventType,
        payload: Dict[str, Any],
    ) -> int:
        """构造事件并广播到会话。"""
        event = (
            WebSocketEvent.builder(event_type, session_id)
            .with_payload_dict(payload)
            .build()
        )
        return await self.broadcast_to_session(session_id, event)

    # ── 快捷事件构造 ───────────────────────────────────────────────────────

    async def send_message_event(
        self, session_id: str, content: str, role: str = "agent"
    ) -> int:
        """发送标准消息事件。"""
        return await self.send_to_session(
            session_id,
            EventType.MESSAGE,
            {"content": content, "role": role, "timestamp": time.time()},
        )

    async def send_task_update(
        self, session_id: str, task_graph_summary: Dict[str, Any]
    ) -> int:
        """发送任务图更新事件。"""
        return await self.send_to_session(
            session_id,
            EventType.TASK_UPDATE,
            {"task_graph": task_graph_summary, "timestamp": time.time()},
        )

    async def send_error(
        self, session_id: str, code: str, message: str, retryable: bool = False
    ) -> int:
        """发送错误事件。"""
        return await self.send_to_session(
            session_id,
            EventType.ERROR,
            {"code": code, "message": message, "retryable": retryable, "timestamp": time.time()},
        )

    async def send_clarification(
        self, session_id: str, clarification_id: str, message: str, suggestions: List[str]
    ) -> int:
        """发送澄清请求事件。"""
        return await self.send_to_session(
            session_id,
            EventType.CLARIFICATION,
            {
                "clarification_id": clarification_id,
                "message": message,
                "suggestions": suggestions,
                "timestamp": time.time(),
            },
        )

    async def send_heartbeat(self, session_id: str) -> int:
        """发送心跳事件。"""
        return await self.send_to_session(
            session_id,
            EventType.HEARTBEAT,
            {"timestamp": time.time()},
        )

    async def send_system_status(self, session_id: str, status: str, detail: Optional[str] = None) -> int:
        """发送系统状态事件。"""
        payload: Dict[str, Any] = {"status": status, "timestamp": time.time()}
        if detail:
            payload["detail"] = detail
        return await self.send_to_session(session_id, EventType.SYSTEM_STATUS, payload)

    # ── 心跳循环 ───────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """后台心跳检测循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._run_heartbeat_round()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat loop error: %s", exc)
                await asyncio.sleep(1)

    async def _run_heartbeat_round(self) -> None:
        """执行一轮心跳：向所有会话发送 heartbeat，清理断连。"""
        try:
            async with self._lock:
                sessions = {sid: list(conns) for sid, conns in self._connections.items()}

            dead_ws: List[WebSocket] = []
            for session_id, conns in sessions.items():
                for ws in conns:
                    try:
                        await ws.send_text('{"type":"heartbeat","ts":' + str(time.time()) + '}')
                    except Exception:
                        dead_ws.append(ws)

            if dead_ws:
                async with self._lock:
                    for ws in dead_ws:
                        sid = self._session_map.pop(ws, None)
                        if sid and sid in self._connections:
                            self._connections[sid].discard(ws)
                            if not self._connections[sid]:
                                del self._connections[sid]
                logger.debug("Heartbeat removed %d dead connections", len(dead_ws))
        except Exception as exc:
            logger.error(f"_run_heartbeat_round failed: {exc}")

    # ── 统计与诊断 ───────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """获取 WebSocket 统计信息。"""
        async with self._lock:
            return {
                "total_connections_accepted": self._total_connections_accepted,
                "total_connections_closed": self._total_connections_closed,
                "active_connections": len(self._session_map),
                "active_sessions": len(self._connections),
                "total_broadcasts": self._total_broadcasts,
                "total_failures": self._total_failures,
                "heartbeat_interval": self.heartbeat_interval,
                "max_connections_per_session": self.max_connections_per_session,
            }

    async def get_session_connection_count(self, session_id: str) -> int:
        """获取指定会话的当前连接数。"""
        async with self._lock:
            return len(self._connections.get(session_id, set()))


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== WebSocketManager_v3 self-test ===")

        mgr = WebSocketManager_v3(heartbeat_interval_seconds=1.0, max_connections_per_session=2)
        await mgr.start()

        # 1. 统计初始状态
        stats = await mgr.get_stats()
        assert stats["active_connections"] == 0
        print(f"[PASS] initial stats: {stats}")

        # 2. 模拟连接（无真实 WebSocket 时跳过）
        if not HAS_FASTAPI:
            print("[SKIP] FastAPI not installed, skipping WebSocket connect tests")
        else:
            # 创建 mock WebSocket 较难，测试仅验证无异常
            pass

        # 3. 停止
        await mgr.stop()
        stats = await mgr.get_stats()
        assert stats["active_connections"] == 0
        print(f"[PASS] stopped stats: {stats}")

        logger.info("=== WebSocketManager_v3 self-tests passed ===")

    asyncio.run(_self_test())
