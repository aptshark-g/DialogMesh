"""Span Tracer — OpenTelemetry-style distributed tracing built-in.

Traces every request: Frontend → API → Gateway → LLM → back.

Spans show:
  - Timing at each hop
  - Status (ok/error)
  - Parent-child relationships
  - Correlation via trace_id header

No external dependencies — pure Python, stored in-memory.
"""
from __future__ import annotations
import time, uuid, threading, json, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("tracer")


@dataclass
class Span:
    id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    service: str  # frontend | api | gateway | llm
    start: float
    end: float = 0
    status: str = "ok"  # ok | error | timeout
    tags: Dict[str, str] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000 if self.end else 0


class SpanTracer:
    """Lightweight distributed tracer. One instance per process."""

    def __init__(self, max_traces: int = 500):
        self._traces: Dict[str, List[Span]] = {}  # trace_id → spans
        self._active: Dict[str, Span] = {}  # span_id → span
        self._max = max_traces
        self._lock = threading.Lock()

    def start_span(self, name: str, service: str = "api",
                   trace_id: str = None, parent_id: str = None,
                   tags: Dict[str, str] = None) -> str:
        """Begin a new span. Returns span_id."""
        tid = trace_id or str(uuid.uuid4())[:12]
        sid = str(uuid.uuid4())[:12]
        span = Span(
            id=sid, trace_id=tid, parent_id=parent_id,
            name=name, service=service, start=time.time(),
            tags=tags or {},
        )
        with self._lock:
            self._active[sid] = span
            if tid not in self._traces:
                self._traces[tid] = []
            self._traces[tid].append(span)
            # Trim old traces
            if len(self._traces) > self._max:
                oldest = sorted(self._traces.keys())[:-self._max]
                for k in oldest:
                    del self._traces[k]
        return sid

    def end_span(self, span_id: str, status: str = "ok", tags: Dict = None):
        """Finish a span."""
        with self._lock:
            span = self._active.pop(span_id, None)
            if span:
                span.end = time.time()
                span.status = status
                if tags:
                    span.tags.update(tags)

    def add_event(self, span_id: str, name: str, data: Dict = None):
        """Add an event (log point) to a span."""
        with self._lock:
            span = self._active.get(span_id)
            if span:
                span.events.append({"name": name, "ts": time.time(), "data": data or {}})

    def get_trace(self, trace_id: str) -> List[Dict]:
        """Get all spans for a trace."""
        with self._lock:
            spans = self._traces.get(trace_id, [])
            return [self._span_to_dict(s) for s in spans]

    def recent_traces(self, limit: int = 20) -> List[Dict]:
        """Recent trace summaries."""
        with self._lock:
            keys = list(self._traces.keys())[-limit:]
            result = []
            for tid in keys:
                spans = self._traces[tid]
                if not spans: continue
                root = [s for s in spans if s.parent_id is None]
                root_span = root[0] if root else spans[0]
                errs = [s for s in spans if s.status != "ok"]
                result.append({
                    "trace_id": tid,
                    "root": root_span.name,
                    "spans": len(spans),
                    "total_ms": sum(s.duration_ms for s in spans),
                    "errors": [s.name for s in errs],
                    "start": root_span.start,
                })
            return sorted(result, key=lambda x: x["start"], reverse=True)

    def waterfall(self, trace_id: str) -> str:
        """HTML waterfall view for a trace."""
        spans = sorted(self._traces.get(trace_id, []), key=lambda s: s.start)
        if not spans: return "<p>Trace not found</p>"

        base = min(s.start for s in spans)
        max_t = max(s.end for s in spans)
        total_ms = (max_t - base) * 1000
        if total_ms == 0: total_ms = 1

        rows = ""
        for s in spans:
            indent = "　" * (s.parent_id is not None)
            offset_pct = ((s.start - base) * 1000) / total_ms * 100
            width_pct = max(s.duration_ms / total_ms * 100, 0.5)
            color = "#22c55e" if s.status == "ok" else "#ef4444"
            rows += f"""
            <div style="display:flex;align-items:center;margin:4px 0;font-size:13px">
              <span style="width:200px;color:#9ca3af">{indent}{s.service}</span>
              <span style="width:300px;color:#e5e7eb">{s.name}</span>
              <div style="flex:1;margin:0 12px;background:#1f2937;border-radius:4px;height:20px;position:relative">
                <div style="position:absolute;left:{offset_pct:.1f}%;width:{width_pct:.1f}%;height:100%;background:{color};border-radius:3px;min-width:2px"></div>
              </div>
              <span style="color:{color};width:60px;text-align:right">{s.duration_ms:.1f}ms</span>
            </div>"""

        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Trace: {trace_id}</title>
<style>body{{font-family:system-ui;background:#111;color:#e5e7eb;padding:20px}}</style></head><body>
<h2>🔍 Trace: {trace_id} <span style="font-size:14px;color:#9ca3af">({total_ms:.0f}ms total)</span></h2>
{rows}
<p style="margin-top:20px;color:#4b5563">{len(spans)} spans · {'✅ all ok' if all(s.status=='ok' for s in spans) else '❌ has errors'}</p>
</body></html>"""

    def _span_to_dict(self, s: Span) -> dict:
        return {
            "id": s.id, "trace_id": s.trace_id, "parent_id": s.parent_id,
            "name": s.name, "service": s.service,
            "start": s.start, "duration_ms": s.duration_ms,
            "status": s.status, "tags": s.tags,
        }


# ── Global instance ──

_SPAN_TRACER: Optional[SpanTracer] = None

def get_tracer() -> SpanTracer:
    global _SPAN_TRACER
    if _SPAN_TRACER is None:
        _SPAN_TRACER = SpanTracer()
    return _SPAN_TRACER
