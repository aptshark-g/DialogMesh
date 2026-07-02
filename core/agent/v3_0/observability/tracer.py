# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/tracer.py
───────────────────────────────────────
DialogMesh v3.0 异步链路追踪器。

用途：
  - 提供 async context manager 风格的 span 管理
  - 支持嵌套 span 和自动 parent_id 关联
  - 与 AsyncStructuredLogger 和 AsyncMetricsAggregator 集成

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from core.agent.v3_0.observability.models import Span, SpanStatus, TurnTrace

logger = logging.getLogger(__name__)

# 当前活跃 trace 的上下文变量（支持协程级别隔离）
_current_trace: ContextVar[Optional[TurnTrace]] = ContextVar("current_trace", default=None)
_current_span_stack: ContextVar[List[Span]] = ContextVar("current_span_stack", default=[])


class AsyncTracer:
    """
    异步链路追踪器。

    设计要点：
      - 使用 ContextVar 实现协程安全的 trace/span 上下文传递
      - 支持 async with 语法自动管理 span 生命周期
      - 支持最大 trace 数限制（LRU 淘汰）
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: List[TurnTrace] = []
        self._max_traces = max_traces
        self._lock = asyncio.Lock()

    # ── Trace 生命周期 ───────────────────────────────────────────

    async def start_turn(
        self, session_id: str, turn_index: int, query: str, metadata: Optional[Dict[str, Any]] = None
    ) -> TurnTrace:
        """开始一轮追踪。"""
        trace = TurnTrace(
            session_id=session_id,
            turn_index=turn_index,
            query=query,
            metadata=metadata or {},
        )
        _current_trace.set(trace)
        _current_span_stack.set([])

        async with self._lock:
            if len(self._traces) >= self._max_traces:
                self._traces.pop(0)
            self._traces.append(trace)

        logger.debug(f"[AsyncTracer] trace started: {trace.trace_id}")
        return trace

    async def end_turn(self) -> Optional[TurnTrace]:
        """结束当前轮追踪。"""
        trace = _current_trace.get()
        if trace is None:
            return None

        trace.finish()
        _current_trace.set(None)
        _current_span_stack.set([])

        logger.debug(f"[AsyncTracer] trace ended: {trace.trace_id}, duration={trace.total_duration_ms:.1f}ms")
        return trace

    def get_active_trace(self) -> Optional[TurnTrace]:
        """获取当前协程的活跃 trace。"""
        return _current_trace.get()

    # ── Span 生命周期（显式 API）────────────────────────────────

    async def start_span(
        self,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """开始一个 span（显式 API）。"""
        trace = _current_trace.get()
        if trace is None:
            raise RuntimeError("No active trace. Call start_turn() first.")

        stack = _current_span_stack.get()
        parent_id = stack[-1].span_id if stack else None

        span = trace.add_span(
            name=name,
            input_summary=input_summary,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        stack.append(span)
        _current_span_stack.set(stack)

        logger.debug(f"[AsyncTracer] span started: {name} ({span.span_id})")
        return span

    async def end_span(
        self,
        status: str = "ok",
        output_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Span]:
        """结束当前 span（栈顶）。"""
        stack = _current_span_stack.get()
        if not stack:
            return None

        span = stack.pop()
        _current_span_stack.set(stack)

        span.end_ns = time.time_ns()
        span.status = SpanStatus(status)
        span.output_summary = output_summary
        if metadata:
            span.metadata.update(metadata)

        logger.debug(f"[AsyncTracer] span ended: {span.name}, status={status}")
        return span

    async def annotate_span(self, key: str, value: Any) -> None:
        """为当前 span 添加注解。"""
        stack = _current_span_stack.get()
        if stack:
            stack[-1].metadata[key] = value

    # ── async context manager 支持 ───────────────────────────────

    def span(
        self,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> _SpanContextManager:
        """返回 async context manager 用于自动管理 span 生命周期。"""
        return _SpanContextManager(self, name, input_summary, metadata)

    # ── 查询 ───────────────────────────────────────────

    async def get_recent_traces(self, n: int = 10) -> List[TurnTrace]:
        """获取最近 N 条 trace。"""
        async with self._lock:
            return list(self._traces[-n:])

    async def get_trace_by_id(self, trace_id: str) -> Optional[TurnTrace]:
        """按 ID 查找 trace。"""
        async with self._lock:
            for t in self._traces:
                if t.trace_id == trace_id:
                    return t
            return None

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> AsyncTracer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class _SpanContextManager:
    """Span 异步上下文管理器。"""

    def __init__(
        self,
        tracer: AsyncTracer,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self._tracer = tracer
        self._name = name
        self._input_summary = input_summary
        self._metadata = metadata or {}
        self._span: Optional[Span] = None

    async def __aenter__(self) -> Span:
        self._span = await self._tracer.start_span(
            self._name, self._input_summary, self._metadata
        )
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        status = "error" if exc_type is not None else "ok"
        await self._tracer.end_span(
            status=status,
            output_summary="" if exc_type is None else str(exc_val),
        )
