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
from fastapi.middleware.cors import CORSMiddleware
from core.agent.v4.monitor.interaction_monitor import interaction_middleware, get_interaction_monitor
from core.agent.v4.monitor.span_tracer import get_tracer
from pydantic import BaseModel, field_validator, Field
import uvicorn

from core.agent.v4.event_ir import EventIR
from core.agent.v4.api_event_log import EventLog

# ══════════ P0 Security: Input validation + Auth + Key masking ══════════

# API key mask for logging
import re

class APIKeyMaskFilter(logging.Filter):
    """Redact API keys from log messages."""
    _PATTERNS = [
        (re.compile(r'(api_key["\s:=]+)([a-zA-Z0-9_-]{20,})', re.I), r'\1[REDACTED]'),
        (re.compile(r'(Bearer\s+)([a-zA-Z0-9_-]{20,})'), r'\1[REDACTED]'),
        (re.compile(r'(sk-[a-zA-Z0-9]{20,})'), r'[REDACTED_KEY]'),
    ]
    def filter(self, record):
        msg = record.getMessage()
        for pat, repl in self._PATTERNS:
            msg = pat.sub(repl, msg)
        record.msg = msg
        return True

logging.getLogger().addFilter(APIKeyMaskFilter())

# Bearer token auth — P0 minimum viable
import os as _os
AUTH_TOKEN = _os.environ.get("DM_AUTH_TOKEN", "dev-token")
ADMIN_TOKEN = _os.environ.get("DM_ADMIN_TOKEN", "admin-token")

def require_auth(request):
    """Minimal Bearer token check."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return False
    token = auth[7:]
    return token in (AUTH_TOKEN, ADMIN_TOKEN)

def require_admin(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return False
    return auth[7:] == ADMIN_TOKEN

# Text size limits
MAX_EVENT_TEXT = 10_000   # 10KB per event
MAX_INSPECT_DEPTH = 3
MAX_SESSION_RESULTS = 100

# Input sanitizer
def sanitize_path(path: str) -> str:
    """Reject path traversal attempts."""
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid path: .. not allowed")
    return path.replace("\\", "/").strip()
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.v4.api_gateway import router as gateway_router, init as gateway_init
from core.agent.v4.api_viz_edit import router as viz_edit_router, init as viz_edit_init
from core.agent.v4.api_annotate import router as annotate_router, init as annotate_init

logger = logging.getLogger(__name__)

# ---- Global state ----
from fastapi import Request
from fastapi.responses import JSONResponse

app = FastAPI(title="DialogMesh v6 API", version="1.0")

# CORS: allow frontend (:4173) to call API (:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Interaction monitor middleware — captures every FE↔API call
@app.middleware("http")
async def interaction_logger(request: Request, call_next):
    return await interaction_middleware(request, call_next)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """P0: Bearer token check. OPTIONS (CORS preflight) always passes."""
    if request.method == "OPTIONS":
        return await call_next(request)
    public_paths = ("/v4/health", "/docs", "/openapi.json", "/v4/ws", "/v3/health",
                     "/v6/monitor", "/v6/monitor/")
    if any(request.url.path.startswith(p) for p in public_paths):
        return await call_next(request)
    if not require_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

_engine: Optional[CognitiveRuntimeEngine] = None
_event_log: Optional[EventLog] = None

# Register gateway router
app.include_router(gateway_router)
# Register visualization edit router
app.include_router(viz_edit_router)
# Register annotation router
app.include_router(annotate_router)


# ---- Models (with P0 validators) ----

class EventRequest(BaseModel):
    event_id: str = Field(max_length=128)
    kind: str = Field(default="dialog.message", max_length=64)
    payload: dict = Field(default={}, max_length=MAX_EVENT_TEXT)
    trace_id: str = Field(default="", max_length=64)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v):
        import json
        size = len(json.dumps(v, ensure_ascii=False))
        if size > MAX_EVENT_TEXT:
            raise ValueError(f"Payload too large: {size} > {MAX_EVENT_TEXT}")
        return v


class IngestRequest(BaseModel):
    source_path: str = Field(max_length=512)
    content: str = Field(default="", max_length=100_000)
    file_type: str = Field(default="markdown", max_length=32)

    @field_validator("source_path")
    @classmethod
    def sanitize_source(cls, v):
        return sanitize_path(v)


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

    # Initialize gateway (provider management)
    gateway_init(_engine)
    # Auto-configure LLM provider via switch gateway
    try:
        from core.agent.llm_providers.openai_provider import OpenAIProvider
        _engine._llm_provider = OpenAIProvider("deepseek", {
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "not-needed",  # gateway handles auth
            "model": "deepseek-v4-flash",
        })
        logger.info("LLM provider: switch gateway (deepseek)")
    except Exception as e:
        logger.warning("LLM provider init failed: %s", e)

    # Initialize visualization edit (白盒化)
    viz_edit_init(_engine)
    # Initialize annotation system
    annotate_init(_engine)

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
@app.get("/v3/health")
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
    dimension: str = Field(max_length=8)     # C, NC, MS, CL, etc.
    value: float = Field(ge=0.0, le=1.0)     # OCEAN ranges
    reason: str = Field(default="", max_length=200)


@app.put("/v6/profile")
async def v6_profile_edit(req: ProfileEditRequest):
    """Edit OCEAN profile. All corrections journaled → drift detection."""
    if not _engine:
        raise HTTPException(503, "Engine not started")

    result = {"updated": [], "journal": [], "drift_alert": None}
    ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
    journal = getattr(_engine, '_correction_journal', None)

    # Update OCEAN dimension
    if req.dimension and ocean:
        dims = getattr(ocean, 'dims', {})
        if req.dimension in dims:
            old = dims[req.dimension]
            dims[req.dimension] = req.value
            result["updated"].append(f"{req.dimension}: {old:.2f} → {req.value:.2f}")
            # Journal the correction
            if journal:
                journal.record(req.dimension, old, req.value, reason="user_edit", turn=getattr(_engine, '_turn_counter', 0))
                result["journal"].append(req.dimension)

    # Update MBTI → feed back to ABC rules + journal
    if req.mbti and ocean:
        old_mbti = ocean.to_mbti()
        if old_mbti != req.mbti and journal:
            journal.record("mbti", old_mbti, req.mbti, reason="user_edit", turn=getattr(_engine, '_turn_counter', 0))
            result["journal"].append("mbti")

        if hasattr(_engine, '_abc') and _engine._abc:
            from core.agent.v4.cognitive.neuro_symbolic import Rule
            _engine._abc._rule_engine.register(Rule(
                name="user_correction_mbti",
                premise={"profile_tags": {"contains": "personality"}},
                conclusion={"mbti": req.mbti, "action": "user_override"},
                source="user_feedback", confidence=0.9,
            ))
            _engine._abc._rule_engine.save()
            result["updated"].append(f"MBTI rule: →{req.mbti} (conf=0.9)")

    # Check for drift
    if journal and ocean:
        drifts = []
        for dim, val in ocean.dims.items():
            d = journal.check_drift(dim, val)
            if d: drifts.append(d)
        if drifts:
            result["drift_alert"] = {"affected": len(drifts), "details": drifts}

    return result
    return result


    return result


# ── Correction journal ──

@app.get("/v6/profile/corrections")
async def v6_profile_corrections():
    """Get correction journal — all user edits with before/after/drift."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    journal = getattr(_engine, '_correction_journal', None)
    if not journal:
        return {"entries": [], "total": 0}
    entries = [{"ts": e.timestamp, "dim": e.dimension, "before": str(e.before),
                "after": str(e.after), "turn": e.turn, "reason": e.reason}
               for e in journal._entries[-50:]]
    return {"entries": entries, "total": len(journal._entries), "stats": journal.stats()}


