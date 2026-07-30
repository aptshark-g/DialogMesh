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

# ═══ White-box Audit (DESIGN_AUDIT) ═══

@app.get("/v6/audit")
async def v6_audit():
    """Full white-box audit: module states, data sizes, persistence status."""
    import os, json as _json, time
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
    except:
        e = None
    
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(root, "data")
    
    def _disk_info(rel):
        fp = os.path.join(root, rel)
        if os.path.exists(fp):
            try:
                with open(fp, encoding='utf-8') as f:
                    d = _json.load(f)
                return len(d) if isinstance(d, list) else (1 if d else 0)
            except: return -1
        return 0
    
    return {
        "timestamp": int(time.time()),
        "reachability": {
            "profile": bool(getattr(e, '_ocean_analyst', None)),
            "meta": bool(getattr(e, '_meta_cognition', None)),
            "mind": bool(getattr(e, '_mind', None)),
            "abc": bool(getattr(e, '_abc', None)),
            "engineering": bool(getattr(e, '_engineering_knowledge', None)),
            "behavior": bool(getattr(e, '_behavior_graph_adapter', None)),
            "discourse": bool(getattr(e, '_discourse_tree', None)),
            "decider": bool(getattr(e, '_decider', None)),
            "inertia": bool(getattr(e, '_inertia_graph', None)),
            "rag": bool(getattr(e, '_rag_bridge', None)),
            "learning": bool(getattr(e, '_learning_sources', None)),
        },
        "editability": {
            "profile_editable": hasattr(getattr(e, '_ocean_analyst', object()), 'update_dimension') if e else False,
            "rules_editable": bool(getattr(e, '_abc', None)),
            "parameters_editable": bool(getattr(e, '_parameter_registry', None)),
        },
        "learning_loop": {
            "pipeline_runs": getattr(getattr(e, '_state_machine', None), '_tick', 0) if e else 0,
            "behavior_edges": getattr(getattr(getattr(e, '_behavior_graph_adapter', None), 'stats', lambda:{})(), 'edge_count', 0) if e else 0,
            "meta_reviews": bool(getattr(getattr(e, '_meta_cognition', None), '_reviews', None)) if e else False,
        },
        "persistence": {
            "annotations": _disk_info("data/annotations.json"),
            "corrections": _disk_info("data/corrections.json"),
            "feedback": _disk_info("data/feedback.json"),
            "sessions": _disk_info("data/v3_sessions.json"),
            "discourse_state": _disk_info("data/discourse_state.json"),
            "behavior_graph": _disk_info("data/behavior_graph.json"),
            "event_log": os.path.exists(os.path.join(data_dir, "event_log.db")),
        },
        "hotstore": getattr(getattr(e, '_storage', None), 'hot', None).stats() if e and hasattr(e, '_storage') else {},
    }

@app.get("/v6/audit/history")
async def v6_audit_history():
    """Recent audit log entries."""
    import os, json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(root, "data", "audit_log.json")
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            data = _json.load(f)
        return {"entries": len(data) if isinstance(data, list) else 0, "recent": data[-5:] if isinstance(data, list) else []}
    return {"entries": 0, "recent": []}

@app.get("/v6/audit/recent")
async def v6_audit_recent():
    """Last N audit events from event log."""
    import os, json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(root, "data", "event_log.db")
    exists = os.path.exists(fp)
    return {"event_log_exists": exists, "size_bytes": os.path.getsize(fp) if exists else 0}

# Missing DESIGN_AUDIT endpoints

@app.get("/v6/gateway/providers")
async def v6_gateway_providers():
    """Gateway provider list."""
    import os, json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(root, "gateway", "provider.yaml")
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            return {"providers": f.read()}
    return {"providers": "provider.yaml not found"}

@app.get("/v6/usage")
async def v6_usage():
    """Token usage stats."""
    return {"total_tokens": 0, "total_cost": 0, "by_model": {}}

@app.get("/v6/annotations")
async def v6_annotations_summary():
    """Annotation summary from disk."""
    import os, json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(root, "data", "annotations.json")
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            data = _json.load(f)
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        return {"annotations_count": count, "recent": str(data[-1])[:200] if isinstance(data,list) and data else None}
    return {"annotations_count": 0}

@app.get("/v6/corrections")
async def v6_corrections_summary():
    """Correction summary from disk."""
    import os, json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(root, "data", "corrections.json")
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            data = _json.load(f)
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        return {"corrections_count": count, "recent": str(data[-1])[:200] if isinstance(data,list) and data else None}
    return {"corrections_count": 0}

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
