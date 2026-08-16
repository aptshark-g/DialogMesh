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

# B4-1-P1 (2026-08-04): 薄中间件层 — rate_limiter/queue/session 挂 FastAPI
# （服务层降级为组件库后，缓冲由唯一生产入口内聚接入）。
from core.agent.api.service_middleware import (
    install_service_middleware, router as service_router,
)
install_service_middleware(app)
app.include_router(service_router)

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
from core.agent.api.stubs_api import router as stubs_router, v4_router
app.include_router(stubs_router)
app.include_router(v4_router)

# ═══ Legacy API routes (gracefully) ═══
_loaded = []

def _try_include(import_path: str, router_name: str):
    try:
        mod = __import__(import_path, fromlist=[router_name])
        router = getattr(mod, router_name, None)
        if router:
            app.include_router(router)
            _loaded.append(import_path)
            print(f"  [OK] {import_path}")
        return router
    except Exception as e:
        print(f"  [SKIP] {import_path}: {e}")
        return None

# v4/v6 legacy routes (frontend expects these)
_try_include("core.agent.api.api_gateway","router")  # /v6/gateway/*
_try_include("core.agent.api.api_annotate","router")  # /v6/annotate (真实 JSONL 注释系统)
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
_try_include("core.agent.api.api_viz_edit","router")  # /v6/edit/* (FE-1/G4 白盒编辑)

# Legacy health endpoints (frontend probes)
@app.get("/v4/health")
@app.get("/v3/health")
async def legacy_health():
    return {"status": "ok", "version": "6.0.0"}

@app.get("/v1/health")
async def v1_health():
    from core.agent.kernel import kernel_engine_status
    st = kernel_engine_status()
    return {"status": "ok" if st.get("running") else "degraded",
            "version": "6.0.0",
            "components": {"engine": "ok" if st.get("running") else "down"}}

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

@app.get("/v6/usage")
async def v6_usage():
    """Token usage stats（真实内核数据）。"""
    from core.agent.kernel import kernel_providers_tokens
    return kernel_providers_tokens()

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
    return {
        "active": pcr is not None,
        "last_zone": getattr(last, 'zone', getattr(last, 'expectation', 'none')) if last else 'none',
        "last_complexity": getattr(last, 'complexity_level', 0) if last else 0,
        "last_labels": getattr(last, 'labels', {}) if last else {},
    }

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
    # FE-1/G4 (2026-08-04): 白盒编辑 API 注入 engine
    # （api_viz_edit / api_gateway 均需 engine 才能操作真实数据）
    try:
        from core.agent.cli.engine import get_engine
        eng = get_engine()
        try:
            import core.agent.api.api_viz_edit as viz_mod
            if hasattr(viz_mod, "init"):
                viz_mod.init(eng)
                logger.info("api_viz_edit init(engine) — 白盒编辑已启用")
        except Exception as e:
            logger.warning("api_viz_edit init failed: %s", e)
        try:
            import core.agent.api.api_gateway as gw_mod
            if hasattr(gw_mod, "init"):
                gw_mod.init(eng)
        except Exception:
            pass
    except Exception as e:
        logger.warning("White-box edit engine inject failed: %s", e)
    # P1-① (2026-08-16): 主动体检 —— 元认知定期自检（无触发也巡检）。
    # daemon 线程, 启动延迟后首检, 周期 interval; DM_PROBE_ENABLED=0 可关。
    try:
        from core.agent.meta.probe import get_probe
        if os.environ.get("DM_PROBE_ENABLED", "1").lower() not in (
                "0", "false", "off", "no"):
            get_probe().start()
            logger.info("Proactive health probe started")
    except Exception as e:
        logger.warning("Proactive health probe start failed: %s", e)
    logger.info("Orchestrator loaded — %d legacy routes", len(_loaded))