@app.post("/v6/profile/corrections/review")
async def v6_profile_corrections_review():
    """Trigger LLM retrospective review of latest corrections and drift."""
    if not _engine or not _engine._llm_provider: raise HTTPException(503)
    journal = getattr(_engine, '_correction_journal', None)
    if not journal or not journal._entries: return {"reviewed": False}
    ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
    drifts = []
    if ocean:
        for dim, val in ocean.dims.items():
            d = journal.check_drift(dim, val)
            if d: drifts.append(d)
    recent = [getattr(e, 'text', '') for e in getattr(_engine, '_event_buffer', [])[-5:]]
    prompt = journal.build_retrospective_prompt(drifts, recent)
    try:
        from core.agent.llm_providers.base import GenerateRequest
        req = GenerateRequest(prompt=prompt, max_tokens=300, temperature=0.3)
        result = _engine._llm_provider.generate(req)
        text = result.text if hasattr(result, 'text') else str(result)
        return {"reviewed": True, "drifts": len(drifts), "verdict": text[:500]}
    except Exception as e:
        return {"reviewed": False, "error": str(e)[:200]}


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


# ══════════ v6 Business Logic APIs ══════════


# ── Pipeline (tier stats, pass rates) ──

@app.get("/v6/pipeline")
async def v6_pipeline():
    """Get processing pipeline tier statistics."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    tiers = {}
    # Check extraction orchestrator
    if hasattr(_engine, '_extraction_orchestrator') and _engine._extraction_orchestrator:
        eo = _engine._extraction_orchestrator
        for name in ['regex', 'jieba', 'stanza', 'lmstudio', 'deepseek']:
            provider = getattr(eo, f'_{name}', None)
            if provider:
                tiers[name] = {"available": provider.available() if hasattr(provider, 'available') else True}
    
    # Tiered pipeline
    pipeline = getattr(_engine, '_tiered_pipeline', None)
    if pipeline and hasattr(pipeline, 'tiers'):
        for t in pipeline.tiers:
            tiers[t.name] = {
                "level": t.level,
                "pass_rate": t.stats.pass_rate() if hasattr(t, 'stats') else 0,
                "correction_rate": getattr(t.stats, 'correction_count', 0),
                "avg_latency_ms": t.stats.avg_latency_ms() if hasattr(t, 'stats') else 0,
            }
    
    return {"tiers": tiers, "total": len(tiers)}


# ── Extraction (blueprint results) ──

@app.get("/v6/extraction")
async def v6_extraction():
    """Get extraction blueprint status and last results."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    eo = getattr(_engine, '_extraction_orchestrator', None)
    if not eo:
        return {"providers": [], "last_result": None}
    
    providers = []
    for name in ['regex', 'jieba', 'stanza', 'lmstudio', 'deepseek']:
        p = getattr(eo, f'_{name}', None)
        if p:
            providers.append({
                "name": name,
                "available": p.available() if hasattr(p, 'available') else True,
                "type": str(type(p).__name__),
            })
    
    last = getattr(eo, '_last_result', None)
    last_data = None
    if last:
        last_data = {
            "definitions": len(getattr(last, 'definitions', [])),
            "relations": len(getattr(last, 'relations', [])),
            "concepts": getattr(last, 'concepts', [])[:10],
        }
    
    return {"providers": providers, "tier_chain": providers, "last_result": last_data}


