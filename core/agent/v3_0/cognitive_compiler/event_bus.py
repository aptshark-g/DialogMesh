# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/event_bus.py
────────────────────────────────────────────────
Cognitive Tree 异步事件通知系统。

提供订阅/发布/过滤/分发能力，支持异步回调与协程回调。
所有事件通过内存队列处理，设计为单进程内的事件总线。

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CogEventType(Enum):
    """Cognitive Tree 事件类型 — 设计文档 §6.3"""
    NODE_CREATED = "node_created"
    NODE_ACTIVATED = "node_activated"
    NODE_VALIDATED = "node_validated"
    NODE_INVALIDATED = "node_invalidated"
    NODE_SUPERSEDED = "node_superseded"
    NODE_ARCHIVED = "node_archived"
    EDGE_CREATED = "edge_created"
    CONFLICT_DETECTED = "conflict_detected"
    STATUS_CHANGED = "status_changed"
    BRANCH_SWITCHED = "branch_switched"
    USER_FEEDBACK = "user_feedback"
    SESSION_ENDED = "session_ended"


@dataclass
class Event:
    """认知事件 — 事件总线中的消息单元"""
    type: CogEventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class Subscription:
    """事件订阅 — 绑定过滤条件与回调函数"""
    sub_id: str
    event_filter: Dict[str, Any]
    callback: Callable[[Event], Any]


class EventBus:
    """
    Cognitive Tree 异步事件通知系统。

    职责:
      - 事件订阅与取消订阅
      - 异步事件队列处理
      - 基于过滤条件的精确分发
      - 回调异常隔离（单个回调失败不影响其他订阅者）
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    def start(self) -> None:
        """启动后台事件处理循环。"""
        try:
            if not self._running:
                self._running = True
                self._worker_task = asyncio.create_task(
                    self._process_loop(), name="event_bus_worker"
                )
                logger.debug("EventBus started")
        except Exception as e:
            logger.error("EventBus start failed: %s", e)
            raise

    def stop(self) -> None:
        """停止事件处理循环。"""
        try:
            self._running = False
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                logger.debug("EventBus stopped")
        except Exception as e:
            logger.error("EventBus stop failed: %s", e)
            raise

    def subscribe(
        self,
        event_type: str,
        event_filter: Dict[str, Any],
        callback: Callable[[Event], Any],
    ) -> str:
        """
        订阅指定类型的事件。

        Args:
            event_type: 事件类型字符串（如 "node_created"）
            event_filter: 过滤条件，仅当事件 data 包含匹配键值时才触发
            callback: 回调函数，支持同步或异步

        Returns:
            sub_id: 订阅唯一标识，用于取消订阅
        """
        try:
            sub_id = str(uuid.uuid4())
            sub = Subscription(
                sub_id=sub_id, event_filter=event_filter, callback=callback
            )
            self._subscribers[event_type].append(sub)
            logger.debug(
                "Subscribed to %s with filter %s (sub_id=%s)",
                event_type, event_filter, sub_id,
            )
            return sub_id
        except Exception as e:
            logger.error("Event subscribe failed: %s", e)
            raise

    def unsubscribe(self, sub_id: str) -> bool:
        """取消订阅。"""
        try:
            for event_type, subs in self._subscribers.items():
                for i, sub in enumerate(subs):
                    if sub.sub_id == sub_id:
                        subs.pop(i)
                        logger.debug(
                            "Unsubscribed sub_id=%s from %s", sub_id, event_type
                        )
                        return True
            logger.warning("Unsubscribe: sub_id %s not found", sub_id)
            return False
        except Exception as e:
            logger.error("Event unsubscribe failed: %s", e)
            raise

    def publish(self, event: Event) -> None:
        """发布事件到异步队列。"""
        try:
            self._queue.put_nowait(event)
        except Exception as e:
            logger.error("Event publish failed: %s", e)

    async def _process_loop(self) -> None:
        """后台事件处理循环。"""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.debug("EventBus process loop cancelled")
                break
            except Exception as e:
                logger.error("Event processing loop error: %s", e)

    async def _dispatch(self, event: Event) -> None:
        """将事件分发到匹配的订阅者。"""
        try:
            subs = self._subscribers.get(event.type.value, [])
            if not subs:
                return

            for sub in subs:
                if self._match_filter(event, sub.event_filter):
                    try:
                        if asyncio.iscoroutinefunction(sub.callback):
                            asyncio.create_task(
                                self._safe_callback(sub.callback, event)
                            )
                        else:
                            sub.callback(event)
                    except Exception as e:
                        logger.error(
                            "Dispatch callback error for sub_id=%s: %s",
                            sub.sub_id, e,
                        )
        except Exception as e:
            logger.error("Event dispatch failed: %s", e)

    async def _safe_callback(
        self, callback: Callable[[Event], Any], event: Event
    ) -> None:
        """安全执行回调，捕获异常。"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        except Exception as e:
            logger.error("Callback execution error: %s", e)

    def _match_filter(self, event: Event, event_filter: Dict[str, Any]) -> bool:
        """检查事件数据是否满足过滤条件。"""
        for key, value in event_filter.items():
            if event.data.get(key) != value:
                return False
        return True
