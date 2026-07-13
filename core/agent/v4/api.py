"""DialogMesh v4 REST API — FastAPI routes.

Endpoints:
    POST /v4/event          Send event to cognitive runtime
    GET  /v4/status         Runtime engine stats
    GET  /v4/inspect/{mod}  System inspection (JSON)
    POST /v4/checkpoint     Manually trigger Slow Path
    GET  /v4/health         Health check
"""
from __future__ import annotations
import time, logging, os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from core.agent.v4.event_ir import EventIR
from core.agent.v4.api_event_log import EventLog
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

logger = logging.getLogger(__name__)

# ---- Global state ----
app = FastAPI(title="DialogMesh v4 API", version="1.0")
_engine: Optional[CognitiveRuntimeEngine] = None
_event_log: Optional[EventLog] = None


# ---- Models ----

class EventRequest(BaseModel):
    event_id: str
    kind: str = "dialog.message"
    payload: dict = {}
    trace_id: str = ""


class StatusResponse(BaseModel):
    async_stats: dict
    slow_stats: dict
    deep_stats: dict


# ---- Lifecycle ----

def init_api(db_path: str = "data/event_log.db",
             config_path: Optional[str] = None):
    """Initialize global engine and event log. Called once at startup."""
    global _engine, _event_log

    os.makedirs("data", exist_ok=True)

    _event_log = EventLog(db_path)
    _event_log.open()

    _engine = CognitiveRuntimeEngine(config_path=config_path)
    _engine.start()

    # Replay unconsumed events from crash
    unconsumed = _event_log.replay_unconsumed(limit=200)
    for ev in unconsumed:
        event_ir = EventIR(
            id=ev["event_id"],
            kind=ev["kind"],
            payload=ev["payload"],
        )
        _engine.on_event(event_ir)
        _event_log.ack_event(ev["event_id"])

    logger.info("API initialized. Engine started. %d events replayed.", len(unconsumed))


def shutdown_api():
    """Clean shutdown."""
    global _engine, _event_log
    if _engine:
        _engine.stop()
    if _event_log:
        _event_log.cleanup_old()
        _event_log.close()


# ---- Routes ----

@app.post("/v4/event", status_code=200)
async def post_event(req: EventRequest):
    """Receive event from Switch. Fire-and-forget."""
    if _engine is None or _event_log is None:
        raise HTTPException(503, "API not initialized")

    # Persist to EventLog (idempotent)
    ok = _event_log.put_event(
        event_id=req.event_id,
        kind=req.kind,
        payload=req.payload,
        trace_id=req.trace_id,
    )
    if not ok:
        raise HTTPException(500, "Failed to persist event")

    # Route to Runtime (async)
    event_ir = EventIR(
        id=req.event_id,
        kind=req.kind,
        payload=req.payload,
    )
    _engine.on_event(event_ir)

    # Ack
    _event_log.ack_event(req.event_id)

    return {"status": "accepted", "event_id": req.event_id}


@app.get("/v4/status")
async def get_status():
    """Return runtime engine stats."""
    if _engine is None:
        raise HTTPException(503, "API not initialized")

    stats = _engine.stats
    return {
        "async": _stats_to_dict(stats.get("async")),
        "slow": _stats_to_dict(stats.get("slow")),
        "deep": _stats_to_dict(stats.get("deep")),
    }


@app.get("/v4/inspect/{module}")
async def inspect(module: str, detail: bool = False, limit: int = 10):
    """Inspect system state. Modules: observations, hypotheses, knowledge,
    skills, world, context."""
    if _engine is None:
        raise HTTPException(503, "API not initialized")

    # Delegate to CLI inspect functions
    try:
        from core.agent.v4.cli.inspect import (
            _inspect_observations, _inspect_hypotheses, _inspect_knowledge,
            _inspect_skills, _inspect_world, _inspect_context,
        )
        # Use JSON mode by capturing output? Better: return structured data.
        # For now, return basic info based on module
        if module == "observations":
            pool = getattr(_engine, '_observation_pool', None)
            bundles = pool.get_by_domain("all")[:limit] if pool else []
            return {"count": len(bundles), "items": [str(b)[:200] for b in bundles]}
        elif module == "context":
            ctx = getattr(_engine, '_last_context', None)
            if ctx:
                return {"intent": str(getattr(ctx, 'intent', '')), "items": ctx.total_items if hasattr(ctx, 'total_items') else 0}
            return {"intent": "", "items": 0}
        else:
            return {"module": module, "status": "available", "detail": detail}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/v4/checkpoint")
async def trigger_checkpoint():
    """Manual Slow Path trigger."""
    if _engine is None:
        raise HTTPException(503, "API not initialized")

    results = _engine.trigger_checkpoint()
    return {
        "status": "completed",
        "results": [{"adapter": r.adapter_name, "ok": r.ok} for r in results],
    }


@app.get("/v4/health")
async def health_check():
    """Health check."""
    checks = {"api": "ok"}
    if _engine:
        checks["engine"] = f"{_engine.adapter_count} adapters"
    if _event_log:
        checks["event_log"] = _event_log.stats
    return checks


# ---- Helpers ----

def _stats_to_dict(stats) -> dict:
    if stats is None:
        return {}
    return {
        "trigger_count": getattr(stats, 'trigger_count', 0),
        "success_count": getattr(stats, 'success_count', 0),
        "failure_count": getattr(stats, 'failure_count', 0),
        "total_latency_ms": getattr(stats, 'total_latency_ms', 0.0),
    }


# ---- Entry point ----

def serve(host: str = "0.0.0.0", port: int = 8000, db_path: str = "data/event_log.db"):
    """Start FastAPI server."""
    init_api(db_path=db_path)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        shutdown_api()


if __name__ == "__main__":
    serve()