# ── Perspectives (horizon, active view) ──

@app.get("/v6/perspectives")
async def v6_perspectives():
    """Get perspective planner state — horizons, active views."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    pp = getattr(_engine, '_perspective_planner', None)
    vm = getattr(_engine, '_view_manager', None)
    
    result = {"perspectives": [], "active_view": None}
    
    if pp:
        if hasattr(pp, 'perspectives'):
            for p in pp.perspectives[:10]:
                result["perspectives"].append({
                    "name": str(getattr(p, 'name', '?')),
                    "horizon": str(getattr(p, 'horizon', '?')),
                    "targets": getattr(p, 'targets', [])[:5],
                })
    
    if vm and hasattr(vm, 'current_view'):
        v = vm.current_view()
        if v:
            result["active_view"] = {
                "depth": getattr(v, 'depth', 2),
                "visible": getattr(v, 'visible', [])[:10],
            }
    
    return result


# ── Parameters (tunable config) ──

@app.get("/v6/parameters")
async def v6_parameters(prefix: str = ""):
    """Get all tunable parameters."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    pr = getattr(_engine, '_parameter_registry', None)
    if not pr:
        return {"params": {}, "total": 0}
    
    params = pr.all(prefix=prefix or "")
    return {"params": params, "total": len(params)}


class ParamEditRequest(BaseModel):
    key: str
    value: str = ""


@app.put("/v6/parameters")
async def v6_parameters_edit(req: ParamEditRequest):
    """Edit a parameter value."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    pr = getattr(_engine, '_parameter_registry', None)
    if not pr:
        raise HTTPException(404, "Parameter registry not found")
    
    old = pr.get(req.key)
    pr.set(req.key, req.value)
    return {"key": req.key, "old": str(old), "new": req.value, "updated": True}


# ── Switch/Router (full) ──

@app.get("/v6/router/modes")
async def v6_router_modes():
    """Get all routing modes with complexity ranges, stats, and current state."""
    if not _engine:
        raise HTTPException(503, "Engine not started")

    router = getattr(_engine, '_mode_router', None)
    if not router:
        return {"available": False, "modes": []}

    # Mode definitions with complexity ranges
    modes = [
        {"name": "rule", "complexity": "0-3", "cost": "free", "latency": "<1ms",
         "desc": "纯规则引擎,本地计算,零API成本"},
        {"name": "small_model", "complexity": "4-7", "cost": "free", "latency": "~20-100ms",
         "desc": "本地小模型(LMStudio),零API成本"},
        {"name": "remote_llm", "complexity": "8-10", "cost": "API", "latency": "~200ms-2s",
         "desc": "远程大模型(DeepSeek),按量计费"},
    ]

    return {
        "available": True,
        "modes": modes,
        "active": str(getattr(router, '_active', getattr(router, 'force_mode', None) or 'remote_llm')),
        "force_mode": getattr(router, 'force_mode', None),
        "disabled": {
            "remote": getattr(router, 'disable_remote', False),
            "small_model": getattr(router, 'disable_small_model', False),
        },
        "cost_budget": getattr(router, 'cost_budget', 'standard'),
        "route_stats": getattr(router, '_route_stats', {}),
        "complexity": {
            "evaluator_available": getattr(router, 'evaluator', None) is not None,
            "last_score": getattr(getattr(router, 'evaluator', None), '_last_score', None),
        },
        "degradation_chain": ["remote_llm → small_model → rule (自动降级)"],
    }


class ModeOverrideRequest(BaseModel):
    mode: str = ""
    disable_remote: bool = False
    disable_small_model: bool = False
    cost_budget: str = ""


@app.put("/v6/router/modes")
async def v6_router_override(req: ModeOverrideRequest):
    """Force mode, toggle model availability, or set budget."""
    if not _engine:
        raise HTTPException(503, "Engine not started")

    router = getattr(_engine, '_mode_router', None)
    if not router:
        raise HTTPException(404, "Router not found")

    result = {"updated": []}

    if req.mode and req.mode in ["rule", "small_model", "remote_llm"]:
        router.force_mode = req.mode
        result["updated"].append(f"mode={req.mode}")

    if req.disable_remote:
        router.disable_remote = True
        result["updated"].append("remote_disabled")

    if req.disable_small_model:
        router.disable_small_model = True
        result["updated"].append("small_model_disabled")

    if req.cost_budget in ["free", "standard", "premium"]:
        router.cost_budget = req.cost_budget
        result["updated"].append(f"budget={req.cost_budget}")

    result["count"] = len(result["updated"])
    return result


# ── Context (last assembled) ──

@app.get("/v6/context")
async def v6_context():
    """Get last assembled context — domain allocation, entry counts."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    
    lc = getattr(_engine, '_last_context', None)
    if not lc:
        return {"entries": {}, "domains": {}}
    
    entries = {}
    if hasattr(lc, '_entries'):
        for k, v in lc._entries.items():
            entries[str(k)] = {
                "domain": getattr(v, 'domain', '?'),
                "type": getattr(v, 'type', '?'),
                "confidence": getattr(v, 'confidence', 0),
            }
    
    domains = {}
    if hasattr(lc, '_domain_allocation'):
        domains = dict(lc._domain_allocation)
    
    return {"entries": entries, "domains": domains, "total_entries": len(entries)}



