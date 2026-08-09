"""Phase 4: PipelineTracer — distributed tracing + metrics.

Every message gets a trace_id that propagates across all subsystems.
Records: each subsystem step, latency, success/fail, metadata.
Output: JSON traces for debugging, metrics for dashboards.

Design:
  - TraceContext (thread-local) propagates trace_id + span_id
  - @traced decorator auto-records function execution
  - MetricsCollector aggregates latency/throughput/error per subsystem
  - CLI: dm trace show / dm trace metrics
  - API: /v6/trace/recent + /v6/trace/metrics
"""
import time, threading, json, os, uuid, functools
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = __import__('logging').getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  TraceContext — thread-local propagation
# ═══════════════════════════════════════════════════════════

_thread_local = threading.local()


def get_trace_context() -> dict:
    """Get current trace context. Creates one if none exists."""
    ctx = getattr(_thread_local, 'trace_ctx', None)
    if ctx is None:
        ctx = {
            "trace_id": str(uuid.uuid4())[:12],
            "span_id": "root",
            "session_id": "default",
            "started_at": time.time(),
        }
        _thread_local.trace_ctx = ctx
    return ctx


def set_trace_context(**kwargs):
    """Set trace context fields."""
    ctx = get_trace_context()
    ctx.update(kwargs)
    _thread_local.trace_ctx = ctx


def new_span(name: str) -> str:
    """Create a child span. Returns span_id."""
    ctx = get_trace_context()
    span_id = f"{name}_{uuid.uuid4().hex[:6]}"
    ctx["span_id"] = span_id
    return span_id


@contextmanager
def trace_span(name: str, metadata: dict = None):
    """Context manager: trace a block of code."""
    span_id = new_span(name)
    start = time.time()
    try:
        yield span_id
        MetricsCollector.record(name, "success", (time.time() - start) * 1000)
    except Exception as e:
        MetricsCollector.record(name, "error", (time.time() - start) * 1000)
        logger.debug("Trace %s failed: %s", name, e)
        raise
    finally:
        if MetadataStore:
            MetadataStore.add(span_id, metadata or {})


# ═══════════════════════════════════════════════════════════
#  TraceRecord — one step in a trace
# ═══════════════════════════════════════════════════════════

@dataclass
class TraceRecord:
    """One subsystem step with parent/child span hierarchy."""
    trace_id: str
    span_id: str
    parent_span_id: str = "root"  # span hierarchy
    subsystem: str = ""
    kind: str = ""          # "pcr_computed", "intent_parsed", etc.
    success: bool = True
    latency_ms: float = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class TraceStore:
    """In-memory trace buffer with periodic flush to disk."""

    MAX_RECORDS = 1000

    def __init__(self):
        self._records: List[TraceRecord] = []
        self._lock = threading.Lock()

    def add(self, record: TraceRecord):
        with self._lock:
            self._records.append(record)
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS:]

    def query(self, trace_id: str = None, subsystem: str = None,
              limit: int = 50) -> List[dict]:
        with self._lock:
            results = self._records
            if trace_id:
                results = [r for r in results if r.trace_id == trace_id]
            if subsystem:
                results = [r for r in results if r.subsystem == subsystem]
            return [
                {
                    "trace_id": r.trace_id, "span_id": r.span_id,
                    "subsystem": r.subsystem, "kind": r.kind,
                    "success": r.success, "latency_ms": round(r.latency_ms, 1),
                    "timestamp": r.timestamp, "metadata": r.metadata,
                }
                for r in results[-limit:]
            ]

    def get_recent_traces(self, limit: int = 10) -> List[dict]:
        """Get recent traces grouped by trace_id."""
        with self._lock:
            seen = set()
            result = []
            for r in reversed(self._records):
                if r.trace_id not in seen:
                    seen.add(r.trace_id)
                    steps = [s for s in self._records if s.trace_id == r.trace_id]
                    total_latency = sum(s.latency_ms for s in steps)
                    result.append({
                        "trace_id": r.trace_id,
                        "steps": len(steps),
                        "total_latency_ms": round(total_latency, 1),
                        "subsystems": list(set(s.subsystem for s in steps)),
                        "success": all(s.success for s in steps),
                        "started_at": min(s.timestamp for s in steps),
                    })
                    if len(result) >= limit:
                        break
            return result

    def stats(self) -> dict:
        with self._lock:
            if not self._records:
                return {"total_traces": 0}
            trace_ids = set(r.trace_id for r in self._records)
            return {
                "total_records": len(self._records),
                "total_traces": len(trace_ids),
                "avg_latency_ms": round(
                    sum(r.latency_ms for r in self._records) / len(self._records), 1
                ),
                "error_rate": round(
                    sum(1 for r in self._records if not r.success) / len(self._records), 3
                ),
            }

    def flush_to_disk(self, path: str):
        try:
            recent = self.query(limit=100)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(recent, f, indent=2, ensure_ascii=False, default=str)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  MetricsCollector — per-subsystem latency + error tracking
