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
import time, logging, os, json
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
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


# ══════════ v6 Endpoints ══════


@app.get("/v6/profile")
async def v6_profile():
    """Get OCEAN 10-dimension profile + MBTI."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
    bfi = getattr(getattr(_engine, '_bfi_calibrator', None), '_bfi_history', [])
    return {
        "oceAN_dims": ocean.dims if ocean else {},
        "mbti": ocean.to_mbti() if ocean else "?",
        "turn_count": ocean.turn_count if ocean else 0,
        "top_dimensions": ocean.top_dimensions(5) if ocean else [],
        "bfi_history": len(bfi),
        "bfi_latest": bfi[-1]["bfi_scores"] if bfi else {},
    }


@app.get("/v6/trace")
async def v6_trace():
    """Get current trace signals."""
    if not _engine or not hasattr(_engine, '_trace_v3'):
        raise HTTPException(503, "Engine not started")
    m = _engine._trace_v3.meta_analyze()
    return {"reason_distribution": m.get("reason_distribution", {}),
            "avg_confidence": m.get("avg_confidence", 0), "total": m.get("total_transitions", 0)}


@app.get("/v6/abc")
async def v6_abc():
    """Get ABC layer stats."""
    if not _engine or not hasattr(_engine, '_abc'):
        raise HTTPException(503, "ABC not available")
    return _engine._abc.report()


@app.get("/v6/mind")
async def v6_mind():
    """Get Mind stats."""
    if not _engine or not hasattr(_engine, '_mind'):
        raise HTTPException(503, "Mind not available")
    return _engine._mind.stats()


@app.get("/v6/persistence")
async def v6_persistence():
    """Get persistence status."""
    store = getattr(_engine, '_annotation_store', None)
    unified = getattr(_engine, '_unified_store', None)
    return {
        "annotation_store": store.stats() if store else None,
        "unified_store": unified.stats() if unified else None,
        "oceAN_saved": os.path.exists("data/profile/ocean_profile.json"),
        "rules_saved": os.path.exists("data/neuro_symbolic_rules.json"),
    }


@app.get("/v6/sessions")
async def v6_sessions():
    """List sessions."""
    d = "data/monitor"
    if not os.path.exists(d):
        return []
    files = sorted([f for f in os.listdir(d) if f.startswith("chat_") and f.endswith(".jsonl")], reverse=True)
    return [{"name": f, "size": os.path.getsize(os.path.join(d, f))} for f in files[:20]]


@app.get("/v6/session/{filename}")
async def v6_session(filename: str):
    """Get session data."""
    path = os.path.join("data/monitor", filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Session not found")
    with open(path) as f:
        return [json.loads(line) for line in f]


# ══════════ v6 GUI Interaction Endpoints ══════════


# ── Graph visualization ──

@app.get("/v6/graph")
async def v6_graph():
    """Get InteractionGraph + SubgraphCompiler state for visualization."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    ig = getattr(_engine, '_interaction_graph', None)
    nodes = []
    edges = []
    if ig and hasattr(ig, '_edges'):
        edge_list = getattr(ig, '_edges', []) if isinstance(getattr(ig, '_edges', None), list) else list(getattr(ig, '_edges', {}).values())
        for e in edge_list[:50]:
            edges.append({
                "source": getattr(e, 'source', '?'),
                "target": getattr(e, 'target', '?'),
                "type": str(getattr(e, 'edge_type', '?')),
                "weight": getattr(e, 'weight', 0.5),
            })
        # Collect unique nodes
        node_set = set()
        for e in edges:
            node_set.add(e["source"])
            node_set.add(e["target"])
        for n in sorted(node_set):
            nodes.append({"id": n, "state": ig.get_node_state(n) if hasattr(ig, 'get_node_state') else {}})
    
    # SubgraphCompiler active subgraph
    subgraph_nodes = []
    if hasattr(_engine, '_world_objects') and _engine._world_objects:
        subgraph_nodes = list(_engine._world_objects.keys())[:20]
    
    return {"nodes": nodes, "edges": edges, "subgraph_nodes": subgraph_nodes}


# ── Discourse Tree visualization ──