# ══════════ v6 Provider & Operations APIs ══════════


@app.get("/v6/providers")
async def v6_providers():
    """List all LLM providers with status, model, health, failover chain."""
    if not _engine:
        raise HTTPException(503, "Engine not started")
    result = {"active": {}, "failover": {}, "available": []}
    prov = getattr(_engine, '_llm_provider', None)
    if prov:
        cfg = getattr(prov, '_config', {}) if hasattr(prov, '_config') else {}
        result["active"] = {
            "name": getattr(prov, 'name', '?'),
            "type": type(prov).__name__,
            "model": cfg.get('model', '?'),
            "base_url": cfg.get('base_url', '?'),
            "healthy": prov.health_check() if hasattr(prov, 'health_check') else None,
            "stats": prov.get_recent_stats(10) if hasattr(prov, 'get_recent_stats') else {},
        }
    fo = getattr(_engine, '_failover_provider', None)
    if fo:
        result["failover"] = {
            "primary": getattr(fo._primary, 'name', '?') if hasattr(fo, '_primary') else None,
            "fallback": getattr(fo._fallback, 'name', '?') if hasattr(fo, '_fallback') else None,
            "active_idx": getattr(fo, '_active_idx', 0),
            "failures": getattr(fo, '_failure_count', 0),
        }
    return result


class ProviderSwitch(BaseModel):
    provider: str = "deepseek"
    model: str = ""
    api_key: str = ""
    base_url: str = ""


@app.put("/v6/providers")
async def v6_providers_switch(req: ProviderSwitch):
    """Switch provider/model/key at runtime."""
    if not _engine: raise HTTPException(503)
    try:
        from core.agent.llm_providers.openai_provider import OpenAIProvider
        old_cfg = getattr(getattr(_engine, '_llm_provider', None), '_config', {}) if _engine._llm_provider else {}
        new = OpenAIProvider(req.provider, {
            "api_key": req.api_key or old_cfg.get('api_key', ''),
            "base_url": req.base_url or old_cfg.get('base_url', ''),
            "model": req.model or old_cfg.get('model', 'deepseek-chat'),
        })
        _engine._llm_provider = new
        return {"switched": req.provider, "model": req.model or 'unchanged',
                "healthy": new.health_check() if hasattr(new, 'health_check') else None}
    except Exception as e:
        return {"error": str(e)}


@app.get("/v6/providers/tokens")
async def v6_providers_tokens():
    """Token usage: current session + all sessions estimate."""
    d = "data/monitor"
    files = sorted([f for f in os.listdir(d) if f.startswith("chat_") and f.endswith(".jsonl")], reverse=True) if os.path.exists(d) else []
    cur = {"turns": 0, "chars": 0, "est_tokens": 0}
    if files:
        with open(os.path.join(d, files[0])) as f:
            rows = [json.loads(l) for l in f]
        cur["turns"] = len(rows)
        cur["chars"] = sum(r.get("response_len", 0) for r in rows)
        cur["est_tokens"] = int(cur["chars"] * 3.5)
    total = 0
    for cf in files[:50]:
        try:
            with open(os.path.join(d, cf)) as f:
                total += sum(json.loads(l).get("response_len", 0) for l in f)
        except: pass
    return {"current": cur, "all_sessions": {"count": len(files), "est_tokens": int(total * 3.5)},
            "rate": {"deepseek": "$0.14/M in, $0.28/M out"}}


