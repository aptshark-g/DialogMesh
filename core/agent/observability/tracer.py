# -*- coding: utf-8 -*-
"""
core/agent/observability/tracer.py
───────────────────────────────────
Turn-level distributed tracing.

设计要点：
  - Span：单个阶段（如 COMPILE, ROUTE, WINDOW, EXECUTE, FALLBACK）
  - Trace：一轮对话的完整 span 集合
  - 零外部依赖：不依赖 OpenTelemetry / Jaeger
  - 轻量：仅记录时间戳、阶段名、输入/输出摘要、状态
  - 与 Telemetry 门面集成：通过 start_span() / end_span() API
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """单个追踪阶段。"""
    name: str
    start_ns: int
    end_ns: Optional[int] = None
    status: str = "ok"          # "ok" | "error" | "timeout" | "skipped"
    input_summary: str = ""     # 输入摘要（截断）
    output_summary: str = ""    # 输出摘要（截断）
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def duration_ms(self) -> float:
        """耗时（毫秒）。"""
        if self.end_ns is None:
            return 0.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "input_summary": self.input_summary[:100],
            "output_summary": self.output_summary[:100],
            "metadata": self.metadata,
            "parent_id": self.parent_id,
        }


@dataclass
class TurnTrace:
    """一轮对话的完整链路追踪。"""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str = ""
    turn_index: int = 0
    query: str = ""
    spans: List[Span] = field(default_factory=list)
    start_ns: int = field(default_factory=lambda: time.time_ns())
    end_ns: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_duration_ms(self) -> float:
        if self.end_ns is None:
            return (time.time_ns() - self.start_ns) / 1_000_000.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    @property
    def has_error(self) -> bool:
        return any(s.status == "error" for s in self.spans)

    def add_span(self, name: str, **kwargs) -> Span:
        """添加并返回一个 Span。"""
        span = Span(name=name, start_ns=time.time_ns(), **kwargs)
        self.spans.append(span)
        return span

    def finish(self) -> None:
        """标记 trace 结束。"""
        self.end_ns = time.time_ns()
        # 自动关闭未关闭的 span
        for span in self.spans:
            if span.end_ns is None:
                span.end_ns = self.end_ns
                span.status = "timeout" if span.status == "ok" else span.status

    def get_span(self, name: str) -> Optional[Span]:
        """按名称查找第一个匹配 span。"""
        for s in self.spans:
            if s.name == name:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id[:8] + "...",
            "turn_index": self.turn_index,
            "query": self.query[:100],
            "total_duration_ms": round(self.total_duration_ms, 3),
            "has_error": self.has_error,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"TurnTrace({self.trace_id}, turn={self.turn_index}, "
            f"spans={len(self.spans)}, total_ms={self.total_duration_ms:.1f})"
        )


class Tracer:
    """
    链路追踪器。
    负责创建和管理 TurnTrace，支持嵌套 span。
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: List[TurnTrace] = []
        self._active_trace: Optional[TurnTrace] = None
        self._active_span_stack: List[Span] = []
        self._max_traces = max_traces

    # ── Trace 生命周期 ───────────────────────────────────────────

    def start_turn(self, session_id: str, turn_index: int, query: str) -> TurnTrace:
        """开始一轮追踪。"""
        trace = TurnTrace(
            session_id=session_id,
            turn_index=turn_index,
            query=query,
        )
        self._active_trace = trace
        self._active_span_stack.clear()

        # LRU 淘汰
        if len(self._traces) >= self._max_traces:
            self._traces.pop(0)
        self._traces.append(trace)

        return trace

    def end_turn(self) -> Optional[TurnTrace]:
        """结束当前轮追踪。"""
        if self._active_trace is None:
            return None
        self._active_trace.finish()
        trace = self._active_trace
        self._active_trace = None
        self._active_span_stack.clear()
        return trace

    def get_active_trace(self) -> Optional[TurnTrace]:
        return self._active_trace

    # ── Span 生命周期 ───────────────────────────────────────────

    def start_span(self, name: str, input_summary: str = "", metadata: Optional[Dict[str, Any]] = None) -> Span:
        """开始一个 span。"""
        if self._active_trace is None:
            raise RuntimeError("No active trace. Call start_turn() first.")

        parent_id = self._active_span_stack[-1].span_id if self._active_span_stack else None
        span = self._active_trace.add_span(
            name=name,
            input_summary=input_summary,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self._active_span_stack.append(span)
        return span

    def end_span(self, status: str = "ok", output_summary: str = "", metadata: Optional[Dict[str, Any]] = None) -> Optional[Span]:
        """结束当前 span（栈顶）。"""
        if not self._active_span_stack:
            return None
        span = self._active_span_stack.pop()
        span.end_ns = time.time_ns()
        span.status = status
        span.output_summary = output_summary
        if metadata:
            span.metadata.update(metadata)
        return span

    def annotate_span(self, key: str, value: Any) -> None:
        """为当前活跃 span 添加注解。"""
        if self._active_span_stack:
            self._active_span_stack[-1].metadata[key] = value

    # ── 查询 ───────────────────────────────────────────

    def get_recent_traces(self, n: int = 10) -> List[TurnTrace]:
        """获取最近 N 轮 trace。"""
        return self._traces[-n:]

    def get_trace_by_turn(self, session_id: str, turn_index: int) -> Optional[TurnTrace]:
        """按会话和轮次查找 trace。"""
        for trace in reversed(self._traces):
            if trace.session_id == session_id and trace.turn_index == turn_index:
                return trace
        return None

    def get_slow_spans(self, threshold_ms: float = 100.0) -> List[Span]:
        """获取所有慢 span。"""
        slow = []
        for trace in self._traces:
            for span in trace.spans:
                if span.duration_ms > threshold_ms:
                    slow.append(span)
        return slow

    def get_error_traces(self) -> List[TurnTrace]:
        """获取所有含错误的 trace。"""
        return [t for t in self._traces if t.has_error]

    def get_summary(self) -> Dict[str, Any]:
        """获取追踪统计。"""
        if not self._traces:
            return {"traces": 0}

        total_spans = sum(len(t.spans) for t in self._traces)
        total_ms = sum(t.total_duration_ms for t in self._traces)
        error_count = sum(1 for t in self._traces if t.has_error)

        # 按 span 名聚合平均耗时
        span_durations: Dict[str, List[float]] = {}
        for t in self._traces:
            for s in t.spans:
                span_durations.setdefault(s.name, []).append(s.duration_ms)

        avg_by_span = {
            name: round(sum(durs) / len(durs), 2)
            for name, durs in span_durations.items()
        }

        return {
            "traces": len(self._traces),
            "total_spans": total_spans,
            "avg_duration_ms": round(total_ms / len(self._traces), 2),
            "error_traces": error_count,
            "avg_span_duration_ms": avg_by_span,
        }

    def clear(self) -> None:
        """清空所有 trace。"""
        self._traces.clear()
        self._active_trace = None
        self._active_span_stack.clear()