# ═══════════════════════════════════════════════════════════

class MetricsCollector:
    """Per-subsystem metrics: latency, success_count, error_count.
    Thread-safe singleton for global access.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._metrics: Dict[str, dict] = {}  # subsystem → stats
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def record(cls, subsystem: str, status: str, latency_ms: float):
        """Record one execution result."""
        m = cls.get()
        with m._lock:
            if subsystem not in m._metrics:
                m._metrics[subsystem] = {
                    "total": 0, "success": 0, "error": 0,
                    "total_latency_ms": 0.0, "min_latency_ms": float("inf"),
                    "max_latency_ms": 0.0, "last_seen": 0,
                }
            s = m._metrics[subsystem]
            s["total"] += 1
            s[status] += 1
            s["total_latency_ms"] += latency_ms
            s["min_latency_ms"] = min(s["min_latency_ms"], latency_ms)
            s["max_latency_ms"] = max(s["max_latency_ms"], latency_ms)
            s["last_seen"] = time.time()

    @classmethod
    def snapshot(cls) -> dict:
        m = cls.get()
        with m._lock:
            result = {}
            for name, s in m._metrics.items():
                total = s["total"]
                result[name] = {
                    "total": total,
                    "success": s["success"],
                    "error": s["error"],
                    "success_rate": round(s["success"] / total, 3) if total > 0 else 1.0,
                    "avg_latency_ms": round(s["total_latency_ms"] / total, 1) if total > 0 else 0,
                    "min_latency_ms": round(s["min_latency_ms"], 1) if s["min_latency_ms"] != float("inf") else 0,
                    "max_latency_ms": round(s["max_latency_ms"], 1),
                    "last_seen": s["last_seen"],
                }
            return result


# ═══════════════════════════════════════════════════════════
#  MetadataStore — optional span metadata
# ═══════════════════════════════════════════════════════════

class _MetadataStore:
    """In-memory metadata for the current trace."""
    def __init__(self):
        self._data: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def add(self, span_id: str, meta: dict):
        with self._lock:
            self._data[span_id] = meta

    def get(self, span_id: str) -> dict:
        return self._data.get(span_id, {})

    def clear(self, span_id: str = None):
        with self._lock:
            if span_id:
                self._data.pop(span_id, None)
            else:
                self._data.clear()


MetadataStore = _MetadataStore()


# ═══════════════════════════════════════════════════════════
#  PipelineTracer — main facade
# ═══════════════════════════════════════════════════════════

@dataclass
class PipelineTracer:
    """Facade: trace, record, query pipeline execution.

    Attach to engine at init time. Each _publish call records a trace step.

    Usage:
        tracer = PipelineTracer()
        with tracer.span("pcr", {"zone": "MIXED"}):
            # ... do work
        tracer.record("discourse", success=True, latency_ms=2.5)
        traces = tracer.query(trace_id="abc123")
    """

    store: TraceStore = field(default_factory=TraceStore)

    def record(self, subsystem: str, kind: str, success: bool,
               latency_ms: float, metadata: dict = None, parent_span_id: str = "root"):
        """Record a pipeline step with span hierarchy."""
        ctx = get_trace_context()
        span_id = f"{subsystem}_{uuid.uuid4().hex[:6]}"
        rec = TraceRecord(
            trace_id=ctx["trace_id"],
            span_id=span_id,
            parent_span_id=parent_span_id,
            subsystem=subsystem,
            kind=kind,
            success=success,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
        self.store.add(rec)
        MetricsCollector.record(subsystem, "success" if success else "error", latency_ms)
        return span_id  # Return span so callers can create children

    @contextmanager
    def span(self, subsystem: str, kind: str):
        """Context manager: auto-record a pipeline step."""
        ctx = get_trace_context()
        span_id = f"{subsystem}_{uuid.uuid4().hex[:6]}"
        ctx["span_id"] = span_id
        start = time.time()
        success = True
        try:
            yield span_id
        except Exception:
            success = False
            raise
        finally:
            latency = (time.time() - start) * 1000
            self.record(subsystem, kind, success, latency)

    def query(self, trace_id: str = None, limit: int = 50) -> List[dict]:
        return self.store.query(trace_id=trace_id, limit=limit)


    def turn_detail(self, trace_id: str = None, limit: int = 50) -> List[dict]:
        """B3: ?? trace????????? phase ???????????

        ? recent() ?? trace_id ?????????? trace ????
        ?pcr/intent/llm/... + publish ???????/???????
        """
        # query() returns plain dicts; re-sort by insertion order (oldest first
        # was the recording order, but query filters preserve list order).
        records = self.store.query(trace_id=trace_id, limit=limit)
        for r in records:
            r["ts"] = r.pop("timestamp", None)
        return records

    def error_report(self, window: int = 200) -> dict:
        """B3: ??????? ? ?? phase ???????????????

        ???????????????"????"?????
        ???? + ?? 10 ????????????
        """
        records = self.store._records[-window:]
        by_subsystem: Dict[str, dict] = {}
        recent_failures = []
        for r in records:
            if not r.success:
                meta = r.metadata or {}
                recent_failures.append({
                    "subsystem": r.subsystem,
                    "kind": r.kind,
                    "latency_ms": round(r.latency_ms, 1),
                    "error": str(meta.get("error", ""))[:200],
                    "ts": r.timestamp,
                })
                s = by_subsystem.setdefault(r.subsystem, {"failures": 0, "last_error": ""})
                s["failures"] += 1
                s["last_error"] = str(meta.get("error", ""))[:200]
        # ????? subsystem ?? total?
        totals: Dict[str, int] = {}
        for r in records:
            totals[r.subsystem] = totals.get(r.subsystem, 0) + 1
        for name, s in by_subsystem.items():
            s["total"] = totals.get(name, 0)
            s["failure_rate"] = round(s["failures"] / max(1, s["total"]), 3)
        return {
            "checked": len(records),
            "failures": len(recent_failures),
            "by_subsystem": by_subsystem,
            "recent_failures": recent_failures[-10:],
        }

    def recent(self, limit: int = 10) -> List[dict]:
        return self.store.get_recent_traces(limit=limit)

    def stats(self) -> dict:
        return self.store.stats()

    def metrics(self) -> dict:
        return MetricsCollector.snapshot()

    def flush(self, path: str = None):
        if path is None:
            from pathlib import Path
            root = Path(__file__).resolve().parent.parent.parent.parent / "data"
            path = str(root / "pipeline_traces.json")
        self.store.flush_to_disk(path)


# ═══════════════════════════════════════════════════════════
#  traced decorator — auto-trace any function
# ═══════════════════════════════════════════════════════════

def traced(subsystem: str = None):
    """Decorator: auto-record function execution in pipeline tracer.

    Usage:
        @traced("discourse")
        def feed(text, sid): ...
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            name = subsystem or fn.__name__
            start = time.time()
            try:
                result = fn(*args, **kwargs)
                latency = (time.time() - start) * 1000
                MetricsCollector.record(name, "success", latency)
                return result
            except Exception:
                latency = (time.time() - start) * 1000
                MetricsCollector.record(name, "error", latency)
                raise
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════
#  Wire into engine
# ═══════════════════════════════════════════════════════════

def wire_tracer(engine) -> PipelineTracer:
    """Attach PipelineTracer to engine for automatic step recording."""
    tracer = PipelineTracer()
    engine._pipeline_tracer = tracer

    # Wrap _publish to auto-record each subscriber step
    original_publish = engine._publish

    def traced_publish(event_type, payload=None):
        kind = event_type.value if hasattr(event_type, 'value') else str(event_type)
        with tracer.span("publish", kind):
            original_publish(event_type, payload)

    engine._publish = traced_publish
    logger.info("PipelineTracer wired: auto-recording all _publish steps")
    return tracer