class ContextTune(BaseModel):
    token_budget: int = 0
    domain_P: float = 0
    domain_C: float = 0
    domain_K: float = 0


@app.put("/v6/context/config")
async def v6_context_tune(req: ContextTune):
    """Adjust context budget and domain weights."""
    if not _engine: raise HTTPException(503)
    updated = []
    if req.token_budget > 0 and hasattr(_engine, '_world_params'):
        _engine._world_params.compiler_token_budget = req.token_budget
        updated.append(f"budget={req.token_budget}")
    lc = getattr(_engine, '_last_context', None)
    if lc and hasattr(lc, '_domain_allocation'):
        for d, v in [("P", req.domain_P), ("C", req.domain_C), ("K", req.domain_K)]:
            if v > 0:
                lc._domain_allocation[d] = v; updated.append(f"{d}={v:.2f}")
    return {"updated": updated, "count": len(updated)}


@app.get("/v6/metrics")
async def v6_metrics():
    """System metrics: uptime, LLM stats, turn count."""
    if not _engine: raise HTTPException(503)
    prov = getattr(_engine, '_llm_provider', None)
    stats = prov.get_recent_stats(50) if prov and hasattr(prov, 'get_recent_stats') else {}
    return {"uptime_s": time.time() - getattr(_engine, '_start_time', time.time()),
            "turns": getattr(_engine, '_turn_counter', 0),
            "llm_latency_ms": stats.get("avg_latency_ms", 0),
            "llm_error_rate": stats.get("error_rate", 0)}


@app.post("/v6/providers/test")
async def v6_providers_test():
    """Quick connectivity test for active provider."""
    if not _engine or not _engine._llm_provider: raise HTTPException(503)
    p = _engine._llm_provider
    try:
        h = p.health_check() if hasattr(p, 'health_check') else None
        l = p.estimate_latency_ms(50, 20) if hasattr(p, 'estimate_latency_ms') else 0
        return {"healthy": h, "latency_50tok_ms": l, "provider": p.name}
    except Exception as e:
        return {"healthy": False, "error": str(e)[:200]}


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



# ══════════ v6 Meta-Cognition + Version Control APIs ══════════

@app.get("/v6/meta/stats")
async def v6_meta_stats():
    """Meta-cognition status: queue, decisions, accuracy."""
    if not _engine or not hasattr(_engine, '_meta'): raise HTTPException(503)
    return _engine._meta.stats()

@app.get("/v6/meta/queue")
async def v6_meta_queue():
    """Pending review queue."""
    if not _engine or not hasattr(_engine, '_meta'): raise HTTPException(503)
    items = [{"id": i.item_id, "source": i.source, "target": i.target,
              "priority": i.priority.name, "verdict": i.verdict}
             for i in _engine._meta._queue[-20:]]
    return {"queue": items, "pending": sum(1 for i in _engine._meta._queue if i.verdict is None)}

@app.post("/v6/meta/scan")
async def v6_meta_scan():
    """Trigger active scan."""
    if not _engine or not hasattr(_engine, '_meta'): raise HTTPException(503)
    items = _engine._meta.scan(_engine)
    _engine._meta.process_queue(max_items=3)
    return {"scanned": len(items), "status": "complete"}

@app.get("/v6/versions/{category}")
async def v6_versions(category: str, target: str = ""):
    """Git version history for a data category."""
    if not _engine or not hasattr(_engine, '_vcs'): raise HTTPException(503)
    store = _engine._vcs.store(category)
    if target:
        commits = store.history(target, 20)
        return {"target": target, "commits": [{"id": c.commit_id, "ts": c.timestamp,
                "author": c.author, "before": c.before, "after": c.after,
                "reason": c.reason, "verify": c.verification} for c in commits]}
    return {"categories": list(_engine._vcs._stores.keys()), "stats": _engine._vcs.stats()}

@app.post("/v6/versions/{category}/rollback")
async def v6_versions_rollback(category: str, target: str = "", commit_id: str = ""):
    """Rollback a target to a previous version."""
    if not _engine or not hasattr(_engine, '_vcs'): raise HTTPException(503)
    store = _engine._vcs.store(category)
    c = store.rollback_to(target, commit_id)
    if c: return {"rollback": target, "to": c.after, "commit": c.commit_id}
    raise HTTPException(404, "Commit not found")

@app.get("/v6/inertia")
async def v6_inertia():
    """Inertia weight graph status."""
    if not _engine or not hasattr(_engine, '_inertia'): raise HTTPException(503)
    return _engine._inertia.stats()

