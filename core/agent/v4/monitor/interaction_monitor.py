"""API Interaction Monitor — capture every FE↔API request/response.

Design:
  - Middleware hooks into every HTTP request
  - Records: method, path, status, timing, request_id, session, error
  - In-memory ring buffer (last 5000 calls)
  - Dashboard endpoint: GET /v6/monitor/interactions
  - Pairs requests with their responses automatically

No external dependency — pure stdlib + FastAPI middleware.
"""
from __future__ import annotations
import time, json, logging, threading, hashlib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("monitor")


@dataclass
class InteractionRecord:
    id: str
    ts: float
    method: str
    path: str
    status: int
    duration_ms: float
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    client_ip: str = ""
    session: str = ""
    error: Optional[str] = None


class InteractionMonitor:
    """Middleware that captures all API request/response pairs."""

    def __init__(self, max_records: int = 5000):
        self._records: List[InteractionRecord] = []
        self._max = max_records
        self._lock = threading.Lock()
        self._by_path: Dict[str, int] = {}
        self._by_status: Dict[int, int] = {}
        self._errors: List[InteractionRecord] = []
        self._active: Dict[str, float] = {}  # request_id → start_time
        self._started = time.time()

    def begin(self, request_id: str, method: str, path: str, 
              client_ip: str = "", session: str = ""):
        with self._lock:
            self._active[request_id] = time.time()

    def end(self, request_id: str, status: int, request_body: str = "",
            response_body: str = ""):
        with self._lock:
            start = self._active.pop(request_id, time.time())
            dur = (time.time() - start) * 1000
            path = self._active.get(request_id + ":path", "?")
            method = self._active.get(request_id + ":method", "?")
            client_ip = self._active.get(request_id + ":ip", "")
            session = self._active.get(request_id + ":session", "")

            # Clean up temp keys
            for k in list(self._active.keys()):
                if k.startswith(request_id):
                    del self._active[k]

            r = InteractionRecord(
                id=request_id, ts=start, method=method, path=path,
                status=status, duration_ms=dur,
                request_body=request_body[:500] if request_body else None,
                response_body=response_body[:500] if response_body else None,
                client_ip=client_ip, session=session,
            )

        self._add(r)
        return r

    def record_full(self, method: str, path: str, status: int, 
                    duration_ms: float, request_body: str = "",
                    response_body: str = "", client_ip: str = "",
                    session: str = "", error: str = ""):
        """Record a complete interaction in one call."""
        r = InteractionRecord(
            id=hashlib.md5(f"{time.time()}{method}{path}".encode()).hexdigest()[:12],
            ts=time.time(), method=method, path=path, status=status,
            duration_ms=duration_ms,
            request_body=request_body[:500] if request_body else None,
            response_body=response_body[:500] if response_body else None,
            client_ip=client_ip, session=session, error=error,
        )
        self._add(r)
        return r

    def _add(self, r: InteractionRecord):
        with self._lock:
            self._records.append(r)
            if len(self._records) > self._max:
                self._records = self._records[-self._max:]

            # Stats
            self._by_path[r.path] = self._by_path.get(r.path, 0) + 1
            self._by_status[r.status] = self._by_status.get(r.status, 0) + 1
            if r.status >= 400:
                self._errors.append(r)
                if len(self._errors) > 500:
                    self._errors = self._errors[-500:]

    def recent(self, limit: int = 50, min_status: int = 0) -> List[dict]:
        """Recent interactions, optionally filtered by minimum status."""
        with self._lock:
            items = [r for r in self._records if r.status >= min_status]
            return [self._to_dict(r) for r in items[-limit:]]

    def errors(self, limit: int = 20) -> List[dict]:
        with self._lock:
            return [self._to_dict(r) for r in self._errors[-limit:]]

    def stats(self) -> dict:
        with self._lock:
            total = len(self._records)
            success = sum(1 for r in self._records if r.status < 400)
            return {
                "uptime_seconds": time.time() - self._started,
                "total_requests": total,
                "success_rate": success / max(total, 1),
                "by_status": dict(self._by_status),
                "top_paths": dict(sorted(self._by_path.items(), key=lambda x: -x[1])[:10]),
                "error_count": len(self._errors),
                "avg_response_ms": sum(r.duration_ms for r in self._records[-100:]) / max(len(self._records[-100:]), 1) if total > 0 else 0,
            }

    def slow_requests(self, threshold_ms: float = 500, limit: int = 10) -> List[dict]:
        with self._lock:
            slow = [r for r in self._records if r.duration_ms > threshold_ms]
            slow.sort(key=lambda r: -r.duration_ms)
            return [self._to_dict(r) for r in slow[:limit]]

    def _to_dict(self, r: InteractionRecord) -> dict:
        return {
            "id": r.id, "ts": r.ts, "method": r.method, "path": r.path,
            "status": r.status, "duration_ms": round(r.duration_ms, 2),
            "client_ip": r.client_ip, "session": r.session,
            "error": r.error,
            "request": r.request_body,
            "response": r.response_body,
        }


# ── FastAPI Middleware Integration ──

_INTERACTION_MONITOR: Optional[InteractionMonitor] = None


def get_interaction_monitor() -> InteractionMonitor:
    global _INTERACTION_MONITOR
    if _INTERACTION_MONITOR is None:
        _INTERACTION_MONITOR = InteractionMonitor()
    return _INTERACTION_MONITOR


async def interaction_middleware(request, call_next):
    """FastAPI middleware: captures timing + status for every request."""
    import uuid
    rid = str(uuid.uuid4())[:12]
    mon = get_interaction_monitor()
    mon.begin(rid, request.method, request.url.path,
              client_ip=request.client.host if request.client else "",
              session=request.headers.get("x-session-id", ""))

    # Capture request body (for POST/PUT)
    body = ""
    try:
        if request.method in ("POST", "PUT"):
            body = (await request.body()).decode()[:500]
    except Exception:
        pass

    response = await call_next(request)

    # Capture response body
    resp_body = ""
    try:
        resp_body = response.body.decode()[:500]
    except Exception:
        pass

    mon.end(rid, response.status_code, request_body=body, response_body=resp_body)
    return response