@app.get("/v6/discourse-tree")
async def v6_discourse_tree():
    """Get DiscourseBlockTree for tree visualization."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    dt = getattr(_engine, '_discourse_tree', None)
    if not dt:
        return {"blocks": [], "branches": []}
    
    trees = getattr(dt, '_trees', {})
    blocks = []
    for tree_id, tree in trees.items():
        block_list = getattr(tree, 'blocks', {})
        for bid, block in block_list.items():
            blocks.append({
                "id": str(bid),
                "tree_id": tree_id,
                "topic": getattr(block, 'topic', '')[:100],
                "temperature": getattr(block, 'temperature', 'warm'),
                "edus": len(getattr(block, 'edus', [])),
                "children": [str(c) for c in getattr(block, 'children', [])],
                "parent": str(getattr(block, 'parent', '')) if getattr(block, 'parent', None) else None,
            })
    
    return {"blocks": blocks, "total": len(blocks)}


# ── Semantic Object graph ──

@app.get("/v6/objects")
async def v6_objects():
    """Get SemanticObject graph for concept visualization."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    objects = getattr(_engine, '_world_objects', {})
    nodes = []
    edges = []
    for name, obj in list(objects.items())[:100]:
        nodes.append({
            "id": name,
            "lifespan": str(getattr(obj, 'lifespan', '?')) if hasattr(obj, 'lifespan') else 'stable',
            "relations": list(getattr(obj, 'relations', {}).keys())[:5] if hasattr(obj, 'relations') else [],
        })
        # Extract edges from object relations
        rels = getattr(obj, 'relations', {})
        for rel_type, targets in (rels.items() if isinstance(rels, dict) else []):
            target_list = targets if isinstance(targets, list) else [targets]
            for target in target_list[:3]:
                edges.append({"source": name, "target": str(target), "type": str(rel_type)})
    
    return {"nodes": nodes[:50], "edges": edges[:100], "total_objects": len(objects)}


# ── Profile editing (user correction → feedback) ──

class ProfileEditRequest(BaseModel):
    dim: str = ""
    value: float = 0.5
    mbti: str = ""


@app.put("/v6/profile")
async def v6_profile_edit(req: ProfileEditRequest):
    """Edit OCEAN profile. User corrections feed back to Mind + ABC rules."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    result = {"updated": [], "feedback": []}
    ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
    
    # Update OCEAN dimension
    if req.dim and ocean:
        dims = getattr(ocean, 'dims', {})
        if req.dim in dims:
            old = dims[req.dim]
            dims[req.dim] = req.value
            result["updated"].append(f"{req.dim}: {old:.2f} → {req.value:.2f}")
    
    # Update MBTI → feed back to ABC rules
    if req.mbti and hasattr(_engine, '_abc') and _engine._abc:
        try:
            from core.agent.v4.cognitive.neuro_symbolic import Rule
            # Create correction rule from user feedback
            _engine._abc._rule_engine.register(Rule(
                name=f"user_correction_mbti",
                premise={"profile_tags": {"contains": "personality"}},
                conclusion={"mbti": req.mbti, "action": "user_override"},
                source="user_feedback",
                confidence=0.9,
            ))
            _engine._abc._rule_engine.save()
            result["feedback"].append(f"Rule: MBTI→{req.mbti} (conf=0.9)")
        except Exception as e:
            result["feedback"].append(f"Rule save failed: {e}")
    
    return result


# ── Response feedback (user marks correct/wrong) ──

class FeedbackRequest(BaseModel):
    turn: int = 0
    correct: bool = True
    rule_name: str = ""


@app.post("/v6/feedback")
async def v6_feedback(req: FeedbackRequest):
    """User feedback on response quality → updates ABC rule confidence."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    result = {"updated": False}
    
    # Update ABC rule confidence
    if req.rule_name and hasattr(_engine, '_abc') and _engine._abc:
        try:
            _engine._abc.learn_from_feedback(req.rule_name, req.correct)
            result["updated"] = True
            result["rule"] = req.rule_name
            result["hit"] = req.correct
        except Exception as e:
            result["error"] = str(e)
    
    # Record correction in Mind
    if hasattr(_engine, '_mind') and _engine._mind and not req.correct:
        try:
            if hasattr(_engine._mind, 'mistakes') and _engine._mind.mistakes:
                _engine._mind.mistakes.record(f"turn_{req.turn}", "user_correction")
            result["mind_updated"] = True
        except Exception:
            pass
    
    return result


# ── Rule management ──

