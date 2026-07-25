"""Unified Trace & Log system — wired into all DialogMesh pipelines.

SpanTracer: OpenTelemetry-style distributed tracing.
  - trace_id propagation across Frontend→API→agent_native→Execution→LLM
  - 9-stage auto-instrumentation
  - tree-wise span tracking

StructuredLogger: JSON lines + level + trace_id correlation.
  - Every log line = one JSON object
  - trace_id always present
  - output: stdout (dev) / file (prod)
"""

from __future__ import annotations
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ═══ Span Tracer ═══

@dataclass
class Span:
    id: str; trace_id: str; parent_id: Optional[str]
    name: str; service: str
    start: float; end: float = 0.0
    status: str = "ok"
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List["Span"] = field(default_factory=list)


class SpanTracer:
    """Distributed tracer. In-memory, exposes via API /v6/trace."""

    MAX_TRACES = 200

    def __init__(self):
        self._traces: Dict[str, List[Span]] = {}
        self._spans: Dict[str, Span] = {}
        self._active: Dict[str, Span] = {}  # trace_id → current span stack

    def start_trace(self, service: str = "frontend") -> Span:
        """Begin a new trace. Returns root span."""
        trace_id = str(uuid.uuid4())[:12]
        span = Span(id=f"{trace_id}_root", trace_id=trace_id,
                    parent_id=None, name=f"{service}_init", service=service,
                    start=time.time())
        self._traces.setdefault(trace_id, []).append(span)
        self._spans[span.id] = span
        self._active[trace_id] = span
        self._cleanup()
        return span

    def start_span(self, trace_id: str, name: str, service: str,
                   parent_id: str = None) -> Span:
        """Start a child span."""
        if trace_id not in self._traces:
            return self.start_trace(service)
        if parent_id is None and self._active.get(trace_id):
            parent_id = self._active[trace_id].id
        span = Span(id=f"{trace_id}_{name}_{len(self._traces[trace_id])}",
                    trace_id=trace_id, parent_id=parent_id,
                    name=name, service=service, start=time.time())
        self._traces[trace_id].append(span)
        self._spans[span.id] = span
        if parent_id and parent_id in self._spans:
            self._spans[parent_id].children.append(span)
        self._active[trace_id] = span
        return span

    def end_span(self, trace_id: str, span_id: str = None,
                 status: str = "ok", metadata: dict = None):
        """End the current span for a trace."""
        if span_id and span_id in self._spans:
            span = self._spans[span_id]
        elif trace_id in self._active:
            span = self._active[trace_id]
        else:
            return
        span.end = time.time()
        span.status = status
        if metadata:
            span.metadata.update(metadata)
        if trace_id in self._active and self._active[trace_id].id == span.id:
            self._active[trace_id] = (
                self._spans.get(span.parent_id) if span.parent_id else None)

    def get_trace(self, trace_id: str) -> dict:
        """Return full trace tree as API-compatible dict."""
        spans = self._traces.get(trace_id, [])
        if not spans:
            return {}
        root = next((s for s in spans if s.parent_id is None), spans[0])
        return {
            "trace_id": trace_id,
            "spans": [self._span_to_dict(s) for s in spans],
            "total_ms": round((spans[-1].end - root.start) * 1000, 1),
        }

    def _span_to_dict(self, s: Span) -> dict:
        return {
            "id": s.id, "parent_id": s.parent_id,
            "name": s.name, "service": s.service,
            "start": round(s.start, 6), "end": round(s.end, 6),
            "duration_ms": round((s.end - s.start) * 1000, 2) if s.end else None,
            "status": s.status, "metadata": s.metadata,
            "children": len(s.children),
        }

    def recent_traces(self, limit: int = 20) -> List[dict]:
        return [self.get_trace(tid) for tid in
                list(self._traces.keys())[-limit:]]

    def _cleanup(self):
        while len(self._traces) > self.MAX_TRACES:
            oldest = next(iter(self._traces))
            del self._traces[oldest]


