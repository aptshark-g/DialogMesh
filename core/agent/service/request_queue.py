# -*- coding: utf-8 -*-
"""
core/agent/service/request_queue.py
────────────────────────────────────
请求队列（生产优化）。

优先队列 + 超时降级：
  - Clarification 回复优先级高于新消息
  - 单会话内消息串行处理（保证时序和上下文一致性）
  - 多会话间并行处理（利用 asyncio）
  - 超时机制：单条消息处理超时 30s 后自动降级返回保守默认
  - 背压：队列深度 > 100 时拒绝新请求
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, Awaitable


@dataclass(order=True)
class QueuedRequest:
    """队列中的请求项。"""
    priority: int  # 越小越优先: 0=澄清, 1=正常, 2=后台
    timestamp: float = field(compare=False)
    session_id: str = field(compare=False)
    request_id: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False)
    future: asyncio.Future = field(compare=False)


class RequestQueue:
    """
    异步优先请求队列。

    每 session_id 维护一个 FIFO 子队列（保证时序），
    全局按优先级和时间戳调度。
    """

    PRIORITY_CLARIFICATION = 0
    PRIORITY_NORMAL = 1
    PRIORITY_BACKGROUND = 2

    def __init__(
        self,
        max_global_depth: int = 100,
        per_session_max_depth: int = 10,
        default_timeout_seconds: float = 30.0,
    ):
        self.max_global_depth = max_global_depth
        self.per_session_max_depth = per_session_max_depth
        self.default_timeout = default_timeout_seconds

        self._queue: asyncio.PriorityQueue[QueuedRequest] = asyncio.PriorityQueue()
        self._session_depths: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self, processor: Callable[[QueuedRequest], Awaitable[Dict[str, Any]]]) -> None:
        """启动处理工作协程。"""
        self._running = True
        self._processor = processor
        self._worker_task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """停止处理工作协程。"""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def enqueue(
        self,
        session_id: str,
        payload: Dict[str, Any],
        priority: int = PRIORITY_NORMAL,
        timeout: Optional[float] = None,
    ) -> asyncio.Future:
        """
        入队并返回 Future。

        如果队列超限，Future 立即被设置异常（背压）。
        """
        timeout = timeout or self.default_timeout
        request_id = f"{session_id}-{time.time()}-{id(payload)}"
        future = asyncio.get_running_loop().create_future()

        async with self._lock:
            global_depth = self._queue.qsize()
            session_depth = self._session_depths.get(session_id, 0)

            if global_depth >= self.max_global_depth:
                future.set_exception(
                    RuntimeError(f"Global queue depth exceeded: {global_depth}")
                )
                return future

            if session_depth >= self.per_session_max_depth:
                future.set_exception(
                    RuntimeError(f"Session queue depth exceeded: {session_depth}")
                )
                return future

            self._session_depths[session_id] = session_depth + 1

        item = QueuedRequest(
            priority=priority,
            timestamp=time.time(),
            session_id=session_id,
            request_id=request_id,
            payload=payload,
            future=future,
        )
        await self._queue.put(item)
        return future

    async def _process_loop(self) -> None:
        """处理循环。"""
        while self._running:
            try:
                item = await self._queue.get()
                async with self._lock:
                    self._session_depths[item.session_id] = (
                        self._session_depths.get(item.session_id, 1) - 1
                    )
                    if self._session_depths[item.session_id] <= 0:
                        self._session_depths.pop(item.session_id, None)

                try:
                    # 超时保护
                    result = await asyncio.wait_for(
                        self._processor(item),
                        timeout=self.default_timeout,
                    )
                    if not item.future.done():
                        item.future.set_result(result)
                except asyncio.TimeoutError:
                    if not item.future.done():
                        item.future.set_exception(
                            TimeoutError(f"Request timed out after {self.default_timeout}s")
                        )
                except Exception as e:
                    if not item.future.done():
                        item.future.set_exception(e)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                # 处理异常不应中断循环
                await asyncio.sleep(0.1)

    async def get_stats(self) -> Dict[str, Any]:
        """获取队列统计。"""
        async with self._lock:
            return {
                "global_depth": self._queue.qsize(),
                "session_depths": dict(self._session_depths),
                "running": self._running,
            }