@app.get("/v6/rules")
async def v6_rules():
    """List all neuro-symbolic rules (view/edit)."""
    if not _engine or not hasattr(_engine, '_abc'):
        raise HTTPException(503, "ABC not available")
    reng = getattr(getattr(_engine, '_abc', None), '_rule_engine', None)
    if not reng:
        return {"rules": []}
    rules = []
    for name, rule in reng._rules.items():
        rules.append({
            "name": name,
            "premise": rule.premise,
            "conclusion": rule.conclusion,
            "confidence": rule.confidence,
            "hits": rule.hits,
            "misses": rule.misses,
            "source": rule.source,
        })
    return {"rules": rules, "total": len(rules)}


class RuleEditRequest(BaseModel):
    name: str
    conclusion: dict = {}
    confidence: float = 0.5


@app.put("/v6/rules")
async def v6_rules_edit(req: RuleEditRequest):
    """Edit a neuro-symbolic rule."""
    if not _engine or not hasattr(_engine, '_abc'):
        raise HTTPException(503, "ABC not available")
    reng = getattr(getattr(_engine, '_abc', None), '_rule_engine', None)
    if not reng or req.name not in reng._rules:
        raise HTTPException(404, f"Rule '{req.name}' not found")
    
    rule = reng._rules[req.name]
    if req.conclusion:
        rule.conclusion.update(req.conclusion)
    rule.confidence = req.confidence
    reng.save()
    return {"updated": req.name, "conclusion": rule.conclusion, "confidence": rule.confidence}


# ══════════ v6 Deep Graph/Chain APIs ══════════


# ── Relation Substrate (typed concept edges) ──

@app.get("/v6/relations")
async def v6_relations(source: str = "", target: str = ""):
    """Get typed relations between concepts."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    rs = None
    if hasattr(_engine, '_world_provider') and _engine._world_provider:
        rs = getattr(_engine._world_provider, 'relation_substrate', None)
    
    if not rs:
        return {"edges": [], "total": 0}
    
    edges = rs.query(source=source or None, target=target or None)
    result = []
    for e in edges[:200]:
        result.append({
            "source": getattr(e, 'source', '?'),
            "target": getattr(e, 'target', '?'),
            "kind": str(getattr(e, 'relation_kind', '?')),
            "strength": getattr(e, 'semantic_strength', 0.5),
            "evidence": str(getattr(e, 'evidence', ''))[:100],
        })
    return {"edges": result, "total": len(edges)}


# ── Causal chains ──

@app.get("/v6/causal")
async def v6_causal():
    """Get causal dependency chains."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    # Try causal substrate adapter
    cs = getattr(_engine, '_causal_substrate_adapter', None)
    chains = []
    
    if cs and hasattr(cs, 'get_chains'):
        chains = cs.get_chains()
    elif hasattr(_engine, '_world_provider') and _engine._world_provider:
        # Try causal_substrate directly
        causal = getattr(_engine._world_provider, 'causal_substrate', None)
        if causal and hasattr(causal, 'edges'):
            for k, v in list(getattr(causal, 'edges', {}).items())[:50]:
                chains.append({
                    "key": str(k),
                    "weight": getattr(v, 'weight', 0.5) if hasattr(v, 'weight') else 0.5,
                })
    
    return {"chains": chains[:50], "total": len(chains)}


# ── Behavior graph ──

@app.get("/v6/behavior")
async def v6_behavior():
    """Get behavior graph edges and statistics."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    bg = getattr(_engine, '_behavior_graph_adapter', None)
    if not bg:
        return {"edges": [], "nodes": 0, "stats": {}}
    
    edges = []
    g = getattr(bg, 'graph', None) if hasattr(bg, 'graph') else bg
    if hasattr(g, '_graph'):
        g = g._graph
    
    if hasattr(g, 'edges'):
        for e in list(getattr(g, 'edges', []))[:100]:
            edges.append({
                "source": str(getattr(e, 'source', '?')),
                "target": str(getattr(e, 'target', '?')),
                "type": str(getattr(e, 'edge_type', 'behavioral')),
                "weight": getattr(e, 'weight', 0.5),
            })
    
    return {
        "edges": edges,
        "nodes": bg.node_count() if hasattr(bg, 'node_count') else 0,
        "stats": getattr(bg, 'stats', lambda: {})(),
    }


# ── Engineering knowledge graph ──

@app.get("/v6/engineering")
async def v6_engineering():
    """Get engineering chain knowledge graph (constraints, patterns)."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    ek = getattr(_engine, '_engineering_knowledge', None)
    if not ek:
        return {"nodes": [], "constraints": [], "patterns": []}
    
    nodes = []
    if hasattr(ek, 'get_by_type'):
        for ktype_name in ['constraint', 'pattern', 'architecture']:
            try:
                from core.agent.v3_2.engineering_chain.models import KnowledgeType
                kt = getattr(KnowledgeType, ktype_name.upper(), None)
                if kt:
                    for n in ek.get_by_type(kt)[:20]:
                        nodes.append({"name": getattr(n, 'name', '?'), "type": ktype_name})
            except Exception:
                pass
    
    constraints = [n for n in nodes if n['type'] == 'constraint']
    patterns = [n for n in nodes if n['type'] == 'pattern']
    
    return {"nodes": nodes, "constraints": constraints, "patterns": patterns}