# Global singleton
_tracer: Optional[SpanTracer] = None

def get_tracer() -> SpanTracer:
    global _tracer
    if _tracer is None:
        _tracer = SpanTracer()
    return _tracer


# ═══ Structure Logger ═══

class StructuredLogger:
    """JSON-lines logger with trace_id correlation.

    Output: one JSON object per line.
    Format: {"ts":"ISO8601","level":"INFO","trace_id":"...","module":"...","msg":"..."}
    """

    def __init__(self, level: str = "INFO", output: str = "stdout"):
        self._level = getattr(logging, level.upper(), logging.INFO)
        self._out = sys.stdout if output == "stdout" else open(output, 'a', encoding='utf-8')
        self._tracer = None  # Set after init

    def set_tracer(self, tracer: SpanTracer):
        self._tracer = tracer

    def _active_trace(self) -> str:
        if self._tracer and self._tracer._active:
            return list(self._tracer._active.keys())[0][:12]
        return "no-trace"

    def _emit(self, level: str, module: str, msg: str, extra: dict = None):
        if getattr(logging, level.upper(), logging.INFO) < self._level:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            "level": level,
            "trace_id": self._active_trace(),
            "module": module,
            "msg": msg,
        }
        if extra:
            entry["extra"] = extra
        self._out.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self._out.flush()

    def debug(self, module: str, msg: str, extra: dict = None):
        self._emit("DEBUG", module, msg, extra)

    def info(self, module: str, msg: str, extra: dict = None):
        self._emit("INFO", module, msg, extra)

    def warn(self, module: str, msg: str, extra: dict = None):
        self._emit("WARN", module, msg, extra)

    def error(self, module: str, msg: str, extra: dict = None):
        self._emit("ERROR", module, msg, extra)


# Global singleton
_logger: Optional[StructuredLogger] = None

def get_logger() -> StructuredLogger:
    global _logger
    if _logger is None:
        _logger = StructuredLogger()
        _logger.set_tracer(get_tracer())
    return _logger


# ═══ Pipeline Instrumentation ═══

class PipelineObserver:
    """Auto-instruments agent_native 9-stage pipeline with spans + logs."""

    STAGES = [
        ("compass", "perception"),
        ("pcr", "perception"),
        ("intent", "cognition"),
        ("l4", "cognition"),
        ("context", "assembly"),
        ("llm_plan", "llm"),
        ("plan_gate", "planning"),
        ("execution", "execution"),
        ("llm_answer", "llm"),
    ]

    def __init__(self, tracer: SpanTracer = None, logger: StructuredLogger = None):
        self._tracer = tracer or get_tracer()
        self._log = logger or get_logger()

    def start_request(self, user_input: str) -> dict:
        """Begin a new request with trace."""
        root = self._tracer.start_trace("api")
        trace_id = root.trace_id
        self._log.info("pipeline", f"Request start: {user_input[:100]}",
                       {"trace_id": trace_id, "input_len": len(user_input)})
        return {"trace_id": trace_id, "root_span_id": root.id}

    def stage_start(self, trace_id: str, stage: str):
        span = self._tracer.start_span(trace_id, stage,
                                       dict(self.STAGES).get(stage, "unknown"))
        self._log.debug(stage, f"Stage start: {stage}")

    def stage_end(self, trace_id: str, stage: str, status: str = "ok",
                  metadata: dict = None):
        self._tracer.end_span(trace_id, status=status, metadata=metadata)
        self._log.debug(stage, f"Stage done: {stage} ({status})",
                        metadata)

    def request_end(self, trace_id: str, result: dict):
        self._tracer.end_span(trace_id, status="ok")
        trace = self._tracer.get_trace(trace_id)
        self._log.info("pipeline", f"Request done: {trace.get('total_ms', 0)}ms",
                       {"trace_id": trace_id, "total_ms": trace.get("total_ms")})
        return trace
