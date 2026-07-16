"""DialogMesh v4 REST API — FastAPI routes.

Endpoints:
    POST /v4/event          Send event to cognitive runtime
    GET  /v4/status         Runtime engine stats
    GET  /v4/inspect/{mod}  System inspection (JSON)
    POST /v4/checkpoint     Manually trigger Slow Path
    GET  /v4/health         Health check
    POST /v4/ingest         Ingest external documents
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


class IngestRequest(BaseModel):
    source_path: str
    content: str = ""
    file_type: str = "markdown"


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
    """Receive event from Switch. Process through cognitive runtime and return LLM response."""
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

    # Route to Runtime (async) — now returns LLM response
    event_ir = EventIR(
        id=req.event_id,
        kind=req.kind,
        payload=req.payload,
    )
    llm_response = _engine.on_event(event_ir)

    # Ack
    _event_log.ack_event(req.event_id)

    return {
        "status": "accepted",
        "event_id": req.event_id,
        "response": llm_response,
        "llm_metrics": _engine.llm_metrics,
    }


@app.post("/v4/ingest", status_code=200)
async def post_ingest(req: IngestRequest):
    """Ingest external document content into the cognitive chain."""
    if _engine is None:
        raise HTTPException(503, "API not initialized")

    try:
        from core.agent.v4.document.pipeline import DocumentIngestionPipeline
        from core.agent.v4.observation_compiler.document_domain_adapter import DocumentDomainAdapter

        pool = getattr(_engine, '_observation_pool', None)
        pipeline = DocumentIngestionPipeline(observation_pool=pool)

        if req.content:
            bundle = pipeline.ingest_text(req.content, source_path=req.source_path)
        else:
            bundle = pipeline.ingest_file(req.source_path)

        if bundle is None:
            raise HTTPException(400, "Ingest failed: no content parsed")

        # Push to pool if available
        if pool is not None:
            adapter = DocumentDomainAdapter()
            obs_bundle = adapter.adapt(bundle)
            pool.put(obs_bundle)

        return {
            "status": "ingested",
            "source_path": req.source_path,
            "observation_count": len(bundle.observations),
            "type_distribution": bundle.stats(),
        }
    except Exception as e:
        logger.warning("Ingest API failed: %s", e)
        raise HTTPException(500, f"Ingest error: {e}")


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
async def inspect(module: str, limit: int = 10, detail: bool = False):
    """Inspect system state. Returns structured JSON.

    Modules: observations, hypotheses, knowledge, skills, world, context.
    """
    if _engine is None:
        raise HTTPException(503, "API not initialized")

    try:
        if module == "observations":
            pool = getattr(_engine, '_observation_pool', None)
            if pool is None:
                return {"module": "observations", "count": 0, "items": []}
            bundles = pool.get_by_domain("all")[-limit:]
            items = []
            for b in bundles:
                items.append({
                    "id": str(getattr(b, 'bundle_id', '?')),
                    "domain": str(getattr(b, 'domain', '?')),
                    "summary": str(getattr(b, 'summary', ''))[:200],
                    "timestamp": getattr(b, 'timestamp', 0),
                })
            return {"module": "observations", "count": len(bundles), "items": items}

        elif module == "hypotheses":
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            items = []
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in list(pipe._match_vote._hypotheses.items())[:limit]:
                    bs = h.belief_state
                    items.append({
                        "id": hid,
                        "statement": h.statement,
                        "domain": h.domain,
                        "status": h.status,
                        "belief_state": {
                            "support": bs['support'], "conflict": bs['conflict'],
                            "stability": bs['stability'], "coverage": bs['coverage'],
                            "recency": bs['recency'], "novelty": bs['novelty'],
                            "entropy": bs['entropy'],
                        },
                        "domain_signals": h.domain_signals,
                    })
            return {"module": "hypotheses", "count": len(items), "items": items}

        elif module == "knowledge":
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            items = []
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in pipe._match_vote._hypotheses.items():
                    if h.status == "frozen":
                        items.append({
                            "id": hid, "statement": h.statement,
                            "domain": h.domain, "score": h.belief_score(),
                        })
            return {"module": "knowledge", "count": len(items), "items": items[:limit]}

        elif module == "skills":
            from core.agent.v4.skill_layer.skill_pool import SkillPool
            pool = SkillPool()
            skills = pool.list_all() if hasattr(pool, 'list_all') else []
            items = []
            for s in skills[:limit]:
                items.append({
                    "name": getattr(s, 'name', str(s)),
                    "domain": getattr(s, 'domain', ''),
                    "status": getattr(s, 'status', ''),
                    "usage": getattr(s, 'usage_count', 0),
                })
            return {"module": "skills", "count": len(items), "items": items}

        elif module == "world":
            graph = getattr(_engine, '_world_graph', None)
            if graph is None:
                return {"module": "world", "status": "not loaded", "nodes": 0, "edges": 0}
            top = sorted(graph.backbone.items(), key=lambda x: x[1], reverse=True)[:limit]
            backbone = [{"id": uid, "score": score} for uid, score in top]
            comms = {cid: len(units) for cid, units in list(graph.communities.items())[:limit]}
            return {
                "module": "world",
                "nodes": graph.node_count, "edges": graph.edge_count,
                "communities": len(graph.communities), "community_sizes": comms,
                "top_backbone": backbone,
            }

        elif module == "context":
            ctx = getattr(_engine, '_last_context', None)
            if ctx is None:
                return {"module": "context", "compiled": False}
            result = {"module": "context", "compiled": True, "intent": str(getattr(ctx, 'intent', ''))}
            if hasattr(ctx, 'total_items'):
                result["total_items"] = ctx.total_items
            if hasattr(ctx, 'items'):
                from collections import Counter
                sources = Counter(i.source for i in ctx.items)
                result["sources"] = {src: count for src, count in sources.most_common()}
            return result

        else:
            return {"module": module, "status": "unknown", "available_modules": [
                "observations", "hypotheses", "knowledge", "skills", "world", "context",
            ]}
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
