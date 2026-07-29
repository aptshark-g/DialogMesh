"""v6 Frontend-compatible API stubs — EXACT match to frontend TypeScript types.

Each return dict maps 1:1 to the corresponding V6*Response interface.
Additions/changes must be verified against src/types/api.ts.
"""

from fastapi import APIRouter
import logging

router = APIRouter(prefix="/v6", tags=["stubs"])
logger = logging.getLogger("stubs_api")

# ── Engine access helper ──
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        try:
            from core.agent.cli.engine import get_engine as _ge
            _engine = _ge()
        except Exception:
            return None
    return _engine

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
        "oceAN_labels": {
            "O": "开放性 (Openness)", "C": "尽责性 (Conscientiousness)",
            "E": "外向性 (Extraversion)", "A": "宜人性 (Agreeableness)",
            "N": "神经质 (Neuroticism)", "NC": "认知需求 (Need for Cognition)",
            "CS": "沟通风格 (Communication Style)", "DK": "领域知识 (Domain Knowledge)",
            "MS": "元认知 (Meta-Cognition)", "CL": "好奇心 (Curiosity Level)"
        },
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
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    rf = os.path.join(root, "data", "neuro_symbolic_rules.json")
    rules_data = json.load(open(rf, encoding="utf-8")) if os.path.exists(rf) else {"rules": []}
    if isinstance(rules_data, list):
        rules = rules_data
    else:
        rules = list(rules_data.values()) if rules_data else []
    return {"rules": len(rules), "recent_rules": [r.get("antecedent","")[:50] if isinstance(r,dict) else str(r)[:50] for r in rules[-5:]]}

@router.get("/mind")
async def get_mind():
    return {"dimensions": 8, "modules_available": ["assoc","pcr","intent","discourse","blueprint","decider","meta","behavior"]}

@router.get("/mind/full")
async def get_mind_full():
    return {"dimensions": 0, "raw": {}, "projections": []}

# ═══════════════════════════════════════════════════════
# Graph — V6GraphResponse
# ═══════════════════════════════════════════════════════
@router.get("/graph")
async def get_graph():
    import json, os
    nodes, edges, sub = [], [], []
    try:
        if os.path.exists("data/v3_sessions.json"):
            sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
            for sid, s in sessions.items():
                nodes.append({"id": sid, "label": f"Session {sid[:8]}", "type": "session", "size": len(s.get("messages",[]))})
        sub = [n["id"] for n in nodes[:5]]
    except: pass
    return {"nodes": nodes, "edges": edges, "subgraph_nodes": sub}

# ═══════════════════════════════════════════════════════
# Discourse — V6DiscourseTreeResponse
# ═══════════════════════════════════════════════════════
@router.get("/discourse-tree")
async def get_discourse_tree():
    import json, os
    blocks = []
    try:
        if os.path.exists("data/v3_sessions.json"):
            with open("data/v3_sessions.json") as f:
                sessions = json.load(f)
            for sid, s in sessions.items():
                msgs = s.get("messages", [])
                for i, m in enumerate(msgs):
                    blocks.append({
                        "id": f"block_{sid[:6]}_{i}",
                        "session_id": sid[:8],
                        "role": m.get("role", "user"),
                        "content": m.get("content", "")[:100],
                        "turn_index": i,
                        "timestamp": s.get("created_at", 0) + i * 10,
                    })
    except Exception:
        pass
    return {"blocks": blocks, "total": len(blocks)}

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
    return {"edge_count": 0, "patterns": ["cause/effect","sequence","reference","is-a","part-of"]}

@router.get("/causal")
async def get_causal():
    return {"relations": [], "substrates": 0}

# ═══════════════════════════════════════════════════════
# Behavior — V6BehaviorResponse
# ═══════════════════════════════════════════════════════
@router.get("/behavior")
async def get_behavior():
    return {"edge_count": 0, "patterns": [], "predictions": []}

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
    return {"constraints": [], "propagations": 0, "violations": 0}

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
    import json, os
    from core.agent.cli.engine import PROJECT_ROOT
    tc = 0
    try:
        sp = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
        if os.path.exists(sp):
            sessions = json.load(open(sp, encoding="utf-8"))
            tc = sum(len(s.get("messages",[])) for s in sessions.values())
    except: pass
    return {
        "annotation_store": {"status": "running", "records": tc},
        "unified_store": {"status": "running", "records": tc},
        "oceAN_saved": True,
        "rules_saved": True,
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
    import json, os
    sessions = []
    try:
        if os.path.exists("data/v3_sessions.json"):
            for sid, s in json.load(open("data/v3_sessions.json", encoding="utf-8")).items():
                msgs = s.get("messages", [])
                size = sum(len(json.dumps(m)) for m in msgs)
                sessions.append({"name": sid, "size": size})
    except: pass
    return sessions

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
@router.get("/session/{filename}")
async def get_session_detail(filename: str):
    """Return session detail data from v3_sessions.json."""
    import json, os
    # stubs_api.py is at <root>/core/agent/api/stubs_api.py — go up 4 levels
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sess_path = os.path.join(root, "data", "v3_sessions.json")
    if os.path.exists(sess_path):
        with open(sess_path, encoding="utf-8") as f:
            sessions = json.load(f)
        if filename in sessions:
            return sessions[filename].get("messages", [])
    return []

@router.get("/metrics")
async def get_metrics():
    return {"engine_uptime": 0, "subsystems_loaded": 32, "total_turn_count": 0}

@router.get("/meta/stats")
async def get_meta_stats():
    import json, os
    turn_count = 0
    try:
        if os.path.exists("data/v3_sessions.json"):
            sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
            turn_count = sum(len(s.get("messages",[])) for s in sessions.values())
    except: pass
    return {"queue_size": turn_count//2, "pending": 0, "reviewed": turn_count,
            "decisions_total": turn_count, "self_audit": {"accuracy": 0.85, "by_verdict": {"pass": turn_count}}}

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
# ═══════════════════════════════════════════════════════
# Gateway — V6GatewayProvidersResponse
# ═══════════════════════════════════════════════════════
@router.get("/gateway/providers")
async def get_gateway_providers():
    return {
        "providers": [
            {"name": "deepseek", "display_name": "DeepSeek", "configured": True, "healthy": True,
             "base_url": "https://api.deepseek.com", "models": [
                 {"id": "deepseek-v4-flash", "display": "V4 Flash", "context": 65536, "cost_in": 0.27, "cost_out": 1.10} if x == 0 else None for x in range(1)
             ]},
            {"name": "deepseek-pro", "display_name": "DeepSeek Pro", "configured": True, "healthy": True,
             "base_url": "https://api.deepseek.com", "models": [
                 {"id": "deepseek-v4-pro", "display": "V4 Pro", "context": 65536, "cost_in": 0.55, "cost_out": 2.19}
             ]},
        ],
        "active_provider": "deepseek",
        "active_model": "deepseek-v4-flash",
    }

@router.get("/gateway/tokens")
async def get_gateway_tokens():
    return {"total_tokens": 0, "by_provider": {}}

@router.get("/gateway/usage")
async def get_gateway_usage():
    return {"by_model": {}, "total_calls": 0}

@router.get("/gateway/config")
async def get_gateway_config():
    return {"providers": 2, "models": 2, "checkpoint": False}

@router.get("/gateway/stats")
async def get_gateway_stats():
    return {"uptime_hours": 0, "last_error": None, "active_since": ""}

@router.get("/gateway/health")
async def get_gateway_health():
    return {"status": "healthy", "last_check": "", "latency_ms": 2}

@router.get("/providers")
async def get_providers():
    return await get_gateway_providers()
