"""v6 Trace + Meta + Gateway API stubs — frontend compatible.

Real data flows in gradually as backends mature.
"""

from fastapi import APIRouter

trace_router = APIRouter(prefix="/v6", tags=["trace"])
meta_router = APIRouter(prefix="/v6", tags=["meta"])
gateway_router = APIRouter(prefix="/v6", tags=["gateway"])


# ═══ Trace / SpanTracer ═══

@trace_router.get("/trace")
async def get_trace():
    try:
        from core.agent.monitor.trace_log import get_tracer
        tracer = get_tracer()
        return {"traces": tracer.recent_traces(20)}
    except Exception:
        return {"traces": [], "note": "SpanTracer not loaded"}

@trace_router.get("/trace/{trace_id}")
async def get_trace_detail(trace_id: str):
    try:
        from core.agent.monitor.trace_log import get_tracer
        return get_tracer().get_trace(trace_id)
    except Exception:
        return {"trace_id": trace_id, "error": "Not found"}


# ═══ Relations / Causal / Behavior / Engineering (DeepChain) ═══

@trace_router.get("/relations")
async def get_relations():
    return {"relations": [], "count": 0, "note": "RelationSubstrate — real data pending"}

@trace_router.get("/causal")
async def get_causal():
    return {"chains": [], "count": 0}

@trace_router.get("/behavior")
async def get_behavior():
    return {"patterns": [], "count": 0}

@trace_router.get("/engineering")
async def get_engineering():
    return {"rules": [], "count": 0}


# ═══ Graph / Objects / DiscourseTree / Subgraph (ConversationGraph) ═══

@trace_router.get("/graph")
async def get_graph():
    return {"nodes": [], "edges": [], "count": 0}

@trace_router.get("/objects")
async def get_objects():
    return {"objects": [], "count": 0}

@trace_router.get("/discourse-tree")
async def get_discourse_tree():
    return {"tree": {}, "nodes": 0}

@trace_router.get("/subgraph")
async def get_subgraph():
    return {"subgraph": {}, "cache_hit_rate": 0.0}

@trace_router.get("/subgraph/cache")
async def get_subgraph_cache():
    return {"hit_rate": 0.0, "total_queries": 0}

@trace_router.get("/pipeline")
async def get_pipeline_status():
    return {"status": "idle", "stages": 9}

@trace_router.get("/extraction")
async def get_extraction():
    return {"extractions": [], "count": 0}

@trace_router.get("/perspectives")
async def get_perspectives():
    return {"perspectives": [], "count": 0}

@trace_router.get("/mind")
async def get_mind():
    return {"mind_space": {}, "dimensions": 0}

@trace_router.get("/mind/full")
async def get_mind_full():
    return {"mind_space": {}, "dimensions": 0, "raw": {}, "projections": []}

@trace_router.get("/abc")
async def get_abc():
    return {"abc_data": [], "count": 0}

@trace_router.get("/sessions")
async def get_sessions():
    return {"sessions": [], "count": 0}

@trace_router.get("/persistence")
async def get_persistence():
    return {"persistence": {}, "graphs": 0}

@trace_router.get("/persistence/graphs")
async def get_persistence_graphs():
    return {"graphs": [], "count": 0}

@trace_router.get("/versions")
async def get_versions():
    return {"versions": [], "current": "6.0.0"}

@trace_router.get("/metrics")
async def get_metrics():
    return {"metrics": {}, "requests": 0}

@trace_router.get("/profile")
async def get_profile():
    return {"profile": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}}


# ═══ MetaCenter ═══

@meta_router.get("/meta/stats")
async def get_meta_stats():
    return {"stats": {"audits": 0, "decisions": 0, "archive_reopens": 0}, "note": "MetaTree stats"}

@meta_router.get("/meta/queue")
async def get_meta_queue():
    return {"queue": [], "pending": 0}


# ═══ Gateway ═══

@gateway_router.get("/gateway/providers")
async def get_providers():
    try:
        from core.agent.gateway.gateway_v2 import GatewayV2
        gw = GatewayV2()
        return {"providers": gw.list_providers()}
    except Exception:
        return {"providers": [], "note": "GatewayV2 not loaded"}

@gateway_router.get("/gateway/stats")
async def get_gateway_stats():
    try:
        from core.agent.gateway.gateway_v2 import GatewayV2
        gw = GatewayV2()
        return gw.stats
    except Exception:
        return {"providers": 0, "active": 0, "requests": 0}

@gateway_router.get("/gateway/health")
async def get_gateway_health():
    return {"status": "ok", "gateway": "v2", "upstream": "unchecked"}