@app.post("/v6/ocean/params")
async def v6_ocean_params_apply():
    """Apply OCEAN→parameter auto-mapping."""
    if not _engine: raise HTTPException(503)
    ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
    pr = getattr(_engine, '_parameter_registry', None)
    if not ocean or not pr: raise HTTPException(404)
    updates = {}
    dims = ocean.dims
    if dims.get("C", 0.5) > 0.7:
        old = int(pr.get("behavior.min_repeat_count", 3))
        pr.set("behavior.min_repeat_count", str(max(1, old - 1)))
        updates["behavior.min_repeat_count"] = f"{old}→{max(1, old - 1)}"
    if dims.get("NC", 0.5) > 0.7:
        old = float(pr.get("behavior.min_confidence", 0.75))
        pr.set("behavior.min_confidence", str(round(old + 0.05, 2)))
        updates["behavior.min_confidence"] = f"{old}→{round(old + 0.05, 2)}"
    if dims.get("A", 0.5) < 0.4:
        old = int(pr.get("behavior.auto_accept_timeout", 10))
        pr.set("behavior.auto_accept_timeout", str(old + 5))
        updates["behavior.auto_accept_timeout"] = f"{old}→{old + 5}"
    return {"applied": updates, "ocean": {k: round(v,2) for k,v in dims.items() if k in "CNCA"}}

@app.get("/v6/behavior/patterns")
async def v6_behavior_patterns():
    """Discovered behavior patterns."""
    if not _engine or not hasattr(_engine, '_behavior_discovery'): raise HTTPException(503)
    bd = _engine._behavior_discovery
    return {"patterns": [{"trigger": p.trigger, "predicted": p.predicted,
            "confidence": round(p.confidence, 2), "support": p.support,
            "reviewed": p.reviewed, "verdict": p.review_verdict}
            for p in bd._patterns.values()], "stats": bd.stats()}

class BehaviorFeedback(BaseModel):
    pattern: str = ""
    accepted: bool = True

@app.post("/v6/behavior/feedback")
async def v6_behavior_feedback(req: BehaviorFeedback):
    """User ✓/✗ on a behavior pattern."""
    if not _engine or not hasattr(_engine, '_behavior_discovery'): raise HTTPException(503)
    _engine._behavior_discovery.handle_user_feedback(req.pattern, req.accepted)
    return {"pattern": req.pattern, "accepted": req.accepted}



# ══════════ v6 Gap Fillers ══════════

@app.get("/v6/behavior/predict")
async def v6_behavior_predict():
    """Manual trigger: predict next user action."""
    if not _engine or not hasattr(_engine, '_behavior_discovery'): raise HTTPException(503)
    bd = _engine._behavior_discovery
    actions = bd._action_history[-10:]
    patterns = {k: {"trigger": p.trigger, "predicted": p.predicted, "conf": round(p.confidence,2)}
                for k, p in bd._patterns.items() if p.confidence > 0.5}
    return {"recent_actions": actions, "predictions": patterns}

@app.get("/v6/belief")
async def v6_belief(session_id: str = "default"):
    """View L2.5 belief accumulator state."""
    if not _engine or not hasattr(_engine, '_belief_accumulator'): raise HTTPException(503)
    return _engine._belief_accumulator.stats()

@app.get("/v6/recursive-map")
async def v6_recursive_map():
    """View/control engineering recursive map."""
    if not _engine or not hasattr(_engine, '_recursive_map'): raise HTTPException(503)
    return _engine._recursive_map.stats()

class MapControl(BaseModel):
    node: str = ""
    action: str = ""  # expand | collapse

@app.put("/v6/recursive-map")
async def v6_recursive_map_control(req: MapControl):
    """Expand/collapse nodes in recursive map."""
    if not _engine or not hasattr(_engine, '_recursive_map'): raise HTTPException(503)
    rm = _engine._recursive_map
    if req.action == "expand": rm.expand(req.node)
    elif req.action == "collapse": rm.collapse(req.node)
    return {"node": req.node, "action": req.action, 
            "expanded": rm._nodes[req.node].expanded if req.node in rm._nodes else False}

@app.post("/v6/meta/retrospect")
async def v6_meta_retrospect(target: str = "", category: str = "parameters"):
    """Manual trigger: retrospection report."""
    if not _engine or not hasattr(_engine, '_meta'): raise HTTPException(503)
    report = _engine._meta.retrospect(target, category)
    if report: return {"target": report.target, "delta": report.delta, "verdict": report.verdict}
    raise HTTPException(404, "Insufficient history for retrospection")

@app.get("/v6/subgraph/cache")
async def v6_subgraph_cache():
    """Subgraph cache stats. Registered before /v6/subgraph/{perspective} so the
    literal 'cache' path is not captured by the path parameter."""
    if not _engine: raise HTTPException(503)
    sc = getattr(_engine, '_subgraph_cache', None)
    if sc: return sc.stats()
    return {"error": "subgraph cache not available"}

