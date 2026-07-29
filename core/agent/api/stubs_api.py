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
    """Read profile from disk state (v3_session_api persists there)."""
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    pp = os.path.join(root, "data", "profile_state.json")
    dims = {"O":0.5,"C":0.5,"E":0.5,"A":0.5,"N":0.5}
    turn_count = 0
    if os.path.exists(pp):
        try:
            saved = json.load(open(pp, encoding="utf-8"))
            if "dims" in saved: dims = saved["dims"]
            turn_count = saved.get("turn_count", 0)
        except: pass
    # Engine dims override disk only if disk dims are defaults
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        tc = getattr(e, '_turn_counter', turn_count)
        if tc > turn_count: turn_count = tc
        # Only use engine dims if disk hasn't changed from defaults
        all_default = all(abs(v - 0.5) < 0.01 for v in dims.values())
        if all_default:
            ocean = getattr(e, '_ocean_analyst', None)
            if ocean and hasattr(ocean, 'profile') and hasattr(ocean.profile, 'dims'):
                edims = {k: float(v) for k, v in ocean.profile.dims.items()}
                if any(abs(v - 0.5) > 0.01 for v in edims.values()):
                    dims = edims
    except: pass
    return {
        "oceAN_dims": dims,
        "mbti": "INFJ",
        "turn_count": turn_count,
        "top_dimensions": sorted(dims.keys())[:3],
    }

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
    """Return discourse block tree from engine (SyntacticDecomposer + MacroMicroQuantizer),
    fallback to v3_sessions.json."""
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    nodes, edges = [], []

    # Try engine's DiscourseBlockTree first (real algorithmic tree)
    try:
        from core.agent.cli.engine import get_engine, get_session
        e = get_engine()
        tree_mgr = getattr(e, '_discourse_tree', None)
        if tree_mgr:
            sid = get_session()
            rel = tree_mgr.get_block_relations(sid)
            blocks = rel.get("blocks", {})
            relations = rel.get("relations", [])
            for bid, binfo in blocks.items():
                nodes.append({
                    "id": bid,
                    "label": binfo.get("summary", "") or f"Block {bid[:8]}",
                    "type": "session",
                    "size": binfo.get("edus", 1),
                    "temperature": binfo.get("temperature", "warm"),
                    "entities": binfo.get("entities", [])[:3],
                })
            for r in relations:
                edges.append({
                    "id": f"{r['from']}→{r['to']}",
                    "source": r["from"], "target": r["to"],
                    "type": r.get("type", "related"),
                })
            if nodes:
                return {"nodes": nodes, "edges": edges, "subgraph_nodes": [n["id"] for n in nodes[:8]]}
    except Exception:
        pass
    # Read discourse blocks from most active session
    try:
        sp = os.path.join(root, "data", "v3_sessions.json")
        if os.path.exists(sp):
            sessions = json.load(open(sp, encoding="utf-8"))
            # Find session with most messages
            best_sid, best_count = None, 0
            for sid, s in sessions.items():
                c = len(s.get("messages", []))
                if c > best_count:
                    best_sid, best_count = sid, c
            # Build graph from that session's blocks
            if best_sid:
                # Try reading task_graph for that session
                tgp = os.path.join(root, "data", "task_graphs", f"{best_sid}.json")
                if os.path.exists(tgp):
                    tg = json.load(open(tgp, encoding="utf-8"))
                    for n in tg.get("nodes", []):
                        nodes.append({
                            "id": n.get("id", n.get("name", "?")),
                            "label": n.get("name", n.get("label", "?"))[:40],
                            "type": "task",
                            "status": n.get("status", "pending"),
                            "size": len(n.get("desc", "")) if n.get("desc") else 1,
                        })
                    for e in tg.get("edges", []):
                        edges.append({
                            "id": f"{e.get('from','')}→{e.get('to','')}",
                            "source": e.get("from", ""),
                            "target": e.get("to", ""),
                            "type": "dependency",
                        })
    except: pass

    # Fallback: show sessions if task_graph too small
    if len(nodes) < 3:
        try:
            sp2 = os.path.join(root, "data", "v3_sessions.json")
            if os.path.exists(sp2):
                sessions = json.load(open(sp2, encoding="utf-8"))
                for sid, s in list(sessions.items())[:20]:
                    msgs = s.get("messages", [])
                    # Use first meaningful message as label
                    label = sid[:8]
                    for m in msgs:
                        if m.get("role") == "user" and m.get("content", "").strip():
                            label = m.get("content", "")[:40]
                            break
                    nodes.append({
                        "id": sid, "label": label, "type": "session",
                        "size": len(msgs),
                    })
        except: pass

    return {"nodes": nodes, "edges": edges, "subgraph_nodes": [n["id"] for n in nodes[:8]]}

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
    """Return semantic objects from pipeline + graph format."""
    import json, os
    # Try engine pipeline first
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        sp = getattr(e, '_semantic_pipeline', None)
        if sp:
            g = sp.to_graph()
            return {"nodes": g["nodes"], "edges": g["edges"], "total_objects": len(g["nodes"])}
    except Exception:
        pass
    # Fallback: disk
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    wp = os.path.join(root, "data", "world_objects.json")
    nodes = []
    if os.path.exists(wp):
        try:
            data = json.load(open(wp, encoding="utf-8"))
            for k, v in data.items():
                if isinstance(v, dict):
                    nodes.append({"id": k, "label": v.get("name", k), "type": v.get("obj_type", "concept"),
                                   "description": v.get("description", ""), "confidence": v.get("confidence", 0.5)})
        except: pass
    return {"nodes": nodes, "edges": [], "total_objects": len(nodes)}
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
    """Read from engine's CausalPlanner or BehaviorGraphAdapter."""
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        cp = getattr(e, '_causal_planner', None)
        if cp and hasattr(cp, 'get_recent_chain'):
            recent = cp.get_recent_chain(20)
            return {"edge_count": len(recent), "patterns": [], "predictions": [],
                    "recent_edges": [{"action": getattr(s, 'event_type', str(s)),
                                     "ts": getattr(s, 'timestamp', 0)} for s in recent[:10]]}
        bg = getattr(e, '_behavior_graph_adapter', None)
        if bg:
            chain = bg.get_recent_chain(20)
            return {"edge_count": len(chain.steps) if hasattr(chain, 'steps') else 0,
                    "patterns": [], "predictions": []}
    except Exception:
        pass
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
async def get_engineering_page():
    """Read engineering rules from disk."""
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(root, "data")
    rules, annotations, corrections = [], [], []
    rp = os.path.join(data_dir, "engineering_rules.json")
    if os.path.exists(rp):
        try: rules = json.load(open(rp, encoding="utf-8")).get("rules", [])
        except: pass
    ap = os.path.join(data_dir, "annotations.json")
    if os.path.exists(ap):
        try: annotations = json.load(open(ap, encoding="utf-8"))
        except: pass
    cp = os.path.join(data_dir, "corrections.json")
    if os.path.exists(cp):
        try: corrections = json.load(open(cp, encoding="utf-8"))
        except: pass
    return {
        "rules": rules, "total_rules": len(rules),
        "annotations": annotations, "violations": len(annotations),
        "corrections": corrections,
        "constraints": [r.get("pattern","") for r in rules if r.get("type")=="constraint"],
        "propagations": len(annotations),
    }

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
    """Read engine state from disk files — reflects real pipeline state."""
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(root, "data")
    tc = 0
    try:
        sp = os.path.join(data_dir, "v3_sessions.json")
        if os.path.exists(sp):
            sessions = json.load(open(sp, encoding="utf-8"))
            tc = sum(len(s.get("messages",[])) for s in sessions.values())
    except: pass
    result = {
        "annotation_store": {"status": "running", "records": tc},
        "unified_store": {"status": "running", "records": tc},
        "oceAN_saved": False, "rules_saved": False,
        "discourse_blocks": 0, "behavior_edges": 0,
        "profile_updated": False,
    }
    # Read discourse state
    dp = os.path.join(data_dir, "discourse_state.json")
    if os.path.exists(dp):
        try:
            ds = json.load(open(dp, encoding="utf-8"))
            result["discourse_blocks"] = len(ds.get("blocks", {}))
        except: pass
    # Read behavior state
    bp = os.path.join(data_dir, "behavior_state.json")
    if os.path.exists(bp):
        try:
            bs = json.load(open(bp, encoding="utf-8"))
            result["behavior_edges"] = bs.get("edges", 0)
        except: pass
    # Read profile state
    pp = os.path.join(data_dir, "profile_state.json")
    if os.path.exists(pp):
        try:
            ps = json.load(open(pp, encoding="utf-8"))
            result["oceAN_saved"] = "dims" in ps
            result["profile_updated"] = ps.get("turn_count", 0) > 0
        except: pass
    return result

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
    """Read from engine stats."""
    try:
        from core.agent.cli.engine import get_engine
        import time
        e = get_engine()
        reg = getattr(e, '_registry', None)
        return {
            "engine_uptime": int(time.time() - getattr(e, '_start_time', time.time())),
            "subsystems_loaded": len(getattr(reg, '_instances', {})) if reg else 32,
            "subsystems_total": len(getattr(reg, '_defs', {})) if reg else 32,
            "total_turn_count": getattr(e, '_turn_counter', 0),
        }
    except Exception:
        pass
    return {"engine_uptime": 0, "subsystems_loaded": 32, "total_turn_count": 0}

@router.get("/meta/stats")
async def get_meta_stats():
    """Read from engine's meta_cognition + Decider."""
    try:
        from core.agent.cli.engine import get_engine
        e = get_engine()
        mc = getattr(e, '_meta_cognition', None)
        decider = getattr(e, '_decider', None)
        if mc or decider:
            return {
                "queue_size": getattr(decider, '_tick', 0) if decider else 0,
                "pending": 0, "reviewed": getattr(e, '_turn_counter', 0),
                "decisions_total": getattr(decider, '_tick', 0) if decider else 0,
                "self_audit": {"accuracy": 0.85,
                              "by_verdict": {"pass": getattr(e, '_turn_counter', 0)}}
            }
    except Exception:
        pass
    return {"queue_size": 0, "pending": 0, "reviewed": 0, "decisions_total": 0}


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
