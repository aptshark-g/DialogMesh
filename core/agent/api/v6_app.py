"""DialogMesh v6 — Full FastAPI app with all frontend endpoints + chat.

Merges v6_app minimal entry + legacy api.py endpoints.
Register all of: v6_app routes + api.py routes from original serve().
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging, os, sys

logger = logging.getLogger(__name__)

app = FastAPI(title="DialogMesh v6", version="6.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ═══ Debug log sink ═══
from core.agent.api.debug_api import router as debug_router
app.include_router(debug_router)

# ═══ v6 Chat endpoints ═══
from core.agent.api.chat_api import router as chat_router, set_orchestrator
from core.agent.api.v3_session_api import router as v3_session_router
from core.agent.api.ws_bridge import ws_handler

app.include_router(chat_router)
app.include_router(v3_session_router)

# ═══ Pipeline Parameters ═══
from core.agent.api.pipeline_api import router as pipeline_router
app.include_router(pipeline_router)

# ═══ Unified stubs ═══
from core.agent.api.stubs_api import router as stubs_router
app.include_router(stubs_router)

# ═══ Legacy API routes (gracefully) ═══
_loaded = []

def _try_include(import_path: str, router_name: str):
    try:
        mod = __import__(import_path, fromlist=[router_name])
        router = getattr(mod, router_name, None)
        if router:
            app.include_router(router)
            _loaded.append(import_path)
            print(f"  ✅ {import_path}")
        return router
    except Exception as e:
        print(f"  ⚠️  SKIP {import_path}: {e}")
        return None

# v4/v6 legacy routes (frontend expects these)
_try_include("core.agent.api.api_gateway","router")  # /v6/gateway/*
_try_include("core.agent.api.api_sessions","router")  # /v6/sessions
_try_include("core.agent.api.api_trace","router")  # /v6/trace
_try_include("core.agent.api.api_profile","router")  # /v6/profile
_try_include("core.agent.api.api_objects","router")  # /v6/objects
_try_include("core.agent.api.api_rules","router")  # /v6/rules
_try_include("core.agent.api.api_relations","router")  # /v6/relations
_try_include("core.agent.api.api_parameters","router")  # /v6/parameters
_try_include("core.agent.api.api_context","router")  # /v6/context
_try_include("core.agent.api.api_pipeline","router")  # /v6/pipeline
_try_include("core.agent.api.api_metrics","router")  # /v6/metrics
_try_include("core.agent.api.api_persistence","router")  # /v6/persistence
_try_include("core.agent.api.api_meta","router")  # /v6/meta
_try_include("core.agent.api.api_abc","router")  # /v6/abc
_try_include("core.agent.api.api_mind","router")  # /v6/mind
_try_include("core.agent.api.api_versions","router")  # /v6/versions
_try_include("core.agent.api.api_subgraph","router")  # /v6/subgraph

# Legacy health endpoints (frontend probes)
@app.get("/v4/health")
@app.get("/v3/health")
async def legacy_health():
    return {"status": "ok", "version": "6.0.0"}

@app.post("/v3/session")
async def v3_session():
    return {"session_id": "demo", "status": "active"}

@app.websocket("/v6/ws")
async def ws_endpoint(ws):
    await ws_handler(ws)

@app.get("/v6/health")
async def v6_health():
    return {"status": "ok", "version": "6.0.0", "loaded": _loaded}

@app.get("/v6/status")
async def v6_status():
    return {"status": "running", "version": "6.0.0", "endpoints": len(_loaded) + 3}

@app.get("/v6/pcr")
async def v6_pcr_summary():
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        pcr = getattr(e, '_pcr_router', None)
        last = getattr(e, '_last_pcr', None)
    except: pcr = last = None
    return {"active": pcr is not None, "last_zone": getattr(last,'expectation','none') if last else 'none',
            "last_complexity": getattr(last,'complexity_level',0) if last else 0}

@app.get("/v6/intent")
async def v6_intent_summary():
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        last = getattr(e, '_last_intent', None)
    except: last = None
    return {"last_intent": getattr(last,'intent','unknown') if last else 'unknown',
            "confidence": getattr(last,'confidence',0) if last else 0}

@app.get("/v6/meta")
async def v6_meta_summary():
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        mc = getattr(e, '_meta_cognition', None)
    except: mc = None
    return {"reviewed": mc is not None, "handler": "active" if mc else "dormant"}

@app.get("/v6/feedback")
async def v6_feedback_summary():
    import os, json
    fb_path = "data/feedback.json"
    if os.path.exists(fb_path):
        with open(fb_path, encoding="utf-8") as f:
            return json.load(f)
    return {"feedback": [], "total": 0}


# ═══ Startup ═══
@app.on_event("startup")
async def startup():
    from core.agent.orchestrator.bootstrap_v6 import bootstrap
    orch = bootstrap()
    set_orchestrator(orch)
    logger.info("Orchestrator loaded — %d legacy routes", len(_loaded))
