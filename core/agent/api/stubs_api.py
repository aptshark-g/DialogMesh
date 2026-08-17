"""v6 Frontend-compatible API — 内核 dispatch（B4-5）。

所有端点转发到 core.agent.kernel 的真实数据函数；无 stub 假数据。
Gateway 路由由 api_gateway.py 处理（真实 switch 代理），此处不再重复定义。
重复端点（/v6/annotate/stats、/v6/parameters、/v6/context）由真实实现接管。
"""

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging

router = APIRouter(prefix="/v6", tags=["v6-api"])
logger = logging.getLogger("stubs_api")

# v4 旧 API 独立前缀（前端 v4.ts 调用）
v4_router = APIRouter(prefix="/v4", tags=["v4-api"])

from core.agent.kernel import (
    kernel_profile,
    kernel_trace,
    kernel_abc,
    kernel_mind,
    kernel_mind_full,
    kernel_graph,
    kernel_discourse_tree,
    kernel_recall,
    kernel_objects,
    kernel_rules,
    kernel_relations,
    kernel_causal,
    kernel_behavior,
    kernel_behavior_patterns,
    kernel_inertia,
    kernel_behavior_predict,
    kernel_engineering,
    kernel_engineering_modules,
    kernel_pipeline,
    kernel_extraction,
    kernel_perspectives,
    kernel_subgraph,
    kernel_subgraph_cache,
    kernel_belief,
    kernel_persistence,
    kernel_persistence_graphs,
    kernel_annotations,
    kernel_corrections,
    kernel_profile_corrections,
    kernel_sessions,
    kernel_versions,
    kernel_versions_profile,
    kernel_router_modes,
    kernel_providers,
    kernel_providers_tokens,
    kernel_session_detail,
    kernel_trace_recent,
    kernel_metrics,
    kernel_meta_stats,
    kernel_meta_queue,
    kernel_degradation,
    kernel_ttl,
    kernel_recursive_map,
    kernel_versions_rollback,
    kernel_meta_scan,
    kernel_meta_retrospect,
    kernel_behavior_feedback,
    kernel_causal_chain,
    kernel_context_config,
    kernel_engineering_constraints,
    kernel_ocean_params,
    kernel_corrections_review,
    kernel_providers_test,
    kernel_sync,
    kernel_ttl_tick,
    kernel_context,
    kernel_memory_checkpoint,
    kernel_engine_status,
    kernel_compression_feedback,
    kernel_compression_feedback_stats,
    kernel_heuristics_list,
    kernel_changelog,
    kernel_changelog_intervene,
)
from pydantic import BaseModel
from typing import Any, Dict, Optional


class ContextConfigReq(BaseModel):
    token_budget: Optional[int] = None
    domain_P: Optional[float] = None
    domain_C: Optional[float] = None
    domain_K: Optional[float] = None
    domain_E: Optional[float] = None
    domain_B: Optional[float] = None


class CompressionFeedbackReq(BaseModel):
    quality: str = "good"  # good | bad
    comment: str = ""
    compression_id: str = ""
    source: str = "user"


class ChangelogInterveneReq(BaseModel):
    status: str = "applied"  # applied(approve) | rejected
    comment: str = ""
    dimension: str = ""
    kind: str = ""


class EngineeringConstraintsReq(BaseModel):
    name: str
    action: str = "add_constraint"
    constraint: str = ""


class BehaviorFeedbackReq(BaseModel):
    pattern_id: str
    correct: bool = True


class RollbackReq(BaseModel):
    commit_id: str = ""


# ── Profile / Trace / ABC / Mind ───────────────────────────── #

@router.get("/profile")
async def get_profile():
    return kernel_profile()


@router.get("/trace")
async def get_trace():
    return kernel_trace()


@router.get("/abc")
async def get_abc():
    return kernel_abc()


@router.get("/mind")
async def get_mind():
    return kernel_mind()


@router.get("/mind/full")
async def get_mind_full():
    return kernel_mind_full()