# ── Mind space (full introspection) ──

@app.get("/v6/mind/full")
async def v6_mind_full():
    """Full Mind introspection — all components with history."""
    if not _engine or not hasattr(_engine, '_mind'):
        raise HTTPException(503, "Mind not available")
    
    mind = _engine._mind
    result = {"stats": mind.stats()}
    
    # Relations
    if hasattr(mind, 'relations') and mind.relations:
        rels = getattr(mind.relations, '_relations', {})
        result["relations"] = {str(k): {"confidence": getattr(v, 'confidence', 0.5)} 
                               for k, v in list(rels.items())[:20]}
    
    # Attention anchors
    if hasattr(mind, 'attention') and mind.attention:
        anchors = getattr(mind.attention, '_anchors', {})
        result["anchors"] = {str(k): {"weight": getattr(v, 'weight', 0.5)}
                            for k, v in list(anchors.items())[:20]}
    
    # Mistakes
    if hasattr(mind, 'mistakes') and mind.mistakes:
        errs = getattr(mind.mistakes, '_errors', [])
        result["mistakes"] = [str(e)[:100] for e in errs[-10:]]
    
    return result


# ── Mode router (switch state) ──

@app.get("/v6/router")
async def v6_router():
    """Get mode router state — which processing path is active."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    router = getattr(_engine, '_mode_router', None)
    if not router:
        return {"active_mode": "unknown", "stats": {}}
    
    return {
        "active_mode": str(getattr(router, 'active_mode', 'unknown')),
        "stats": router.get_stats() if hasattr(router, 'get_stats') else {},
    }


# ── Persisted graphs ──

@app.get("/v6/persistence/graphs")
async def v6_persistence_graphs():
    """List all persisted graph data."""
    paths = {
        "mind_relations": "data/mind_relation.json",
        "mind_attention": "data/mind_attention.json",
        "mind_mistakes": "data/mind_mistakes.json",
        "neuro_symbolic_rules": "data/neuro_symbolic_rules.json",
        "ocean_profile": "data/profile/ocean_profile.json",
        "pattern_learner": "data/pattern_learner.json",
    }
    result = {}
    for name, path in paths.items():
        if os.path.exists(path):
            size = os.path.getsize(path)
            result[name] = {"size": size, "exists": True}
        else:
            result[name] = {"exists": False}
    return result


# ══════════ WebSocket — Real-time streaming ══════════

@app.websocket("/v4/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming.

    Messages from client:
        { "type": "message", "payload": { "content": "..." } }
    Messages to client:
        { "event_type": "MESSAGE", "payload": { "content": "..." }, "server_timestamp": ... }
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "message":
                content = payload.get("content", "")
                if content and _engine and _event_log:
                    event_id = f"ws_{int(time.time() * 1000)}"
                    # Persist
                    _event_log.put_event(
                        event_id=event_id,
                        kind="dialog.message",
                        payload={"text": content},
                        trace_id="",
                    )
                    # Process through engine
                    event_ir = EventIR(
                        id=event_id,
                        kind="dialog.message",
                        payload={"text": content},
                    )
                    response_text = _engine.on_event(event_ir)
                    _event_log.ack_event(event_id)
                    # Send response back
                    await websocket.send_json({
                        "event_type": "MESSAGE",
                        "payload": {
                            "content": response_text,
                            "event_id": event_id,
                        },
                        "server_timestamp": int(time.time() * 1000),
                    })
            elif msg_type == "ping":
                await websocket.send_json({
                    "event_type": "HEARTBEAT",
                    "payload": {"echo": "pong"},
                    "server_timestamp": int(time.time() * 1000),
                })
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


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
