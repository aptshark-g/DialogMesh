# -*- coding: utf-8 -*-
"""
service/api/websocket.py
───────────────────────
WebSocket 连接管理器：连接池、心跳、广播、事件序列化。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from service.protocol.events import WebSocketEvent, EventBuilder, EventSerializer

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Connection 内部模型
# ═══════════════════════════════════════════════════════════════════════════════

class _Connection:
    """单个 WebSocket 连接的元数据。"""

    def __init__(self, connection_id: str, websocket: WebSocket, session_id: str) -> None:
        self.connection_id = connection_id
        self.websocket = websocket
        self.session_id = session_id
        self.last_pong = time.time()
        self.miss_count = 0
        self.active = True


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocketManager
# ═══════════════════════════════════════════════════════════════════════════════

class WebSocketManager:
    """
    WebSocket 连接管理器。

    - 连接池: Dict[session_id, List[connection_id]]
    - 心跳: 30 秒 ping/pong，3 次未响应自动断开
    - 所有事件通过 EventBuilder 构造，EventSerializer 序列化
    """

    HEARTBEAT_INTERVAL: float = 30.0
    HEARTBEAT_TIMEOUT: float = 90.0   # 3 * 30s
    MAX_MISSED_PONGS: int = 3

    def __init__(self) -> None:
        self._connections: Dict[str, _Connection] = {}   # conn_id -> _Connection
        self._session_map: Dict[str, List[str]] = {}     # session_id -> [conn_id]
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台心跳检测任务。"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocketManager heartbeat started")

    async def stop(self) -> None:
        """优雅关闭：取消心跳任务，关闭所有连接。"""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        async with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._session_map.clear()

        for conn in conns:
            try:
                await conn.websocket.close()
            except Exception:
                pass
        logger.info("WebSocketManager stopped")

    # ── Connection management ────────────────────────────────────────────────

    async def connect(self, session_id: str, websocket: WebSocket) -> str:
        """注册新连接，返回 connection_id。"""
        await websocket.accept()
        conn_id = f"{session_id}-{uuid.uuid4().hex[:8]}"
        async with self._lock:
            self._connections[conn_id] = _Connection(conn_id, websocket, session_id)
            self._session_map.setdefault(session_id, []).append(conn_id)
        logger.info("WebSocket connected: %s for session %s", conn_id, session_id)
        return conn_id

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """通过 session_id + websocket 对象移除连接。"""
        conn_id: Optional[str] = None
        async with self._lock:
            for cid, conn in self._connections.items():
                if conn.session_id == session_id and conn.websocket is websocket:
                    conn_id = cid
                    break
        if conn_id:
            await self._disconnect_by_id(conn_id)

    async def disconnect_by_id(self, connection_id: str) -> None:
        """通过 connection_id 移除连接。"""
        async with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn is None:
                return
            conn.active = False
            sess_conns = self._session_map.get(conn.session_id, [])
            if connection_id in sess_conns:
                sess_conns.remove(connection_id)
            if not sess_conns:
                self._session_map.pop(conn.session_id, None)
        try:
            await conn.websocket.close()
        except Exception:
            pass
        logger.info("WebSocket disconnected: %s", connection_id)

    # ── Messaging ──────────────────────────────────────────────────────────────

    async def broadcast(self, session_id: str, event: WebSocketEvent) -> None:
        """向某会话的所有连接广播事件。"""
        data = EventSerializer.serialize(event)
        async with self._lock:
            conn_ids = list(self._session_map.get(session_id, []))

        for cid in conn_ids:
            conn = self._connections.get(cid)
            if conn is None or not conn.active:
                continue
            try:
                await conn.websocket.send_text(data)
            except Exception:
                conn.active = False
                asyncio.create_task(self._disconnect_by_id(cid))

    async def send_to_connection(self, connection_id: str, event: WebSocketEvent) -> bool:
        """向单个连接发送事件。"""
        conn = self._connections.get(connection_id)
        if conn is None or not conn.active:
            return False
        try:
            await conn.websocket.send_text(EventSerializer.serialize(event))
            return True
        except Exception:
            conn.active = False
            asyncio.create_task(self._disconnect_by_id(connection_id))
            return False

    # ── Heartbeat ────────────────────────────────────────────────────────────

    def update_pong(self, connection_id: str) -> None:
        """客户端响应 pong 时更新状态。"""
        conn = self._connections.get(connection_id)
        if conn:
            conn.last_pong = time.time()
            conn.miss_count = 0

    def get_connection_count(self, session_id: str) -> int:
        """返回某会话的活跃连接数。"""
        return len(self._session_map.get(session_id, []))

    async def _heartbeat_loop(self) -> None:
        """后台心跳循环：每 30 秒发送 ping，检查超时。"""
        while True:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break

            now = time.time()
            dead: List[str] = []

            async with self._lock:
                for cid, conn in list(self._connections.items()):
                    if not conn.active:
                        dead.append(cid)
                        continue

                    # 检查是否超过 90 秒未收到 pong
                    if now - conn.last_pong > self.HEARTBEAT_TIMEOUT:
                        conn.miss_count += 1
                        if conn.miss_count >= self.MAX_MISSED_PONGS:
                            dead.append(cid)
                            continue

                    # 发送应用层 ping
                    try:
                        ping_event = EventBuilder.ping()
                        await conn.websocket.send_text(
                            EventSerializer.serialize(ping_event)
                        )
                    except Exception:
                        conn.miss_count += 1
                        if conn.miss_count >= self.MAX_MISSED_PONGS:
                            dead.append(cid)

            for cid in dead:
                await self._disconnect_by_id(cid)
