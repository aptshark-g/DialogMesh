"""v6 Frontend-compatible API stubs.

CRITICAL: Return format MUST match frontend TypeScript types exactly:
  - getSessions() → V6SessionListItem[]  (bare array, NOT {"sessions":[]})
  - getTrace() → V6TraceResponse          (object with traces field)
  - etc.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/v6", tags=["stubs"])


# ═══ Format: Bare arrays (frontend expects arrays directly) ═══

@router.get("/sessions")
async def get_sessions():
    return []  # NOT {"sessions": []} — frontend expects V6SessionListItem[]

@router.get("/trace")
async def get_trace():
    return {"traces": [], "note": "SpanTracer — real data pending"}

@router.get("/profile")
async def get_profile():
    return {"profile": {
        "oceAN_dims": {"O": 0.79, "C": 0.78, "E": 0.39, "A": 0.41, "N": 0.75},
        "raw_oceAN": {"openness": 0.79, "conscientiousness": 0.78,
                       "extraversion": 0.39, "agreeableness": 0.41, "neuroticism": 0.75},
        "bfi_10": {"C": 4.5},
        "inertia": {"by_weight": {"O": 0.05, "C": 0.03, "N": 0.08}},
        "applied": {},
        "corrections": []
    }}

@router.get("/abc")
async def get_abc():
    return {"abc_data": [], "count": 0}

@router.get("/mind")
async def get_mind():
    return {"mind_space": {}, "dimensions": 0}

@router.get("/mind/full")
async def get_mind_full():
    return {"mind_space": {}, "dimensions": 0, "raw": {}, "projections": []}

@router.get("/graph")
async def get_graph():
    return {"nodes": [], "edges": [], "count": 0}

@router.get("/discourse-tree")
async def get_discourse_tree():
    return {"tree": {}, "nodes": 0}

@router.get("/objects")
async def get_objects():
    return {"objects": [], "count": 0}

@router.get("/relations")
async def get_relations():
    return {"relations": [], "count": 0}

@router.get("/causal")
async def get_causal():
    return {"chains": [], "count": 0}

@router.get("/behavior")
async def get_behavior():
    return {"patterns": [], "count": 0}

@router.get("/behavior/patterns")
async def get_behavior_patterns():
    return {"patterns": [], "count": 0}

@router.get("/inertia")
async def get_inertia():
    return {"by_weight": {}, "total": 0}

@router.get("/engineering")
async def get_engineering():
    return {"rules": [], "count": 0}

@router.get("/engineering/modules")
async def get_engineering_modules():
    return {"modules": [], "count": 0}

@router.get("/rules")
async def get_rules():
    return []  # V6RulesResponse expects array

@router.get("/degradation")
async def get_degradation():
    return {"level": "none", "score": 0}

@router.get("/ttl")
async def get_ttl():
    return {"ttl_stats": {"by_state": {}}, "total": 0}

@router.get("/recursive-map")
async def get_recursive_map():
    return {"map": {"by_level": {}}, "count": 0}

@router.get("/pipeline")
async def get_pipeline_status():
    return {"status": "idle", "stages": 9}

@router.get("/extraction")
async def get_extraction():
    return {"extractions": [], "count": 0}

@router.get("/perspectives")
async def get_perspectives():
    return {"perspectives": [], "count": 0}

@router.get("/subgraph")
async def get_subgraph():
    return {"subgraph": {}, "cache_hit_rate": 0.0}

@router.get("/subgraph/cache")
async def get_subgraph_cache():
    return {"hit_rate": 0.0, "total_queries": 0}

@router.get("/persistence")
async def get_persistence():
    return {"graphs": [], "count": 0}

@router.get("/persistence/graphs")
async def get_persistence_graphs():
    return []

@router.get("/versions")
async def get_versions():
    return {"versions": [], "current": "6.0.0"}

@router.get("/versions/profile")
async def get_versions_profile():
    return {"versions": [], "current": "6.0.0"}

@router.get("/metrics")
async def get_metrics():
    return {"metrics": {}, "requests": 0}

@router.get("/router/modes")
async def get_router_modes():
    return {"modes": ["hybrid", "rule", "llm"], "active": "hybrid"}

@router.get("/providers")
async def get_providers_list():
    return []  # V6ProvidersResponse expects array

@router.get("/providers/tokens")
async def get_providers_tokens():
    return {"tokens": {}, "count": 0}


# ═══ MetaCenter ═══

@router.get("/meta/stats")
async def get_meta_stats():
    return {"stats": {"audits": 0, "decisions": 0, "archive_reopens": 0},
            "self_audit": {"by_verdict": {}}}

@router.get("/meta/queue")
async def get_meta_queue():
    return {"queue": [], "pending": 0}


# ═══ Gateway (these use the API from stubs, not real gateway) ═══

@router.get("/gateway/providers")
async def get_providers():
    try:
        from core.agent.gateway.gateway_v2 import GatewayV2
        return GatewayV2().list_providers()
    except Exception:
        return []

@router.get("/gateway/config")
async def get_gateway_config():
    return {"config": {}, "stats": {}}

@router.get("/gateway/usage")
async def get_gateway_usage():
    return {"all_sessions": {"by_provider": {}}}

@router.get("/gateway/stats")
async def get_gateway_stats():
    return {"providers": 0, "active": 0, "requests": 0, "errors_by_provider": {}}

@router.get("/gateway/health")
async def get_gateway_health():
    return {"status": "ok", "gateway": "v2", "circuits": {}, "engine_status": {}}