@app.get("/v6/subgraph/{perspective}")
async def v6_subgraph(perspective: str = "dialogue"):
    """View compiled subgraph context."""
    if not _engine or not hasattr(_engine, '_subgraph'): raise HTTPException(503)
    if perspective == "dialogue":
        ctx = _engine._subgraph.compile_dialogue()
    elif perspective == "meta":
        ctx = _engine._subgraph.compile_meta()
    else:
        raise HTTPException(400, "Unknown perspective")
    return {"perspective": ctx.perspective, "domains": ctx.domains,
            "entries": [{"domain": e.domain, "content": e.content[:200]} for e in ctx.entries],
            "total_tokens": ctx.total_tokens, "budget": ctx.budget}

@app.get("/v6/engineering/modules")
async def v6_engineering_modules():
    """List engineering modules with constraints."""
    if not _engine or not hasattr(_engine, '_engineering_knowledge'): raise HTTPException(503)
    ek = _engine._engineering_knowledge
    modules = []
    if hasattr(ek, 'get_by_type'):
        try:
            from core.agent.v3_2.engineering_chain.models import KnowledgeType
            for n in ek.get_by_type(KnowledgeType.CONSTRAINT)[:20]:
                modules.append({"name": str(getattr(n, 'name', '?')), "type": "constraint"})
        except: pass
    return {"modules": modules}

class EngineeringEdit(BaseModel):
    name: str = ""
    action: str = ""  # add_constraint | remove_constraint
    constraint: str = ""

@app.put("/v6/engineering/constraints")
async def v6_engineering_constraints_edit(req: EngineeringEdit):
    """Edit engineering constraints."""
    if not _engine: raise HTTPException(503)
    rec_map = getattr(_engine, '_recursive_map', None)
    if rec_map and req.action == "add_constraint" and req.name and req.constraint:
        rec_map.bind_constraint(req.name, req.constraint)
        return {"updated": req.name, "constraint": req.constraint}
    raise HTTPException(404, "Recursive map not available")



@app.get("/v6/sync")
async def v6_sync(block_id: str = ""):
    """Strong-consistency read: block until all pending events processed."""
    if not _engine: raise HTTPException(503)
    if not block_id:
        return {"status": "sync_ready", "pending": 0}
    # Force collect async dispatcher
    if hasattr(_engine, '_async_dispatch') and _engine._async_dispatch:
        _engine._async_dispatch.collect(max_results=10)
    # Return latest state for block
    state = getattr(_engine, '_sharded_state', None)
    if state:
        bs = state.get(block_id)
        return {"block_id": block_id, "text": bs.text[:200] if hasattr(bs, 'text') else "?"}
    return {"block_id": block_id, "text": "?"}

@app.get("/v6/causal-chain")
async def v6_causal_chain(event: str = ""):
    """Trace causal chain for UI optimistic updates."""
    if not _engine or not hasattr(_engine, '_causal_tracker'): raise HTTPException(503)
    ct = _engine._causal_tracker
    if event:
        chain = ct.get_chain(event)
        return {"chain": chain, "remaining": ct.estimate_remaining(len(chain))}
    return ct.stats()

@app.get("/v6/degradation")
async def v6_degradation():
    """Current system degradation level."""
    if not _engine or not hasattr(_engine, '_degradation'): raise HTTPException(503)
    d = _engine._degradation
    return {"level": d.level.name, "queue_depth": d._queue_depth}


@app.get("/v6/causal")
async def v6_causal():
    """Causal chain: L4 temporal → L5 causal candidates."""
    if not _engine: raise HTTPException(503)
    cp = getattr(_engine, '_causal_promoter', None)
    if cp: return cp.stats()
    return {"error": "causal promoter not available"}

@app.get("/v6/ttl")
async def v6_ttl():
    """TTL/HCWA temperature migration status."""
    if not _engine: raise HTTPException(503)
    tm = getattr(_engine, '_ttl_manager', None)
    if tm: return tm.stats()
    return {"error": "TTL manager not available"}

@app.post("/v6/ttl/tick")
async def v6_ttl_tick():
    """Trigger TTL temperature migration tick."""
    if not _engine: raise HTTPException(503)
    tm = getattr(_engine, '_ttl_manager', None)
    if tm: return tm.tick()
    return {"error": "TTL manager not available"}

@app.get("/v6/audit")
async def v6_audit(category: str = "", action: str = "", limit: int = 50):
    """Unified audit trail: all user + system operations."""
    if not _engine or not hasattr(_engine, '_audit_trail') or _engine._audit_trail is None:
        return {"records": [], "total_operations": 0, "by_category": {}, "by_action": {}}
    records = _engine._audit_trail.query(category=category, action=action, limit=limit)
    return {
        "records": [{"ts": r.ts, "category": r.category, "action": r.action,
                      "target": r.target, "before": r.before, "after": r.after,
                      "author": r.author} for r in records],
        **(_engine._audit_trail.stats()),
    }

