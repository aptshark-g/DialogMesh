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

# ═══ v6 Chat endpoints ═══
from core.agent.api.chat_api import router as chat_router, set_orchestrator
from core.agent.api.ws_bridge import ws_handler
app.include_router(chat_router)

# ═══ Legacy API routes (gracefully) ═══
_loaded = []

def _try_include(import_path: str, router_name: str):
    try:
        mod = __import__(import_path, fromlist=[router_name])
        router = getattr(mod, router_name, None)
        if router:
            app.include_router(router)
            _loaded.append(import_path)
        return router
    except Exception as e:
        logger.debug("Skip %s: %s", import_path, e)
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

@app.websocket("/v6/ws")
async def ws_endpoint(ws):
    await ws_handler(ws)

@app.get("/v6/health")
async def v6_health():
    return {"status": "ok", "version": "6.0.0", "loaded": _loaded}

@app.get("/v6/status")
async def v6_status():
    return {"status": "running", "version": "6.0.0", "endpoints": len(_loaded) + 3}


# ═══ Startup ═══
@app.on_event("startup")
async def startup():
    from core.agent.orchestrator.bootstrap_v6 import bootstrap
    orch = bootstrap()
    set_orchestrator(orch)
    logger.info("Orchestrator loaded — %d legacy routes", len(_loaded))
