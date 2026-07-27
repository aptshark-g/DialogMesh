"""v6 Frontend-compatible API stubs — EXACT match to frontend TypeScript types.

Each return dict maps 1:1 to the corresponding V6*Response interface.
Additions/changes must be verified against src/types/api.ts.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v6", tags=["stubs"])


# ═══════════════════════════════════════════════════════
# Profile — V6ProfileResponse
# ═══════════════════════════════════════════════════════
@router.get("/profile")
async def get_profile():
    # Read actual session count for turn_count
    import json, os
    turn_count = 0
    try:
        if os.path.exists("data/v3_sessions.json"):
            with open("data/v3_sessions.json") as f:
                sessions = json.load(f)
            turn_count = sum(len(s.get("messages", [])) for s in sessions.values())
    except Exception:
        pass
    # Base profile + dynamic turn count
    return {
        "oceAN_dims": {"O": 0.79, "C": 0.78, "E": 0.39, "A": 0.41, "N": 0.75},
        "mbti": "INFJ",
        "turn_count": turn_count,
        "top_dimensions": ["O", "N", "C"],
        "bfi_history": turn_count // 2 if turn_count > 0 else 0,
        "bfi_latest": {"C": 4.5},
    }


# ═══════════════════════════════════════════════════════
# Trace — V6TraceResponse
# ═══════════════════════════════════════════════════════
@router.get("/trace")
async def get_trace():
    return {
        "reason_distribution": {},
        "avg_confidence": 0.0,
        "total": 0,
    }


# ═══════════════════════════════════════════════════════
# ABC — V6AbcResponse
# ═══════════════════════════════════════════════════════
@router.get("/abc")
async def get_abc():
    return {}


# ═══════════════════════════════════════════════════════
# Mind — V6MindResponse
# ═══════════════════════════════════════════════════════
@router.get("/mind")
async def get_mind():
    return {}

@router.get("/mind/full")
async def get_mind_full():
    return {"dimensions": 0, "raw": {}, "projections": []}


# ═══════════════════════════════════════════════════════
# Graph — V6GraphResponse
# ═══════════════════════════════════════════════════════
@router.get("/graph")
async def get_graph():
    return {"nodes": [], "edges": [], "subgraph_nodes": []}


# ═══════════════════════════════════════════════════════
# Discourse — V6DiscourseTreeResponse
# ═══════════════════════════════════════════════════════
@router.get("/discourse-tree")
async def get_discourse_tree():
    return {"blocks": [], "total": 0}


# ═══════════════════════════════════════════════════════
# Objects — V6ObjectsResponse
# ═══════════════════════════════════════════════════════
@router.get("/objects")
async def get_objects():
    return {"nodes": [], "edges": [], "total_objects": 0}


# ═══════════════════════════════════════════════════════
# Rules — V6RulesResponse
# ═══════════════════════════════════════════════════════
@router.get("/rules")
async def get_rules():
    return {"rules": [], "total": 0}


# ═══════════════════════════════════════════════════════
# Relations — V6RelationsResponse
# ═══════════════════════════════════════════════════════
@router.get("/relations")
async def get_relations():
    return {}


# ═══════════════════════════════════════════════════════
# Causal — V6CausalResponse
# ═══════════════════════════════════════════════════════
@router.get("/causal")
async def get_causal():
    return {}


# ═══════════════════════════════════════════════════════
# Behavior — V6BehaviorResponse
# ═══════════════════════════════════════════════════════
@router.get("/behavior")
async def get_behavior():
    return {}

@router.get("/behavior/patterns")
async def get_behavior_patterns():
    return {"stats": {"total_patterns": 0, "user_approved": 0, "frequency_by_type": {}}, "patterns": []}

@router.get("/inertia")
async def get_inertia():
    return {"total_patterns": 0, "stable": 0, "confirmed": 0, "breaking": 0,
            "by_weight": {}, "constraints": []}


@router.get("/behavior/predict")
async def get_behavior_predictions():
    return {"recent_actions": [], "predictions": {}}


# ═══════════════════════════════════════════════════════
# Engineering — V6EngineeringResponse
# ═══════════════════════════════════════════════════════
@router.get("/engineering")
async def get_engineering():
    return {}

@router.get("/engineering/modules")
async def get_engineering_modules():
    return {"modules": [], "count": 0}


# ═══════════════════════════════════════════════════════
# Pipeline — V6PipelineResponse
# ═══════════════════════════════════════════════════════
@router.get("/pipeline")
async def get_pipeline_status():
    return {}


# ═══════════════════════════════════════════════════════
# Extraction — V6ExtractionResponse
# ═══════════════════════════════════════════════════════
@router.get("/extraction")
async def get_extraction():
    return {}


# ═══════════════════════════════════════════════════════
# Perspectives — V6PerspectivesResponse
# ═══════════════════════════════════════════════════════
@router.get("/perspectives")
async def get_perspectives():
    return {}


# ═══════════════════════════════════════════════════════
# Parameters — V6ParameterItem wrapper
# ═══════════════════════════════════════════════════════
@router.get("/parameters")
async def get_parameters():
    return {}


# ═══════════════════════════════════════════════════════
# Context
# ═══════════════════════════════════════════════════════
@router.get("/context")
async def get_context():
    return {}


# ═══════════════════════════════════════════════════════
# Subgraph
# ═══════════════════════════════════════════════════════
@router.get("/subgraph")
async def get_subgraph():
    return {}

@router.get("/subgraph/cache")
async def get_subgraph_cache():
    return {"hit_rate": 0.0, "total_queries": 0}


# ═══════════════════════════════════════════════════════
# DeepChain — Belief + Subgraph
# ═══════════════════════════════════════════════════════
@router.get("/belief")
async def get_belief(session_id: str = "default"):
    return {"total_hypotheses": 0, "locked": 0, "avg_evidence": 0, "by_hypothesis": {}}

@router.get("/subgraph/{perspective}")
async def get_subgraph_by_perspective(perspective: str):
    return {"perspective": perspective, "domains": {}, "entries": [], "total_tokens": 0, "budget": 0}


# ═══════════════════════════════════════════════════════
# Persistence — V6PersistenceResponse
# ═══════════════════════════════════════════════════════
@router.get("/persistence")
async def get_persistence():
    return {
        "annotation_store": {},
        "unified_store": {},
        "oceAN_saved": False,
        "rules_saved": False,
    }

@router.get("/persistence/graphs")
async def get_persistence_graphs():
    return []  # bare array — V6SessionListItem[]


# ═══════════════════════════════════════════════════════
# Annotations + Corrections
# ═══════════════════════════════════════════════════════
@router.get("/annotate")
async def get_annotations():
    return {"annotations": [], "total": 0}

@router.get("/annotate/stats")
async def get_annotation_stats():
    return {"total": 0, "by_author": {}, "by_date": {}}

@router.get("/profile/corrections")
async def get_profile_corrections():
    return {"corrections": [], "total": 0}


# ═══════════════════════════════════════════════════════
# Sessions — bare array (V6SessionListItem[])
# ═══════════════════════════════════════════════════════
@router.get("/sessions")
async def get_sessions():
    return []


# ═══════════════════════════════════════════════════════
# Versions
# ═══════════════════════════════════════════════════════
@router.get("/versions")
async def get_versions():
    return {}

@router.get("/versions/profile")
async def get_versions_profile():
    return {"commits": [], "target": None, "current": "6.0.0"}


# ═══════════════════════════════════════════════════════
# Router — V6RouterModesResponse
# ═══════════════════════════════════════════════════════
@router.get("/router/modes")
async def get_router_modes():
    return {
        "available": True,
        "modes": [{"name": "hybrid", "description": "Rule + LLM"}],
        "active": "hybrid",
        "force_mode": None,
        "disabled": {"remote": False, "small_model": False},
    }


# ═══════════════════════════════════════════════════════
# Providers — V6ProvidersResponse
# ═══════════════════════════════════════════════════════
@router.get("/providers")
async def get_providers():
    return {
        "active": {"name": "", "display_name": "", "kind": "", "base_url": ""},
        "failover": {
            "primary": "",
            "fallback": "",
            "active_idx": 0,
            "failures": 0,
        },
    }

@router.get("/providers/tokens")
async def get_providers_tokens():
    return {"current": {"turns": 0, "est_tokens": 0}, "all_sessions": {"est_tokens": 0, "turns": 0}}


# ═══════════════════════════════════════════════════════
# Metrics — V6MetricsResponse
# ═══════════════════════════════════════════════════════
@router.get("/metrics")
async def get_metrics():
    return {}


# ═══════════════════════════════════════════════════════
# MetaCenter
# ═══════════════════════════════════════════════════════
@router.get("/meta/stats")
async def get_meta_stats():
    return {"stats": {"decisions_total": 0, "pending": 0, "queue_size": 0, "reviewed": 0,
                      "audits": 0, "archive_reopens": 0},
            "self_audit": {"by_verdict": {}}}


@router.get("/meta/queue")
async def get_meta_queue():
    return {"queue": [], "pending": 0}


# ═══════════════════════════════════════════════════════
# Degradation / TTL / RecursiveMap
# ═══════════════════════════════════════════════════════
@router.get("/degradation")
async def get_degradation():
    return {"level": "none", "score": 0}

@router.get("/ttl")
async def get_ttl():
    return {"ttl_stats": {"by_state": {}}, "total": 0}

@router.get("/recursive-map")
async def get_recursive_map():
    return {"map": {"by_level": {}}, "count": 0}


# ═══════════════════════════════════════════════════════
# Gateway — handled by api_gateway.py (proxies switch gateway)
# DO NOT define gateway routes here — they conflict.
# ═══════════════════════════════════════════════════════