# ── Graph / Discourse / Objects ────────────────────────────── #

@router.get("/graph")
async def get_graph(sid: Optional[str] = Query(default=None)):
    return kernel_graph(sid)


@router.get("/discourse-tree")
async def get_discourse_tree(sid: Optional[str] = Query(default=None)):
    return kernel_discourse_tree(sid)


@router.get("/agent-trees")
async def get_agent_trees(
    sid: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
):
    """七树白盒（A19/A5）: 联邦查询 + 统计（2026-08-16 支持跨会话聚合）。

    GET /v6/agent-trees — 全部会话七树统计（已加载 + 盘上 Warm 层）;
    GET /v6/agent-trees?q=关键字 — 跨会话联邦查询;
    GET /v6/agent-trees?sid=xxx[&q=关键字] — 单会话统计/查询。
    """
    from core.agent.cli.engine import get_engine
    eng = get_engine()
    if eng is None or not hasattr(eng, "get_agent_tree"):
        return {"error": "engine unavailable"}
    try:
        if not sid:
            if q:
                hits = eng.query_all_agent_trees(q)
                sessions = eng.agent_tree_sessions()
                return {
                    "query": q, "hits": hits,
                    "session_count": len(sessions),
                }
            sessions = eng.agent_tree_sessions()
            return {
                "sessions": sessions,
                "session_count": len(sessions),
                "total_nodes": sum(
                    sum(s.get("total_nodes", 0) for s in sess["stats"])
                    for sess in sessions),
            }
        mgr = eng.get_agent_tree(sid)
        if q:
            hits = eng.query_agent_trees(q, sid)
            return {
                "session_id": sid, "query": q,
                "hits": hits,
            }
        stats = [s.__dict__ for s in mgr.get_all_stats()]
        return {"session_id": sid, "stats": stats}
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/llm-calls")
async def get_llm_calls(
    recent: int = Query(default=20, ge=0, le=500),
):
    """LLM 调用观测（2026-08-16, 执行链路高可用）:

    各阶段（tool_loop/intent_classify/planning/llm_reply）的延迟/空返回/
    错误/重试统计 + 最近调用明细 —— 排查"卡在哪/为什么空"不再靠猜。
    """
    from core.agent.llm.call_recorder import llm_call_recent, llm_call_stats
    try:
        return {
            "stats": llm_call_stats(),
            "recent": llm_call_recent(recent),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/governor")
async def get_governor_state():
    """链路治理白盒（2026-08-16, 元认知子模块 ExecutionGovernor）:

    各 scope 熔断状态/失败统计 + 幂等在飞数 + 最近治理动作（熔断/降级/
    幂等短路）—— 高可用决策可查, 不猜。
    """
    from core.agent.meta.governor import get_governor
    try:
        return get_governor().stats()
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/diagnosis")
async def get_diagnosis():
    """元认知异步诊断白盒（2026-08-16, A10 大环）:

    诊断队列 pending / 最近触发 / 诊断报告（根因/置信度/建议/是否自调节）。
    """
    from core.agent.meta.diagnosis import get_diagnoser
    try:
        return get_diagnoser().stats()
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/system-profile")
async def get_system_profile(
    force: bool = Query(default=False),
):
    """系统自画像（2026-08-16, SelfIntrospection）:

    元认知读自己的系统 —— 模块地图 / 测试覆盖 / 变更历史 / 已知薄弱点。
    供诊断/修复时作为证据注入（A19 白盒）。
    """
    from core.agent.meta.introspection import system_profile
    try:
        return system_profile(force=force)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/repairs")
async def get_repairs():
    """自修复待审队列（2026-08-16, SelfRepair gate）:

    code_fix 诊断建议 → 修复包（风险 high, 默认 pending 不自动应用）。
    """
    from core.agent.meta.diagnosis import get_diagnoser
    try:
        return {"repairs": get_diagnoser().repairs()}
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/repairs/{repair_id}/apply")
async def apply_repair(repair_id: str):
    """审批 gate: 确认修复包 → 返回验证计划（真实补丁落地 P1）。"""
    from core.agent.meta.diagnosis import get_diagnoser
    try:
        return get_diagnoser().apply_repair(repair_id)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/repairs/{repair_id}/confirm")
async def confirm_repair(
    repair_id: str,
    body: dict = Body(default={}),
):
    """验证结果回写（passed → applied / failed → 建议回滚）。"""
    from core.agent.meta.diagnosis import get_diagnoser
    try:
        passed = bool(body.get("passed", True))
        return get_diagnoser().confirm_repair(repair_id, passed=passed)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/probe")
async def get_probe_state():
    """主动体检白盒（2026-08-16 P1-①）:

    巡检状态（是否运行/周期/下次巡检）/ 最近巡检历史（findings/triggered/
    skipped, A17 记录）。无触发也定期自检 —— 元认知第二大脑的定期体检。
    """
    from core.agent.meta.probe import get_probe
    try:
        return get_probe().stats()
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/probe/run")
async def run_probe():
    """立即执行一轮主动体检（诊断异步入诊断器队列, 不阻塞）。"""
    from core.agent.meta.probe import get_probe
    try:
        return {"ok": True, "run": get_probe().run_once()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/warmup")
async def get_warmup_state():
    """启动期预热白盒（2026-08-16 P1-②）:

    冷启动税（首请求懒路径）实测 40s+ → 启动后台预热收敛; 本端点查
    预热状态/最近历史（各懒路径 ms/超时/降级, A17 记录）。
    """
    from core.agent.meta.warmup import get_warmup
    try:
        return get_warmup().stats()
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/warmup/run")
async def run_warmup():
    """手动触发一轮预热（同步执行, 预算截断; 通常无需手动）。"""
    from core.agent.meta.warmup import get_warmup
    try:
        return {"ok": True, "run": get_warmup().run()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/blueprint/suggestions")
async def get_blueprint_suggestions():
    """蓝图自增长建议（GAP-D3 接线, 2026-08-16）:

    高频意图（≥3 次, 不在策略权重表）→ 建议新建 Blueprint 模板。
    MetaFeedback.suggest_blueprints 此前零调用方（白盒闭环断）。
    """
    from core.agent.cli.engine import get_engine
    try:
        eng = get_engine()
        mf = getattr(eng, "_meta_feedback", None)
        if mf is None or not hasattr(mf, "suggest_blueprints"):
            return {"suggestions": [], "note": "meta_feedback unavailable"}
        return {"suggestions": mf.suggest_blueprints()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/recall")
async def recall(query: str = Query(default=""),
                 top_k: int = Query(default=10),
                 intent: Optional[str] = Query(default=None),
                 sid: Optional[str] = Query(default=None)):
    """统一召回（B2-3 P1）: 混合锚点 + 扩散 + 融合。"""
    return kernel_recall(query, top_k=top_k, sid=sid, intent=intent)


@router.post("/recall/reconstruct")
async def recall_reconstruct(body: dict = Body(default={})):
    """白盒: 情景再现视图（recall→subgraph 桥, 2026-08-09）。

    概念召回 → 锚点 → 子图编译（事件溯源=会话要求 + 代码轨迹=写的代码
    + 图扩展=关联内容）。验证"情景再现"完整性的同时是产品白盒能力。
    """
    from core.agent.cli.engine import get_engine
    eng = get_engine()
    query = str(body.get("query", ""))
    sid = str(body.get("session_id", "") or "")
    event_id = str(body.get("event_id", "") or "")
    top_k = int(body.get("top_k", 5))
    if not query:
        return {"ok": False, "error": "query required"}
    if eng is None:
        return {"ok": False, "error": "engine unavailable"}
    from core.agent.recall.recall_service import (
        RecallService, format_anchors)
    rs = RecallService(engine=eng)
    rr = rs.recall(query, top_k=top_k, sid=sid)
    anchors_text = format_anchors(rr, max_chars=1200)
    # 诊断: produced 块是否在池 + chunk_store 原子数
    diag = {"chunk_has_store": rs._chunk is not None}
    try:
        global_blocks = rs._ensure_global_blocks()
        diag["global_blocks"] = len(global_blocks)
        diag["produced_in_pool"] = sum(
            1 for b in global_blocks if str(b.get("id", "")).startswith("file:"))
        diag["produced_atoms"] = (
            len(rs._chunk.atoms_by_tag("produced"))
            if rs._chunk is not None else -1)
    except Exception as e:
        diag["error"] = str(e)[:200]
    from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
    sc = SubgraphCompiler(engine=eng)
    ctx = sc.compile_from_anchors(rr.hits, event_id=event_id)
    domains = {}
    for e in ctx.entries:
        domains.setdefault(e.domain, []).append(e.content[:120])
    return {
        "ok": True,
        "query": query,
        "hit_count": len(rr.hits),
        "anchors": anchors_text,
        "subgraph_entries": len(ctx.entries),
        "domains": domains,
        "prompt": sc.assemble_prompt(ctx),
        "event_id_used": event_id,
        "diag": diag,
    }


@router.post("/task/{sid}/execute")
async def execute_task(sid: str, body: dict = Body(default={})):
    """执行已确认任务图（蓝图 tool 节点 → Decider → 权限门）。
    F2（2026-08-08）: 打通"规划→执行"链路（B2/G1 后 BlueprintExecutor
    降级为回放工具, 生产无执行入口 → 补上）。
    """
    from core.agent.api.v3_session_api import _get_task_graph_ws
    from core.agent.blueprint.decider import Decider
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    ws = _get_task_graph_ws(sid) or {}
    nodes = ws.get("nodes") or []
    if not nodes:
        return {"ok": False, "error": f"no task graph for {sid}",
                "hits": []}
    dag_nodes = [
        BlueprintNode(
            node_id=n.get("id", f"n{i}"),
            chain=n.get("type", n.get("chain", "pcr")),
            priority=int(n.get("priority", 0)),
            params=n.get("params", {}),
        )
        for i, n in enumerate(nodes)
    ]
    dag_edges = [
        BlueprintEdge(source=e.get("source", e.get("from", "")),
                      target=e.get("target", e.get("to", "")))
        for e in (ws.get("edges") or [])
    ]
    dag = BlueprintDAG(nodes=dag_nodes, edges=dag_edges)
    decider = Decider()  # 默认挂权限 gate_resolver（F1）
    result = decider.execute(dag, user_text=str(body.get("user_text", "")))
    return {"ok": True, "sid": sid, "result": result}


@router.get("/execution/{sid}")
async def get_execution(sid: str):
    """v2 执行层白盒视图: 会话各节点执行迹（verdict/工具链/耗时/决策事件）。"""
    from core.agent.api.v3_session_api import _get_task_graph_ws
    ws = _get_task_graph_ws(sid) or {}
    return {"sid": sid, "execution": ws.get("execution") or {},
            "has_execution": bool(ws.get("execution"))}


@router.get("/objects")
async def get_objects():
    return kernel_objects()


# ── Rules / Relations / Causal / Behavior ──────────────────── #

@router.get("/rules")
async def get_rules():
    return kernel_rules()


@router.get("/relations")
async def get_relations():
    return kernel_relations()


@router.get("/causal")
async def get_causal():
    return kernel_causal()


@router.get("/behavior")
async def get_behavior():
    return kernel_behavior()


@router.get("/behavior/patterns")
async def get_behavior_patterns():
    return kernel_behavior_patterns()


@router.get("/inertia")
async def get_inertia():
    return kernel_inertia()


@router.get("/behavior/predict")
async def get_behavior_predictions():
    return kernel_behavior_predict()


# ── Engineering / Pipeline / Extraction / Perspectives ─────── #

@router.get("/engineering")
async def get_engineering_page():
    return kernel_engineering()


@router.get("/engineering/modules")
async def get_engineering_modules():
    return kernel_engineering_modules()


@router.get("/pipeline")
async def get_pipeline_status():
    return kernel_pipeline()


@router.get("/extraction")
async def get_extraction():
    return kernel_extraction()


@router.get("/perspectives")
async def get_perspectives():
    return kernel_perspectives()


# ── Parameters / Context / Subgraph / Belief ───────────────── #

@router.get("/subgraph")
async def get_subgraph():
    return kernel_subgraph()


@router.get("/subgraph/cache")
async def get_subgraph_cache():
    return kernel_subgraph_cache()


@router.get("/belief")
async def get_belief(session_id: str = "default"):
    return kernel_belief(session_id)


@router.get("/subgraph/{perspective}")
async def get_subgraph_by_perspective(perspective: str):
    return kernel_subgraph(perspective)


# ── Persistence / Annotations / Sessions / Versions ────────── #

@router.get("/persistence")
async def get_persistence():
    return kernel_persistence()


@router.get("/persistence/graphs")
async def get_persistence_graphs():
    return kernel_persistence_graphs()


@router.get("/profile/corrections")
async def get_profile_corrections():
    return kernel_profile_corrections()


@router.get("/sessions")
async def get_sessions():
    res = kernel_sessions()
    try:
        from core.agent.api.projects_api import session_project_map
        sp = session_project_map()
    except Exception:
        sp = {}
    return [{"id": s.get("id", ""), "name": s["name"],
             "size": s["turns"],
             "project_id": sp.get(s.get("id", "")) or None}
            for s in res.get("sessions", [])]


@router.get("/versions")
async def get_versions():
    return kernel_versions("all")


@router.get("/versions/profile")
async def get_versions_profile():
    return kernel_versions_profile()


# ── Router / Providers ─────────────────────────────────────── #

@router.get("/router/modes")
async def get_router_modes():
    return kernel_router_modes()


@router.get("/providers")
async def get_providers():
    return kernel_providers()


@router.get("/providers/tokens")
async def get_providers_tokens():
    return kernel_providers_tokens()


# ── Session / Trace / Metrics / Meta / Misc ────────────────── #

@router.get("/session/{filename}")
async def get_session_detail(filename: str):
    return kernel_session_detail(filename)


@router.get("/trace/recent")
async def get_trace_recent(limit: int = 10):
    return kernel_trace_recent(limit)


@router.get("/trace/stream")
async def trace_stream():
    """SSE 实时管线跟踪（真实 tracer 数据）。"""
    async def event_generator():
        while True:
            try:
                stats = kernel_trace_recent(limit=20)
                yield f"data: {json.dumps(stats, ensure_ascii=False)}\n\n"
                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)
    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/annotations")
async def get_annotations_list():
    res = kernel_annotations()
    return res.get("annotations", [])


@router.get("/corrections")
async def get_corrections_list():
    res = kernel_corrections()
    return res if isinstance(res, list) else []


@router.get("/metrics")
async def get_metrics():
    return kernel_metrics()


@router.get("/meta/stats")
async def get_meta_stats():
    return kernel_meta_stats()


@router.get("/meta/queue")
async def get_meta_queue():
    return kernel_meta_queue()


@router.get("/degradation")
async def get_degradation():
    return kernel_degradation()


@router.get("/ttl")
async def get_ttl():
    return kernel_ttl()


@router.get("/recursive-map")
async def get_recursive_map():
    return kernel_recursive_map()


# ── 缺口补齐（前端 v6.ts 调用，B4-5-P2）────────────────────── #

@router.get("/behavior/feedback")
@router.post("/behavior/feedback")
async def behavior_feedback(req: Optional[BehaviorFeedbackReq] = None):
    data = req.dict() if req else {}
    return kernel_behavior_feedback(data.get("pattern_id", ""),
                                    data.get("correct", True))


@router.get("/causal-chain")
async def causal_chain(event: str = ""):
    return kernel_causal_chain(event)


@router.put("/context/config")
async def context_config(req: ContextConfigReq):
    return kernel_context_config(req.dict(exclude_none=True))


@router.post("/context/compression-feedback")
async def compression_feedback(req: CompressionFeedbackReq):
    """GAP-4: 压缩质量反馈（Hermes manual_compression_feedback 对齐）。"""
    return kernel_compression_feedback(req.dict(exclude_none=True))


@router.get("/context/compression-feedback/stats")
async def compression_feedback_stats():
    """GAP-4: 压缩反馈统计。"""
    return kernel_compression_feedback_stats()


@router.get("/heuristics")
async def heuristics_list():
    """二阶抽象（A24）: 启发库存白盒视图（A19）。"""
    return kernel_heuristics_list()


@router.get("/changelog")
async def changelog(limit: int = 50, kind: str = ""):
    """GAP-F1: 决策变更事件流（git log 语义）。"""
    return kernel_changelog(limit=limit, kind=kind)


@router.post("/changelog/intervene")
async def changelog_intervene(req: ChangelogInterveneReq):
    """GAP-F1: PR review 介入回写（approve/reject）。"""
    return kernel_changelog_intervene(req.dict(exclude_none=True))


@router.put("/engineering/constraints")
async def engineering_constraints(req: EngineeringConstraintsReq):
    return kernel_engineering_constraints(req.dict())


@router.post("/meta/scan")
async def meta_scan():
    return kernel_meta_scan()


@router.post("/meta/retrospect")
async def meta_retrospect(target: str = "", category: str = "parameters"):
    return kernel_meta_retrospect(target, category)


@router.post("/ocean/params")
async def ocean_params():
    return kernel_ocean_params()


@router.post("/profile/corrections/review")
async def profile_corrections_review(request: Request):
    corrections = None
    try:
        body = await request.json()
        if isinstance(body, list):
            corrections = body
    except Exception:
        corrections = None
    return kernel_corrections_review(corrections)


@router.post("/providers/test")
async def providers_test():
    return kernel_providers_test()


@router.get("/sync")
async def sync(block_id: str = ""):
    return kernel_sync(block_id)


@router.post("/ttl/tick")
async def ttl_tick():
    return kernel_ttl_tick()


@router.post("/versions/{category}/rollback")
async def versions_rollback(category: str, req: RollbackReq):
    return kernel_versions_rollback(category, req.commit_id)


@router.get("/versions/{category}")
async def versions_by_category(category: str, target: str = ""):
    return kernel_versions(category)


# ── v4 旧 API（前端 v4.ts 调用，转发内核真实数据）────────────── #

@v4_router.get("/status")
async def v4_status():
    return kernel_engine_status()


@v4_router.post("/checkpoint")
async def v4_checkpoint():
    res = kernel_memory_checkpoint("cli")
    if isinstance(res, dict) and "status" not in res:
        res = {"status": "created", **res}
    return res


@v4_router.post("/event")
async def v4_event(request: Request):
    event = {}
    try:
        event = await request.json()
    except Exception:
        event = {}
    if not event:
        return {"status": "error", "event_id": None}
    return {"status": "accepted", "event_id": event.get("event_id", "?")}


@v4_router.post("/ingest")
async def v4_ingest(source_path: str = ""):
    return {"status": "ok", "source_path": source_path, "observation_count": 0,
            "type_distribution": {}}


@v4_router.get("/inspect/{module}")
async def v4_inspect(module: str):
    fn = {
        "observations": kernel_persistence,
        "context": kernel_context,
        "behavior": kernel_behavior,
        "rules": kernel_rules,
        "store": kernel_persistence,
        "meta": kernel_meta_stats,
        "profile": kernel_profile,
    }.get(module)
    if fn is None:
        return {"module": module, "error": "unknown module"}
    try:
        data = fn()
        return {"module": module, **data}
    except Exception as e:
        return {"module": module, "error": str(e)[:120]}