@app.get("/v6/audit/recent")
async def v6_audit_recent():
    """Recent user actions (frontend: 'what did I just do?')."""
    if not _engine or not hasattr(_engine, '_audit_trail') or _engine._audit_trail is None:
        return {"actions": []}
    records = _engine._audit_trail.recent_user_actions(20)
    return {"actions": [{"ts": r.ts, "category": r.category, "action": r.action,
                          "target": r.target} for r in records]}

@app.get("/v6/audit/history")
async def v6_audit_history(days: int = 7):
    """Audit activity trend over N days."""
    if not _engine or not hasattr(_engine, '_audit_trail') or _engine._audit_trail is None:
        return {}
    return _engine._audit_trail.history(days)

@app.get("/v6/monitor/interactions")
async def monitor_interactions(limit: int = 50, errors_only: bool = False):
    """FE↔API interaction log — every request/response pair."""
    mon = get_interaction_monitor()
    if errors_only:
        return {"errors": mon.errors(limit)}
    return {"recent": mon.recent(limit), "stats": mon.stats()}

@app.get("/v6/monitor/stats")
async def monitor_stats():
    """Interaction monitor stats — success rate, top paths, avg response."""
    return get_interaction_monitor().stats()

@app.get("/v6/monitor/slow")
async def monitor_slow(threshold_ms: int = 500):
    """Slow requests above threshold."""
    return {"slow": get_interaction_monitor().slow_requests(threshold_ms)}

@app.get("/v6/monitor/errors")
async def monitor_errors():
    """Recent errors only."""
    return {"errors": get_interaction_monitor().errors(30)}


@app.get("/v6/monitor/dashboard")
async def monitor_dashboard():
    """HTML mini-dashboard — live API monitoring."""
    from starlette.responses import HTMLResponse
    mon = get_interaction_monitor()
    return HTMLResponse(mon.dashboard_html())

@app.get("/v6/monitor/gateway-raw")
async def monitor_gateway_raw():
    """Dump raw gateway responses — shows exactly what frontend sees."""
    import urllib.request, json
    base = "http://127.0.0.1:8080"
    results = {}
    for path in ["/v1/health", "/v1/providers", "/v1/diagnostics", "/v1/stats"]:
        try:
            req = urllib.request.Request(base + path)
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode()[:5000]
                results[path] = {"status": resp.status, "body": json.loads(body) if body else None}
        except Exception as e:
            results[path] = {"error": str(e)}
    return results


@app.get("/v6/monitor/traces")
async def monitor_traces(limit: int = 20):
    """Recent distributed traces."""
    return {"traces": get_tracer().recent_traces(limit)}

@app.get("/v6/monitor/trace/{trace_id}")
async def monitor_trace_detail(trace_id: str):
    """Full trace detail — all spans with timing."""
    spans = get_tracer().get_trace(trace_id)
    return {"trace_id": trace_id, "spans": spans}

@app.get("/v6/monitor/trace/{trace_id}/waterfall")
async def monitor_waterfall(trace_id: str):
    """Waterfall HTML view for a trace."""
    return HTMLResponse(get_tracer().waterfall(trace_id))

if __name__ == "__main__":

    serve()

# ═══════ V3 Session endpoints (frontend chat compatibility) ═══════

@app.post("/v3/session")
async def v3_create_session():
    """Create a new chat session (frontend compatibility)."""
    import uuid
    sid = str(uuid.uuid4())[:12]
    return {"session_id": sid, "ws_url": "", "created": time.time()}

@app.post("/v3/session/{session_id}/message")
async def v3_send_message(session_id: str, req: Request):
    """Send a message in a session (frontend compatibility)."""
    body = await req.json()
    text = body.get("content", "")
    provider = body.get("provider")
    model = body.get("model")
    try:
        evt = EventRequest(
            text=text, source="user", session_id=session_id,
            event_id=f"v3_{session_id}_{int(time.time())}",
        )
        # Switch provider if requested
        if provider and model:
            try:
                from core.agent.llm_providers.openai_provider import OpenAIProvider
                _engine._llm_provider = OpenAIProvider(provider, {
                    "base_url": f"http://127.0.0.1:8080/v1",
                    "api_key": "not-needed",
                    "model": model,
                })
            except Exception: pass
        r = await post_event(evt)
        reply = ""
        if isinstance(r, dict):
            reply = r.get("reply", r.get("response", r.get("text", str(r)[:500])))
        elif hasattr(r, 'response'):
            reply = r.response
        return {"content": reply, "session_id": session_id, "status": "accepted"}
    except Exception as e:
        return {"content": f"[Error] {e}", "session_id": session_id, "status": "error"}


@app.get("/v3/session/{session_id}/history")
async def v3_session_history(session_id: str, limit: int = 50, offset: int = 0):
    """Get session history (frontend compatibility)."""
    return {"session_id": session_id, "messages": [], "total": 0}

@app.get("/v3/session/{session_id}/status")
async def v3_session_status(session_id: str):
    """Get session status (frontend compatibility)."""
    return {"session_id": session_id, "status": "active", "message_count": 0}
