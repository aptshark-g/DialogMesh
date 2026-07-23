"""API Interaction Monitor v2 — comprehensive FE↔API tracing.

Features:
  - Middleware captures every request/response pair
  - Persistent JSONL logging (tests/log/monitor_*.jsonl)
  - HTML mini-dashboard at /v6/monitor/dashboard
  - Gateway proxy call tagging
  - Auto-cleanup for old records
  - Health timeline (state changes)
"""
from __future__ import annotations
import os, time, json, logging, threading, hashlib
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
    is_gateway_proxy: bool = False


class InteractionMonitor:
    """Middleware that captures all API request/response pairs."""

    def __init__(self, max_records: int = 5000, persist_dir: str = "tests/log"):
        self._records: List[InteractionRecord] = []
        self._max = max_records
        self._lock = threading.Lock()
        self._by_path: Dict[str, int] = {}
        self._by_status: Dict[int, int] = {}
        self._errors: List[InteractionRecord] = []
        self._active: Dict[str, Any] = {}
        self._started = time.time()
        self._persist_dir = persist_dir
        self._persist_path = os.path.join(persist_dir, f"monitor_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
        self._health_timeline: List[dict] = []
        os.makedirs(persist_dir, exist_ok=True)

    def begin(self, request_id: str, method: str, path: str,
              client_ip: str = "", session: str = ""):
        with self._lock:
            self._active[request_id] = {
                "start": time.time(), "method": method, "path": path,
                "client_ip": client_ip, "session": session,
            }

    def end(self, request_id: str, status: int, request_body: str = "",
            response_body: str = "", is_gateway: bool = False):
        with self._lock:
            meta = self._active.pop(request_id, {"start": time.time(), "method": "?", "path": "?", "client_ip": "", "session": ""})
            dur = (time.time() - meta["start"]) * 1000

            r = InteractionRecord(
                id=request_id, ts=meta["start"],
                method=meta["method"], path=meta["path"],
                status=status, duration_ms=dur,
                request_body=request_body[:500] if request_body else None,
                response_body=response_body[:500] if response_body else None,
                client_ip=meta["client_ip"], session=meta["session"],
                is_gateway_proxy=is_gateway or "/v6/gateway" in meta["path"],
            )
        self._add(r)
        self._persist(r)
        return r

    def record_full(self, method: str, path: str, status: int,
                    duration_ms: float, request_body: str = "",
                    response_body: str = "", client_ip: str = "",
                    session: str = "", error: str = ""):
        r = InteractionRecord(
            id=hashlib.md5(f"{time.time()}{method}{path}".encode()).hexdigest()[:12],
            ts=time.time(), method=method, path=path, status=status,
            duration_ms=duration_ms,
            request_body=request_body[:500] if request_body else None,
            response_body=response_body[:500] if response_body else None,
            client_ip=client_ip, session=session, error=error,
            is_gateway_proxy="/v6/gateway" in path,
        )
        self._add(r)
        return r

    def _add(self, r: InteractionRecord):
        with self._lock:
            self._records.append(r)
            if len(self._records) > self._max:
                self._records = self._records[-self._max:]
            self._by_path[r.path] = self._by_path.get(r.path, 0) + 1
            self._by_status[r.status] = self._by_status.get(r.status, 0) + 1
            if r.status >= 400:
                self._errors.append(r)
                if len(self._errors) > 500:
                    self._errors = self._errors[-500:]
            # Health timeline: log every state change
            if not self._health_timeline or self._last_state() != (r.status < 400):
                self._health_timeline.append({
                    "ts": r.ts, "healthy": r.status < 400,
                    "path": r.path, "status": r.status,
                })
                if len(self._health_timeline) > 200:
                    self._health_timeline = self._health_timeline[-200:]

    def _last_state(self) -> bool:
        return self._health_timeline[-1]["healthy"] if self._health_timeline else True

    def _persist(self, r: InteractionRecord):
        try:
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": r.ts, "method": r.method, "path": r.path,
                    "status": r.status, "duration_ms": round(r.duration_ms, 2),
                    "client_ip": r.client_ip, "error": r.error,
                    "gateway": r.is_gateway_proxy,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def recent(self, limit: int = 50, min_status: int = 0) -> List[dict]:
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
            gateway = sum(1 for r in self._records if r.is_gateway_proxy)
            return {
                "uptime_seconds": round(time.time() - self._started, 1),
                "total_requests": total,
                "success_rate": round(success / max(total, 1), 4),
                "gateway_proxy_calls": gateway,
                "by_status": dict(self._by_status),
                "top_paths": dict(sorted(self._by_path.items(), key=lambda x: -x[1])[:10]),
                "error_count": len(self._errors),
                "avg_response_ms": round(
                    sum(r.duration_ms for r in self._records[-100:]) / max(len(self._records[-100:]), 1), 1
                ) if total > 0 else 0,
                "health_timeline": self._health_timeline[-20:],
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
            "error": r.error, "gateway": r.is_gateway_proxy,
            "request": r.request_body,
            "response": r.response_body,
        }

    # ── HTML mini-dashboard ───

    def dashboard_html(self) -> str:
        s = self.stats()
        errors = self.errors(10)
        recent = self.recent(20)

        error_rows = ""
        for e in errors:
            gw = "🔀" if e.get("gateway") else ""
            error_rows += f"<tr><td>{gw}</td><td>{e['method']}</td><td>{e['path']}</td><td style='color:red'>{e['status']}</td><td>{e['duration_ms']}ms</td></tr>"

        recent_rows = ""
        for r in recent:
            gw = "🔀" if r.get("gateway") else ""
            color = "#22c55e" if r["status"] < 400 else "#ef4444"
            recent_rows += f"<tr><td>{gw}</td><td>{r['method']}</td><td>{r['path']}</td><td style='color:{color}'>{r['status']}</td><td>{r['duration_ms']}ms</td></tr>"

        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>DialogMesh Monitor</title>
<meta http-equiv="refresh" content="5">
<style>
body{{font-family:system-ui;background:#111;color:#e5e7eb;margin:0;padding:20px}}
h2{{border-bottom:1px solid #333;padding-bottom:8px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}}
.card{{background:#1a1a2e;border-radius:8px;padding:16px;text-align:center}}
.card .value{{font-size:2em;font-weight:700;margin:4px 0}}
.card .label{{font-size:0.8em;color:#9ca3af}}
.ok{{color:#22c55e}}.warn{{color:#f59e0b}}.err{{color:#ef4444}}
table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}}
th,td{{padding:6px 12px;text-align:left;border-bottom:1px solid #1f2937}}
th{{color:#9ca3af;font-weight:500}}
tr:hover{{background:#1f2937}}
</style></head><body>
<h1>🔍 DialogMesh API Monitor</h1>

<div class="metrics">
  <div class="card"><div class="value ok">{s['total_requests']}</div><div class="label">总请求</div></div>
  <div class="card"><div class="value {'ok' if s['success_rate']>0.99 else 'warn' if s['success_rate']>0.95 else 'err'}">{s['success_rate']*100:.1f}%</div><div class="label">成功率</div></div>
  <div class="card"><div class="value">{s['avg_response_ms']:.0f}ms</div><div class="label">平均响应</div></div>
  <div class="card"><div class="value err">{s['error_count']}</div><div class="label">错误数</div></div>
  <div class="card"><div class="value">{s['gateway_proxy_calls']}</div><div class="label">网关代理</div></div>
  <div class="card"><div class="value">{s['uptime_seconds']:.0f}s</div><div class="label">运行时间</div></div>
</div>

<h2>❌ 最近错误</h2>
<table><tr><th></th><th>方法</th><th>路径</th><th>状态</th><th>延迟</th></tr>{error_rows or '<tr><td colspan=5 style="color:#22c55e">✅ 无错误</td></tr>'}</table>

<h2>📋 最近交互</h2>
<table><tr><th></th><th>方法</th><th>路径</th><th>状态</th><th>延迟</th></tr>{recent_rows}</table>

<footer style="margin-top:20px;color:#4b5563;font-size:12px">每5秒自动刷新 · DialogMesh v6 · {time.strftime('%H:%M:%S')}</footer>
</body></html>"""


# ── FastAPI Middleware Integration ──

_INTERACTION_MONITOR: Optional[InteractionMonitor] = None


def get_interaction_monitor() -> InteractionMonitor:
    global _INTERACTION_MONITOR
    if _INTERACTION_MONITOR is None:
        _INTERACTION_MONITOR = InteractionMonitor()
    return _INTERACTION_MONITOR


async def interaction_middleware(request, call_next):
    """FastAPI middleware: captures timing + status + spans for every request."""
    import uuid
    rid = str(uuid.uuid4())[:12]
    mon = get_interaction_monitor()
    mon.begin(rid, request.method, request.url.path,
              client_ip=request.client.host if request.client else "",
              session=request.headers.get("x-session-id", ""))

    # OpenTelemetry-style span
    from core.agent.monitor.span_tracer import get_tracer
    span_id = get_tracer().start_span(
        name=f"{request.method} {request.url.path}",
        service="api",
        trace_id=request.headers.get("x-trace-id"),
        tags={"method": request.method, "path": request.url.path},
    )

    body = ""
    try:
        if request.method in ("POST", "PUT"):
            body = (await request.body()).decode()[:500]
    except Exception:
        pass

    response = await call_next(request)

    resp_body = ""
    try:
        body_bytes = response.body
        resp_body = body_bytes.decode()[:2000]  # capture more for debugging
    except Exception:
        pass

    mon.end(rid, response.status_code, request_body=body, response_body=resp_body,
            is_gateway="/v6/gateway" in str(request.url.path))
    get_tracer().end_span(span_id, status="ok" if response.status_code < 400 else "error",
                          tags={"status": str(response.status_code)})
    return response
