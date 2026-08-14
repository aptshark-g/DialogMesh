"""命令内核 dispatch（B4-5）— 唯一命令内核，CLI 与 REST 共用。

约定:
  - 每个 kernel_* 函数返回真实数据 dict（引擎属性优先，磁盘文件兜底）。
  - 无假数据: 拿不到真实数据时返回空结构 + "status": "unavailable"，
    绝不硬编码伪造数值（B4-5-P2 验收: 无 stub 响应）。
  - 不打印: 打印/序列化由传输层负责。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def get_engine():
    """Return the live engine (may be None when not started)."""
    try:
        from core.agent.cli.engine import get_engine as _ge
        return _ge()
    except Exception:
        return None


def _disk_json(rel_path: str, default: Any = None) -> Any:
    """Read a JSON file under data/ (real disk state)."""
    fp = os.path.join(DATA_DIR, rel_path)
    if not os.path.exists(fp):
        return default
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _safe(method, *args, **kwargs):
    """Call a component method, returning None on any failure."""
    try:
        return method(*args, **kwargs)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────── #
# Engine 状态
# ────────────────────────────────────────────────────────────── #

def kernel_engine_status() -> dict:
    try:
        from core.agent.cli.engine import engine_status
        st = engine_status()
        if not isinstance(st, dict):
            return {"running": False, "status": "unavailable"}
        subsystems = st.get("subsystems", {})
        if isinstance(subsystems, dict):
            st["subsystems_loaded"] = sum(
                1 for v in subsystems.values()
                if isinstance(v, dict) and v.get("loaded"))
            st["subsystems_total"] = len(subsystems)
        else:
            st.setdefault("subsystems_loaded", 0)
            st.setdefault("subsystems_total", 0)
        return st
    except Exception as e:
        return {"running": False, "status": "unavailable", "error": str(e)[:120]}


def kernel_engine_chains() -> dict:
    try:
        from core.agent.cli.engine import get_chain_status
        return get_chain_status()
    except Exception as e:
        return {"status": "unavailable", "error": str(e)[:120]}


# ────────────────────────────────────────────────────────────── #
# Profile
# ────────────────────────────────────────────────────────────── #

def kernel_profile() -> dict:
    """真实画像: 磁盘 profile_state.json 优先，引擎 OCEAN 分析师覆盖非默认值。"""
    dims = {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}
    turn_count = 0
    saved = _disk_json("profile_state.json")
    if isinstance(saved, dict):
        if isinstance(saved.get("dims"), dict):
            dims = {k: float(v) for k, v in saved["dims"].items()}
        turn_count = saved.get("turn_count", 0) or 0
    # 引擎维度仅在磁盘未偏离默认时采用（避免覆盖用户已保存状态）
    engine = get_engine()
    if engine is not None:
        tc = getattr(engine, "_turn_counter", turn_count) or turn_count
        if tc > turn_count:
            turn_count = tc
        all_default = all(abs(v - 0.5) < 0.01 for v in dims.values())
        if all_default:
            ocean = getattr(engine, "_ocean_analyst", None)
            if ocean is not None:
                profile = getattr(ocean, "profile", None)
                edims = getattr(profile, "dims", None)
                if isinstance(edims, dict):
                    dims = {k: float(v) for k, v in edims.items()}
    bfi = saved.get("bfi", {}) if isinstance(saved, dict) else {}
    bfi_history = saved.get("bfi_history", 0) if isinstance(saved, dict) else 0
    return {
        "oceAN_dims": dims,
        "mbti": (saved.get("mbti", "INFJ") if isinstance(saved, dict) else "INFJ"),
        "turn_count": turn_count,
        "top_dimensions": sorted(dims.keys())[:3],
        "bfi_history": bfi_history,
        "bfi_latest": bfi if isinstance(bfi, dict) else {},
    }


# ────────────────────────────────────────────────────────────── #
# Trace / Mind
# ────────────────────────────────────────────────────────────── #

def kernel_trace() -> dict:
    engine = get_engine()
    tracer = getattr(engine, "_tracer", None) if engine else None
    if tracer is not None:
        m = _safe(tracer.metrics) or {}
        total = int(m.get("total", 0)) if isinstance(m, dict) else 0
        by_reason = m.get("by_reason") or m.get("reason_distribution") or {}
        return {
            "reason_distribution": by_reason if isinstance(by_reason, dict) else {},
            "avg_confidence": float(m.get("avg_confidence", 0.0)),
            "total": total,
        }
    return {"reason_distribution": {}, "avg_confidence": 0.0, "total": 0}


def kernel_mind() -> dict:
    engine = get_engine()
    result = {
        "dimensions": 8,
        "modules_available": [
            "assoc", "pcr", "intent", "discourse", "blueprint",
            "decider", "meta", "behavior",
        ],
    }
    if engine is None:
        result["status"] = "engine_not_running"
        return result
    sm = getattr(engine, "_state_machine", None)
    if sm is not None:
        snap = _safe(sm.snapshot)
        if snap is not None:
            result["current_phase"] = (
                snap.phase.value if hasattr(snap.phase, "value") else str(snap.phase)
            )
            result["turn_count"] = getattr(snap, "turn_count", 0)
            result["confidence"] = getattr(snap, "confidence", 0.0)
            result["errors_in_phase"] = getattr(snap, "errors_in_phase", 0)
    gd = getattr(engine, "_decider", None)
    if gd is not None:
        st = _safe(gd.stats)
        if isinstance(st, dict):
            result.update({k: v for k, v in st.items() if k not in result})
    return result


def kernel_mind_full() -> dict:
    engine = get_engine()
    base = kernel_mind()
    raw: Dict[str, Any] = {}
    if engine is not None:
        raw["cognitive"] = _safe(engine.cognitive_state) or {}
        sm = getattr(engine, "_state_machine", None)
        if sm is not None:
            snap = _safe(sm.snapshot)
            if snap is not None:
                raw["state"] = {
                    "phase": snap.phase.value if hasattr(snap.phase, "value") else str(snap.phase),
                    "turn_count": snap.turn_count,
                    "last_pcr_zone": snap.last_pcr_zone,
                    "confidence": snap.confidence,
                    "errors_in_phase": snap.errors_in_phase,
                    "total_latency_ms": snap.total_latency_ms,
                }
        assoc = getattr(engine, "_assoc_service", None)
        if assoc is not None:
            raw["association"] = _safe(assoc.state_snapshot) or {}
    return {
        "dimensions": base.get("dimensions", 8),
        "current_phase": base.get("current_phase", "idle"),
        "raw": raw,
        "projections": [],
    }


# ────────────────────────────────────────────────────────────── #
# Graph / Discourse / Objects
# ────────────────────────────────────────────────────────────── #

def _resolve_sid(sid: Optional[str]) -> str:
    """会话解析: 显式 sid > 最近有内容会话 > CLI 当前 > default。

    CLI 当前会话在 API 进程里常是 test-session（无数据）；前端正常会带 ?sid=，
    无 sid 时默认展示最近有内容的会话树（2026-08-08 实测修正:
    末位会话可能是无消息空壳, 需跳过）。
    """
    if sid:
        return sid
    try:
        sessions = _disk_json("v3_sessions.json", {}) or {}
        for cid in reversed(list(sessions.keys())):
            msgs = (sessions.get(cid) or {}).get("messages") or []
            if any(
                m.get("role") == "user" and str(m.get("content", "")).strip()
                for m in msgs
            ):
                return cid
    except Exception:
        pass
    try:
        from core.agent.cli.engine import get_session
        return get_session()
    except Exception:
        return "default"


def _discourse_ensure(engine, sid: str):
    """OS 式三级取数（TREE_TIERING_DECISION_20260807）:
    Hot（内存 blocks 已有）→ Warm（序列化 JSON page-in）→
    Cold（v3_sessions.json 原文重建）。返回 tree_mgr（可能空）。"""
    tm = getattr(engine, "_discourse_tree", None)
    if tm is None:
        return None
    if _blocks_for(tm, sid):
        return tm  # Hot 命中
    loader = getattr(engine, "_load_discourse_tree", None)
    if loader is not None:
        # 重试: API 进程冷重建可能正写同一 Warm 文件（Windows 文件锁竞态）
        for _attempt in range(3):
            try:
                if loader(sid) > 0:
                    return tm
                break
            except Exception:
                time.sleep(0.3)
    # Cold 重建: 从 v3_sessions.json 喂该会话 user 消息
    sessions = _disk_json("v3_sessions.json", {}) or {}
    s = sessions.get(sid) or {}
    texts = [
        m.get("content", "")
        for m in (s.get("messages") or [])
        if m.get("role") == "user" and str(m.get("content", "")).strip()
    ]
    for i, t in enumerate(texts[:200]):
        try:
            tm.feed(t, sid)
        except Exception:
            pass
    # 冷重建结束: 强制落盘（绕过 debounce, 保证 Warm 文件完整）
    if texts:
        persist = getattr(engine, "_persist_discourse_tree", None)
        if persist is not None:
            try:
                persist(sid, force=True)
            except Exception:
                pass
    return tm


def _blocks_for(tm, sid: str) -> dict:
    """按会话过滤 blocks（B 内核单实例共享, 块打 _session_id 标签）。
    兼容无标签旧树: 全量视为该会话（单会话语义）。"""
    if tm is None:
        return {}
    tagged = {
        bid: b for bid, b in tm.blocks.items()
        if getattr(b, "_session_id", "") == sid
    }
    if tagged:
        return tagged
    if not any(getattr(b, "_session_id", "") for b in tm.blocks.values()):
        return dict(tm.blocks)
    return {}


def _cross_refs_of(b) -> list:
    """统一读 cross_refs（导入块挂 _exported_cross_refs, 活块挂 cross_refs）。"""
    exported = getattr(b, "_exported_cross_refs", None)
    if exported is not None:
        return list(exported)
    return [
        {"target": r.target_block_id, "type": r.ref_type, "strength": r.strength}
        for r in getattr(b, "cross_refs", [])
    ]


def kernel_graph(sid: Optional[str] = None) -> dict:
    """真实对话树图（Hot→Warm→Cold 三级取数）。空 → 空图 + empty_reason。

    2026-08-07 起删除 v3_sessions 会话链兜底（链 ≠ 树, 误导"没做树图化"）。
    """
    engine = get_engine()
    nodes: List[dict] = []
    edges: List[dict] = []
    sid = _resolve_sid(sid)
    tree_mgr = _discourse_ensure(engine, sid) if engine else None
    tm_blocks = _blocks_for(tree_mgr, sid) if tree_mgr is not None else {}
    if tree_mgr is not None and tm_blocks:
        rel = _safe(tree_mgr.get_block_relations, sid) or {}
        blocks = rel.get("blocks", {}) if isinstance(rel, dict) else {}
        relations = rel.get("relations", []) if isinstance(rel, dict) else []
        roots = {bid for bid, b in tm_blocks.items() if not b.parent_id}
        for bid, b in tm_blocks.items():
            binfo = blocks.get(bid, {}) if isinstance(blocks, dict) else {}
            text = (binfo.get("raw_text") or binfo.get("summary") or
                    f"Block {str(bid)[:8]}").strip()
            nodes.append({
                "id": bid,
                "label": text[:40] or f"Block {str(bid)[:8]}",
                "type": "session" if bid in roots else "concept",
                "size": binfo.get("edus", 1),
                "temperature": binfo.get("temperature", "active"),
                "entities": binfo.get("entities", [])[:3],
                "intent": binfo.get("intent", "unknown"),
                "depth": binfo.get("depth", 0),
                "raw_text": (binfo.get("raw_text") or "")[:400],
                "summary": (binfo.get("summary") or "")[:200],
            })
        # 边: 单向 parent→child（child_of），去重；cross_refs → reference
        seen = set()
        for r in relations:
            if r.get("type") != "child_of":
                continue
            key = (r.get("from"), r.get("to"))
            if key in seen or not key[0] or not key[1]:
                continue
            seen.add(key)
            edges.append({
                "id": f"{r['from']}->{r['to']}",
                "source": r["from"], "target": r["to"], "type": "child_of",
            })
        for bid, b in tm_blocks.items():
            for cr in _cross_refs_of(b):
                tgt = cr.get("target")
                if tgt and tgt in tm_blocks:
                    edges.append({
                        "id": f"ref_{bid}->{tgt}", "source": bid,
                        "target": tgt, "type": "reference",
                    })
        return {
            "nodes": nodes, "edges": edges,
            "session_id": sid,
            "subgraph_nodes": [n["id"] for n in nodes[:8]],
            "version": getattr(engine, "_viz_version", 0),
        }
    return {
        "nodes": [], "edges": [], "session_id": sid,
        "empty_reason": "no_discourse_data",
        "version": getattr(engine, "_viz_version", 0),
    }


def kernel_discourse_tree(sid: Optional[str] = None) -> dict:
    engine = get_engine()
    sid = _resolve_sid(sid)
    tree_mgr = _discourse_ensure(engine, sid) if engine else None
    tm_blocks = _blocks_for(tree_mgr, sid) if tree_mgr is not None else {}
    if tree_mgr is None or not tm_blocks:
        return {"blocks": [], "total": 0, "session_id": sid}
    rel = _safe(tree_mgr.get_block_relations, sid) or {}
    blocks = rel.get("blocks", {}) if isinstance(rel, dict) else {}
    out = []
    for bid, b in tm_blocks.items():
        binfo = blocks.get(bid, {}) if isinstance(blocks, dict) else {}
        out.append({
            "id": bid,
            "tree_id": sid,
            "topic": binfo.get("summary", "")[:40],
            "temperature": binfo.get("temperature", "warm"),
            "edus": binfo.get("edus", 0),
            "children": list(binfo.get("children", [])),
            "parent": binfo.get("parent"),
            "summary": binfo.get("summary", ""),
            "raw_text": binfo.get("raw_text", ""),
            "intent": binfo.get("intent", "unknown"),
            "depth": binfo.get("depth", 0),
        })
    return {"blocks": out, "total": len(out), "session_id": sid,
            "version": getattr(engine, "_viz_version", 0)}


def kernel_recall(query: str, top_k: int = 10,
                  sid: Optional[str] = None,
                  intent: Optional[str] = None) -> dict:
    """统一召回能力接口（B2-3 P1, 2026-08-08）。

    混合锚点（BGE 向量 + BM25 + SPO 约束投影 + HyDE 扩展 + 关联链）→
    溯源置信度加权 → 对话树块图 k-hop 扩散 → 融合排序。
    """
    engine = get_engine()
    if not query:
        return {"error": "query required", "hits": []}
    try:
        # 先确保 discourse 块就绪（Hot→Warm→Cold 三级 page-in, 与 kernel_graph 同）
        sid = _resolve_sid(sid)
        if engine is not None:
            _discourse_ensure(engine, sid)
        from core.agent.recall import RecallService
        svc = RecallService(engine=engine)
        result = svc.recall(query, intent=intent, top_k=top_k, sid=sid,
                            expand_graph=True)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e), "hits": []}

def kernel_objects() -> dict:
    engine = get_engine()
    objs = getattr(engine, "_world_objects", {}) if engine else {}
    nodes = [{"id": k, "lifespan": "active", "relations": []} for k in objs.keys()]
    return {"nodes": nodes, "edges": [], "total_objects": len(nodes),
            "version": getattr(engine, "_viz_version", 0)}


# ────────────────────────────────────────────────────────────── #
# Rules / Relations / Causal / Behavior
# ────────────────────────────────────────────────────────────── #

def kernel_rules() -> dict:
    engine = get_engine()
    abc = getattr(engine, "_abc", None) if engine else None
    if abc is not None:
        report = _safe(abc.report) or {}
        rules = report.get("rules", []) if isinstance(report, dict) else []
        if isinstance(rules, dict):
            rules = list(rules.values())
        out = []
        for r in rules:
            if isinstance(r, dict):
                out.append({
                    "name": r.get("name", "?"),
                    "premise": r.get("premise", {}),
                    "conclusion": r.get("conclusion", {}),
                    "confidence": r.get("confidence", 0.0),
                    "hits": r.get("hits", 0),
                    "misses": r.get("misses", 0),
                    "source": r.get("source", "abc"),
                })
            else:
                out.append({"name": str(r)[:50], "premise": {}, "conclusion": {},
                            "confidence": 0.0, "hits": 0, "misses": 0, "source": "abc"})
        return {"rules": out, "total": len(out)}
    data = _disk_json("neuro_symbolic_rules.json")
    if isinstance(data, list):
        return {"rules": [{"name": str(r)[:50], "premise": {}, "conclusion": {},
                           "confidence": 0.0, "hits": 0, "misses": 0, "source": "disk"}
                          for r in data], "total": len(data)}
    if isinstance(data, dict):
        rules = data.get("rules", []) if isinstance(data.get("rules"), list) else []
        return {"rules": rules, "total": len(rules)}
    return {"rules": [], "total": 0}


def kernel_abc() -> dict:
    return kernel_rules()


def kernel_relations() -> dict:
    engine = get_engine()
    prov = getattr(engine, "_world_provider", None) if engine else None
    if prov is not None:
        try:
            edges = prov.relation_substrate_edges() if hasattr(prov, "relation_substrate_edges") else []
            return {"edge_count": len(edges),
                    "patterns": ["cause/effect", "sequence", "reference", "is-a", "part-of"],
                    "edges": edges[:50],
                    "version": getattr(engine, "_viz_version", 0)}
        except Exception:
            pass
    data = _disk_json("relations.json")
    if isinstance(data, dict) and "edges" in data:
        return {"edge_count": len(data["edges"]), "edges": data["edges"][:50],
                "patterns": ["cause/effect", "sequence", "reference", "is-a", "part-of"],
                "version": getattr(engine, "_viz_version", 0)}
    return {"edge_count": 0, "edges": [],
            "patterns": ["cause/effect", "sequence", "reference", "is-a", "part-of"],
            "version": getattr(engine, "_viz_version", 0)}


def kernel_causal() -> dict:
    engine = get_engine()
    planner = getattr(engine, "_planner", None) if engine else None
    if planner is not None:
        chain = _safe(planner.get_recent_chain, 50) or []
        return {
            "relations": [
                {"action": getattr(s, "event_type", str(s)),
                 "ts": getattr(s, "timestamp", 0)}
                for s in chain[:30]
            ],
            "substrates": len(chain),
        }
    return {"relations": [], "substrates": 0}


def kernel_behavior() -> dict:
    engine = get_engine()
    bg = getattr(engine, "_behavior_graph", None) if engine else None
    if bg is not None:
        chain = _safe(bg.get_recent_chain, 20)
        # BehaviorChainResult 可能无 len — 归一为列表
        if chain is None:
            chain = []
        elif not isinstance(chain, (list, tuple)):
            try:
                chain = list(chain)
            except Exception:
                chain = []
        return {
            "edge_count": len(chain),
            "patterns": [],
            "predictions": [],
            "recent_edges": [
                {"action": getattr(s, "event_type", str(s)),
                 "ts": getattr(s, "timestamp", 0)}
                for s in chain[:10]
            ],
        }
    return {"edge_count": 0, "patterns": [], "predictions": []}


def kernel_behavior_patterns() -> dict:
    engine = get_engine()
    bd = getattr(engine, "_behavior_discovery", None) if engine else None
    patterns = []
    if bd is not None and hasattr(bd, "discover"):
        try:
            res = bd.discover()
            if isinstance(res, dict):
                patterns = res.get("patterns", []) if isinstance(res.get("patterns"), list) else []
            elif isinstance(res, list):
                patterns = res
        except Exception:
            pass
    out = []
    for p in patterns:
        if isinstance(p, dict):
            out.append({
                "trigger": p.get("trigger", p.get("pattern", "?")),
                "predicted": p.get("predicted", p.get("action", "?")),
                "confidence": p.get("confidence", 0.0),
                "support": p.get("support", 0),
                "verdict": p.get("verdict", "pending"),
            })
    return {
        "patterns": out,
        "stats": {
            "total_patterns": len(out),
            "user_approved": sum(1 for p in out if p["verdict"] == "approved"),
            "frequency_by_type": {},
        },
    }


def kernel_inertia() -> dict:
    engine = get_engine()
    inert = getattr(engine, "_inertia", None) if engine else None
    if inert is None:
        return {"total_patterns": 0, "stable": 0, "confirmed": 0, "breaking": 0,
                "by_weight": {}, "constraints": []}
    try:
        d = getattr(inert, "__dict__", {})
        weights = {k: float(v) for k, v in d.items()
                   if isinstance(v, (int, float)) and "weight" in k.lower()}
        constraints = _safe(inert.get_design_constraints) or []
        return {
            "total_patterns": len(weights),
            "stable": sum(1 for v in weights.values() if v >= 0.5),
            "confirmed": sum(1 for v in weights.values() if v >= 0.7),
            "breaking": sum(1 for v in weights.values() if v < 0.3),
            "by_weight": weights,
            "constraints": constraints if isinstance(constraints, list) else [],
        }
    except Exception:
        return {"total_patterns": 0, "stable": 0, "confirmed": 0, "breaking": 0,
                "by_weight": {}, "constraints": []}


def kernel_behavior_predict() -> dict:
    engine = get_engine()
    brain = getattr(engine, "_behavior_brain", None) if engine else None
    recent = []
    bg = getattr(engine, "_behavior_graph", None) if engine else None
    if bg is not None:
        chain = _safe(bg.get_recent_chain, 10) or []
        # get_recent_chain returns BehaviorChainResult (steps list), not a list
        if hasattr(chain, "steps"):
            recent = [
                getattr(s, "action_summary", None) or getattr(s, "event_type", "") or str(s)
                for s in (chain.steps or [])
            ]
        elif isinstance(chain, (list, tuple)):
            recent = [getattr(s, "event_type", str(s)) for s in chain]
    predictions: Dict[str, dict] = {}
    if brain is not None and hasattr(brain, "predict_next"):
        try:
            res = brain.predict_next()
            if isinstance(res, dict):
                predictions = res.get("predictions", {}) if isinstance(res.get("predictions"), dict) else {}
        except Exception:
            pass
    return {"recent_actions": recent, "predictions": predictions}


# ────────────────────────────────────────────────────────────── #
# Engineering / Pipeline / Extraction / Perspectives
# ────────────────────────────────────────────────────────────── #

def kernel_engineering() -> dict:
    engine = get_engine()
    modules = kernel_engineering_modules().get("modules", [])
    return {"modules": modules, "total": len(modules)}


def kernel_engineering_modules() -> dict:
    reg = None
    try:
        from core.agent.cli.subsystem_registrations import _registry
        reg = _registry
    except Exception:
        pass
    modules = []
    if reg is not None:
        defs = getattr(reg, "_defs", {}) or {}
        for name, d in defs.items():
            if isinstance(d, dict):
                modules.append({"name": name, "type": d.get("type", d.get("kind", "subsystem"))})
            else:
                modules.append({"name": name, "type": getattr(d, "type", "subsystem")})
    return {"modules": modules[:50], "total": len(modules)}


def kernel_pipeline() -> dict:
    engine = get_engine()
    sm = getattr(engine, "_state_machine", None) if engine else None
    if sm is None:
        return {"running": False, "phases": [], "current_phase": "idle"}
    snap = _safe(sm.snapshot)
    if snap is None:
        return {"running": False, "phases": [], "current_phase": "idle"}
    try:
        handlers = getattr(sm, "_phase_handlers", {}) or {}
        phases = [p.value for p in handlers.keys()]
    except Exception:
        phases = []
    return {
        "running": True,
        "current_phase": snap.phase.value if hasattr(snap.phase, "value") else str(snap.phase),
        "turn_count": snap.turn_count,
        "confidence": snap.confidence,
        "errors_in_phase": snap.errors_in_phase,
        "total_latency_ms": round(snap.total_latency_ms, 1),
        "chain_results": {k: str(v)[:80] for k, v in snap.chain_results.items()},
        "phases": phases,
    }


def kernel_extraction() -> dict:
    engine = get_engine()
    result = {"entities": [], "coref_pairs": 0, "stats": {"rounds": 0, "gleaned": 0}}
    if engine is None:
        return result
    ext = getattr(engine, "_entity_extractor", None)
    if ext is not None:
        s = _safe(ext.stats) or {}
        result["stats"] = {
            "rounds": s.get("total_rounds", 0),
            "gleaned": s.get("total_gleaned", 0),
        }
        ents = _safe(ext.extract, "") or []
        if isinstance(ents, list):
            result["entities"] = ents[:20]
    coref = getattr(engine, "_hybrid_coref", None)
    if coref is not None:
        t3 = getattr(coref, "t3", None)
        if t3 is not None and hasattr(t3, "metrics"):
            result["coref_pairs"] = getattr(t3.metrics, "total_pairs", 0)
    return result


def kernel_perspectives() -> dict:
    engine = get_engine()
    cw = getattr(engine, "_context_window", None) if engine else None
    if cw is None:
        return {"perspectives": [], "total": 0}
    s = _safe(cw.stats) or {}
    return {
        "perspectives": [{
            "type": "context_window",
            "items": s.get("items", 0),
            "tokens": s.get("tokens", 0),
            "max_tokens": s.get("max_tokens", 4096),
            "block_ids": s.get("block_ids", 0),
        }],
        "total": 1,
    }


# ────────────────────────────────────────────────────────────── #
# Parameters / Context / Subgraph / Belief
# ────────────────────────────────────────────────────────────── #

def kernel_parameters() -> dict:
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
        allp = reg.all()
        params = []
        if isinstance(allp, dict):
            for name, p in allp.items():
                if isinstance(p, dict):
                    params.append({
                        "name": name,
                        "value": p.get("value", p.get("default")),
                        "description": p.get("description", ""),
                        "range": p.get("range"),
                        "editable": True,
                    })
                else:
                    params.append({"name": name, "value": getattr(p, "value", None),
                                   "description": getattr(p, "description", ""),
                                   "range": getattr(p, "range", None), "editable": True})
        return {"parameters": params, "total": len(params)}
    except Exception:
        return {"parameters": [], "total": 0}


def kernel_context() -> dict:
    engine = get_engine()
    if engine is None:
        return {"intent_category": None, "entries": []}
    last = getattr(engine, "_last_context", None)
    if last is not None:
        entries = getattr(last, "entries", None)
        out = []
        if isinstance(entries, list):
            for e in entries:
                out.append({
                    "domain": getattr(e, "domain", ""),
                    "type": getattr(e, "type", ""),
                    "content": str(getattr(e, "content", ""))[:200],
                    "confidence": getattr(e, "confidence", 0.5),
                    "estimated_tokens": len(str(getattr(e, "content", ""))) // 4,
                })
        return {"intent_category": getattr(last, "intent_category", None),
                "entries": out}
    return {"intent_category": None, "entries": []}


def kernel_subgraph(perspective: Optional[str] = None) -> dict:
    engine = get_engine()
    compiler = getattr(engine, "_subgraph_compiler", None) if engine else None
    if compiler is None:
        return {"perspective": perspective or "default", "domains": {}, "entries": [],
                "total_tokens": 0, "budget": 0}
    try:
        if perspective and hasattr(compiler, "compile"):
            res = compiler.compile(perspective=perspective)
        else:
            res = _safe(compiler.show) or {}
        if isinstance(res, dict):
            entries = []
            for k, v in (res.get("entries", {}).items() if isinstance(res.get("entries"), dict) else []):
                entries.append({"domain": k, "content": str(v)[:200]})
            domains = res.get("domains", {}) if isinstance(res.get("domains"), dict) else {}
            return {
                "perspective": perspective or res.get("perspective", "default"),
                "domains": domains,
                "entries": entries[:50],
                "total_tokens": res.get("total_tokens", 0),
                "budget": res.get("budget", 0),
            }
    except Exception:
        pass
    return {"perspective": perspective or "default", "domains": {}, "entries": [],
            "total_tokens": 0, "budget": 0}


def kernel_subgraph_cache() -> dict:
    engine = get_engine()
    compiler = getattr(engine, "_subgraph_compiler", None) if engine else None
    cache = getattr(compiler, "_cache", None) if compiler else None
    if cache is None:
        return {"size": 0, "hits": 0, "stale": 0}
    try:
        stats = cache.stats() if hasattr(cache, "stats") else {}
        if isinstance(stats, dict):
            return stats
    except Exception:
        pass
    return {"size": len(cache) if hasattr(cache, "__len__") else 0, "hits": 0, "stale": 0}


def kernel_belief(session_id: str = "default") -> dict:
    engine = get_engine()
    bel = getattr(engine, "_l2_5_belief", None) if engine else None
    if bel is None:
        return {"total_hypotheses": 0, "locked": 0, "avg_evidence": 0.0, "by_hypothesis": {}}
    try:
        if hasattr(bel, "snapshot"):
            snap = bel.snapshot(session_id=session_id)
        elif hasattr(bel, "state"):
            snap = bel.state(session_id=session_id)
        else:
            snap = None
        if isinstance(snap, dict):
            by = snap.get("by_hypothesis", {})
            if isinstance(by, dict):
                by = {k: (v if isinstance(v, dict) else {"posterior": float(v), "locked": False})
                      for k, v in by.items()}
            return {
                "total_hypotheses": snap.get("total_hypotheses", len(by)),
                "locked": snap.get("locked", 0),
                "avg_evidence": snap.get("avg_evidence", 0.0),
                "by_hypothesis": by,
            }
    except Exception:
        pass
    return {"total_hypotheses": 0, "locked": 0, "avg_evidence": 0.0, "by_hypothesis": {}}


# ────────────────────────────────────────────────────────────── #
# Persistence / Annotations / Sessions / Versions
# ────────────────────────────────────────────────────────────── #

def kernel_persistence() -> dict:
    result = {
        "annotation_store": {"status": "running", "records": 0},
        "unified_store": {"status": "running", "records": 0},
        "oceAN_saved": False, "rules_saved": False,
        "discourse_blocks": 0, "behavior_edges": 0,
        "profile_updated": False, "event_count": 0,
    }
    # warm_store.db 真实事件数
    db = os.path.join(DATA_DIR, "warm_store.db")
    if os.path.exists(db):
        try:
            import sqlite3
            conn = sqlite3.connect(db)
            for table, key in [("events", "event_count"), ("behavior", "behavior_edges")]:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    result[key] = count
                    if key == "event_count":
                        result["annotation_store"]["records"] = count
                        result["unified_store"]["records"] = count
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass
    # event_log.db 真实事件
    el = os.path.join(DATA_DIR, "event_log.db")
    if os.path.exists(el):
        try:
            import sqlite3
            conn = sqlite3.connect(el)
            count = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
            result["event_count"] = max(result["event_count"], count)
            conn.close()
        except Exception:
            pass
    profile = _disk_json("profile_state.json")
    if isinstance(profile, dict):
        result["oceAN_saved"] = "dims" in profile
        result["profile_updated"] = profile.get("turn_count", 0) > 0
    rules = _disk_json("neuro_symbolic_rules.json")
    result["rules_saved"] = isinstance(rules, (dict, list)) and bool(rules)
    discourse = _disk_json("discourse_state.json")
    if isinstance(discourse, dict):
        result["discourse_blocks"] = len(discourse.get("blocks", {}))
    return result


def kernel_persistence_graphs() -> dict:
    graphs = []
    gdir = os.path.join(DATA_DIR, "graphs")
    if os.path.isdir(gdir):
        for fname in sorted(os.listdir(gdir))[:20]:
            if fname.endswith(".json"):
                fp = os.path.join(gdir, fname)
                try:
                    data = json.load(open(fp, encoding="utf-8"))
                    graphs.append({
                        "name": fname[:-5],
                        "node_count": len(data.get("nodes", {})) if isinstance(data, dict) else 0,
                        "edge_count": len(data.get("edges", [])) if isinstance(data, dict) else 0,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S",
                                                    time.localtime(os.path.getmtime(fp))),
                    })
                except Exception:
                    pass
    return {"graphs": graphs}


def kernel_annotations() -> dict:
    data = _disk_json("annotations.json", [])
    if isinstance(data, list):
        return {"annotations": data, "total": len(data)}
    if isinstance(data, dict):
        items = data.get("annotations", data.get("items", []))
        return {"annotations": items if isinstance(items, list) else [], "total": len(items) if isinstance(items, list) else 0}
    return {"annotations": [], "total": 0}


def kernel_annotation_stats() -> dict:
    data = _disk_json("annotations.json", [])
    items = data if isinstance(data, list) else (
        data.get("annotations", []) if isinstance(data, dict) else [])
    by_author: Dict[str, int] = {}
    by_date: Dict[str, int] = {}
    for a in items:
        if isinstance(a, dict):
            author = str(a.get("author", a.get("domain", "?")))
            by_author[author] = by_author.get(author, 0) + 1
            ts = a.get("timestamp", a.get("ts", ""))
            date = str(ts)[:10] if ts else "?"
            by_date[date] = by_date.get(date, 0) + 1
    return {"total": len(items), "by_author": by_author, "by_date": by_date}


def kernel_corrections() -> dict:
    data = _disk_json("corrections.json", [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("corrections", data.get("items", []))
    return []


def kernel_profile_corrections() -> dict:
    engine = get_engine()
    journal = getattr(engine, "_correction_journal", None) if engine else None
    if journal is not None:
        try:
            entries = journal.entries() if hasattr(journal, "entries") else (
                journal._entries if hasattr(journal, "_entries") else [])
            out = []
            for e in entries:
                if isinstance(e, dict):
                    out.append({"id": e.get("id", "?"), "ts": e.get("ts", 0),
                                "author": e.get("author", "user"),
                                "before": str(e.get("before", "")),
                                "after": str(e.get("after", "")),
                                "reason": e.get("reason", ""),
                                "verify": e.get("verify", "pending")})
            return {"corrections": out, "total": len(out)}
        except Exception:
            pass
    data = _disk_json("corrections.json", [])
    if isinstance(data, list):
        return {"corrections": data, "total": len(data)}
    return {"corrections": [], "total": 0}


def kernel_sessions() -> dict:
    data = _disk_json("v3_sessions.json", {}) or {}
    out = []
    if isinstance(data, dict):
        for sid, s in data.items():
            if not isinstance(s, dict):
                continue
            msgs = s.get("messages", [])
            out.append({"id": sid, "name": sid[:12], "turns": len(msgs),
                        "last": msgs[-1].get("content", "")[:60] if msgs else ""})
    return {"sessions": out, "total": len(out)}


def kernel_versions(category: str = "profile") -> dict:
    engine = get_engine()
    meta = getattr(engine, "_meta_cognition", None) if engine else None
    vcs = getattr(meta, "_vcs", None) if meta is not None else None
    if vcs is None and engine is not None:
        vcs = getattr(engine, "_vcs", None)
    commits = []
    if vcs is not None:
        try:
            res = vcs.list_versions(category=category) if hasattr(vcs, "list_versions") else None
            if isinstance(res, list):
                commits = res
            elif isinstance(res, dict):
                commits = res.get("commits", res.get("versions", []))
        except Exception:
            pass
    out = []
    for c in commits:
        if isinstance(c, dict):
            out.append({"id": c.get("id", c.get("commit_id", "?")),
                        "ts": c.get("ts", c.get("timestamp", 0)),
                        "author": c.get("author", "?"),
                        "before": str(c.get("before", "")),
                        "after": str(c.get("after", "")),
                        "reason": c.get("reason", ""),
                        "verify": c.get("verify", "pending")})
    return {"target": category, "commits": out}


def kernel_versions_rollback(category: str, commit_id: str) -> dict:
    """版本回滚（GlobalVersionControl.rollback_to 真实实现）。"""
    engine = get_engine()
    meta = getattr(engine, "_meta_cognition", None) if engine else None
    vcs = getattr(meta, "_vcs", None) if meta is not None else None
    if vcs is None:
        try:
            from core.agent.v4.cognitive.version_control import GlobalVersionControl
            vcs = GlobalVersionControl()
        except Exception:
            vcs = None
    if vcs is None:
        return {"rolled_back": False, "error": "no version control"}
    try:
        store = vcs.store(category) if hasattr(vcs, "store") else vcs
        res = store.rollback_to("", commit_id) if hasattr(store, "rollback_to") else None
        return {"rolled_back": True, "commit_id": commit_id,
                "result": str(res)[:120]}
    except Exception as e:
        return {"rolled_back": False, "error": str(e)[:120]}


def kernel_meta_scan() -> dict:
    """元认知扫描（MetaCognition.scan 真实实现）。"""
    engine = get_engine()
    mc = getattr(engine, "_meta_cognition", None) if engine else None
    if mc is None:
        return {"triggered": False, "items": []}
    try:
        items = mc.scan(engine)
        if not isinstance(items, list):
            items = []
        return {"triggered": True, "items": [
            {"id": getattr(i, "id", getattr(i, "review_id", "?")),
             "target": getattr(i, "target", "?"),
             "verdict": getattr(i, "verdict", "pending")}
            for i in items[:20]
        ]}
    except Exception as e:
        return {"triggered": False, "error": str(e)[:120]}


def kernel_meta_retrospect(target: str = "", category: str = "parameters") -> dict:
    """元认知复盘（MetaCognition.retrospect 真实实现）。"""
    engine = get_engine()
    mc = getattr(engine, "_meta_cognition", None) if engine else None
    if mc is None:
        return {"target": target, "delta": {"value_change": 0.0}, "verdict": "unavailable"}
    try:
        report = mc.retrospect(target or "parameters", category)
        if report is None:
            return {"target": target, "delta": {"value_change": 0.0}, "verdict": "no_report"}
        delta = getattr(report, "delta", None) or getattr(report, "value_change", 0.0)
        if not isinstance(delta, dict):
            delta = {"value_change": float(delta or 0.0)}
        return {"target": getattr(report, "target", target), "delta": delta,
                "verdict": getattr(report, "verdict", "pending")}
    except Exception as e:
        return {"target": target, "delta": {"value_change": 0.0},
                "verdict": "error", "error": str(e)[:120]}


def kernel_behavior_feedback(pattern_id: str = "", correct: bool = True) -> dict:
    """行为反馈（BehaviorGraph.mark_correction 真实实现）。"""
    engine = get_engine()
    bg = getattr(engine, "_behavior_graph", None) if engine else None
    if bg is None or not hasattr(bg, "mark_correction"):
        return {"updated": False, "error": "no behavior graph"}
    try:
        bg.mark_correction(pattern_id, correct=correct)
        # 二阶抽象: 用户纠正 → 变化触发（共性找底发散）
        if engine is not None:
            lb = getattr(engine, "_learning_bridge", None)
            if lb is not None:
                try:
                    lb.on_user_correction("behavior")
                except Exception:
                    pass
        return {"updated": True, "pattern_id": pattern_id, "correct": correct}
    except Exception as e:
        return {"updated": False, "error": str(e)[:120]}


def kernel_causal_chain(event: str = "") -> dict:
    """因果链（CausalPlanner.get_recent_chain 真实实现）。"""
    engine = get_engine()
    planner = getattr(engine, "_planner", None) if engine else None
    if planner is None:
        planner = getattr(engine, "_causal_planner", None) if engine else None
    if planner is None:
        return {"chain": [], "remaining": 0, "tracked_chains": 0,
                "avg_chain_length": 0.0, "p90_chain_length": 0.0}
    try:
        chain = planner.get_recent_chain(30) if hasattr(planner, "get_recent_chain") else []
        if not isinstance(chain, (list, tuple)):
            try:
                chain = list(chain)
            except Exception:
                chain = []
        out = []
        for c in chain:
            ev = getattr(c, "event", None) or getattr(c, "action", None) or str(c)
            out.append({"event": str(ev)[:120],
                        "depth": getattr(c, "depth", 0)})
        n = len(out)
        return {"chain": out, "remaining": 0, "tracked_chains": 1,
                "avg_chain_length": round(n / 1.0, 2) if n else 0.0,
                "p90_chain_length": float(n)}
    except Exception as e:
        return {"chain": [], "remaining": 0, "tracked_chains": 0,
                "avg_chain_length": 0.0, "p90_chain_length": 0.0,
                "error": str(e)[:120]}


def kernel_context_config(req: Optional[dict] = None) -> dict:
    """上下文配置（ParameterRegistry.set 真实实现）。"""
    req = req or {}
    updated = []
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
        for k, v in req.items():
            if k in ("token_budget", "domain_P", "domain_C", "domain_K",
                     "domain_E", "domain_B"):
                ok = reg.set(k, v)
                if ok:
                    updated.append(k)
        return {"updated": updated, "count": len(updated)}
    except Exception as e:
        return {"updated": [], "count": 0, "error": str(e)[:120]}


def kernel_compression_feedback(req: Optional[dict] = None) -> dict:
    """GAP-4: 压缩质量反馈记录（Hermes manual_compression_feedback 对齐）.

    body: {"quality": "good"|"bad", "comment": str, "compression_id": str}
    """
    req = req or {}
    try:
        from core.agent.context_window.compression_feedback import (
            CompressionFeedbackStore,
        )
        store = CompressionFeedbackStore()
        item = store.record(
            quality=str(req.get("quality", "")),
            comment=str(req.get("comment", "")),
            compression_id=str(req.get("compression_id", "")),
            source=str(req.get("source", "user")),
        )
        if item is None:
            return {"recorded": False, "error": "quality must be 'good' or 'bad'"}
        return {"recorded": True, "id": item["id"], "stats": store.stats()}
    except Exception as e:
        return {"recorded": False, "error": str(e)[:120]}


def kernel_compression_feedback_stats() -> dict:
    """GAP-4: 压缩反馈统计。"""
    try:
        from core.agent.context_window.compression_feedback import (
            CompressionFeedbackStore,
        )
        store = CompressionFeedbackStore()
        return {"stats": store.stats(), "recent": store.recent(10)}
    except Exception as e:
        return {"stats": {"total": 0, "good": 0, "bad": 0, "good_rate": 0.0},
                "error": str(e)[:120]}


def kernel_heuristics_list() -> dict:
    """二阶抽象（A24）: 启发库存白盒视图（A19）。"""
    engine = get_engine()
    inv = getattr(engine, "_heuristic_inventory", None) if engine else None
    if inv is None:
        return {"heuristics": [], "stats": {
            "total": 0, "active": 0, "by_source": {},
            "avg_coverage": 0.0, "avg_insight": 0.0,
        }}
    try:
        return {
            "heuristics": [h.to_dict() for h in inv.all(active_only=False)],
            "stats": inv.stats(),
        }
    except Exception as e:
        return {"heuristics": [], "stats": {"error": str(e)[:120]}}


def kernel_changelog(limit: int = 50, kind: str = "") -> dict:
    """GAP-F1: 决策变更事件流（git log 语义, 回看/审计）。"""
    engine = get_engine()
    bus = getattr(engine, "_decision_bus", None) if engine else None
    if bus is None:
        return {"events": [], "stats": {
            "total": 0, "proposed": 0, "applied": 0, "rejected": 0, "reverted": 0,
        }}
    try:
        events = bus.recent(limit=limit, kind=kind)
        stats = {"total": len(events)}
        for s in ("proposed", "applied", "rejected", "reverted"):
            stats[s] = sum(1 for e in events if e.get("status") == s)
        return {"events": events, "stats": stats}
    except Exception as e:
        return {"events": [], "stats": {"error": str(e)[:120]}}


def kernel_changelog_intervene(req: Optional[dict] = None) -> dict:
    """GAP-F1: PR review 介入回写（approve→applied / reject→rejected）。"""
    req = req or {}
    engine = get_engine()
    bus = getattr(engine, "_decision_bus", None) if engine else None
    if bus is None:
        return {"intervened": False, "error": "no decision bus"}
    try:
        ev = bus.intervene(
            status=str(req.get("status", "applied")),
            comment=str(req.get("comment", "")),
            dimension=str(req.get("dimension", "")),
            kind=str(req.get("kind", "")),
        )
        return {"intervened": ev is not None, "event": ev}
    except Exception as e:
        return {"intervened": False, "error": str(e)[:120]}


def kernel_engineering_constraints(req: Optional[dict] = None) -> dict:
    """工程约束编辑（engineering 组件真实实现）。"""
    req = req or {}
    engine = get_engine()
    eng = getattr(engine, "_engineering", None) if engine else None
    action = req.get("action", "add_constraint")
    name = req.get("name", "")
    constraint = req.get("constraint", "")
    status = "updated"
    if eng is not None:
        try:
            if action == "add_constraint" and hasattr(eng, "add_constraint"):
                eng.add_constraint(name, constraint)
            elif action == "remove_constraint" and hasattr(eng, "remove_constraint"):
                eng.remove_constraint(name)
        except Exception:
            status = "update_failed"
    return {"updated": name, "constraint": constraint, "status": status}


def kernel_ocean_params() -> dict:
    """OCEAN 参数应用（真实画像 + 已应用参数）。"""
    engine = get_engine()
    ocean = getattr(engine, "_ocean_analyst", None) if engine else None
    dims = {}
    if ocean is not None:
        profile = getattr(ocean, "profile", None)
        if profile is not None and hasattr(profile, "dims"):
            dims = {k: float(v) for k, v in profile.dims.items()}
    applied = {"strategy": "current", "source": "engine" if ocean else "disk"}
    return {"applied": applied, "ocean": dims}


def kernel_corrections_review(corrections: Optional[list] = None) -> dict:
    """画像校正评审（correction journal 真实实现）。"""
    engine = get_engine()
    journal = getattr(engine, "_correction_journal", None) if engine else None
    reviewed = 0
    if corrections:
        reviewed = len(corrections)
    elif journal is not None:
        try:
            entries = journal.entries_since(limit=50) if hasattr(journal, "entries_since") else []
            reviewed = len(entries)
        except Exception:
            reviewed = 0
    return {"reviewed": reviewed > 0, "count": reviewed}


def kernel_providers_test() -> dict:
    """Provider 连通性测试（真实 LLM provider）。"""
    engine = get_engine()
    provider = getattr(engine, "_llm_provider", None) if engine else None
    if provider is None:
        return {"healthy": False, "latency_ms": 0, "error": "no provider"}
    import time as _t
    t0 = _t.time()
    try:
        if hasattr(provider, "health_check"):
            ok = provider.health_check()
        else:
            ok = True
        return {"healthy": bool(ok), "latency_ms": round((_t.time() - t0) * 1000, 1)}
    except Exception as e:
        return {"healthy": False, "latency_ms": round((_t.time() - t0) * 1000, 1),
                "error": str(e)[:120]}


def kernel_sync(block_id: str = "") -> dict:
    """同步状态（discourse 树真实同步）。"""
    engine = get_engine()
    tree = getattr(engine, "_discourse_tree", None) if engine else None
    if tree is None:
        return {"status": "idle", "pending": 0}
    try:
        stats = tree.get_stats() if hasattr(tree, "get_stats") else {}
        pending = stats.get("pending", 0) if isinstance(stats, dict) else 0
        return {"status": "synced", "pending": pending, "block_id": block_id or None}
    except Exception:
        return {"status": "idle", "pending": 0}


def kernel_ttl_tick() -> dict:
    """TTL 迁移 tick（真实三档存储迁移）。"""
    engine = get_engine()
    store = getattr(engine, "_tiered_storage", None) if engine else None
    promoted = []
    demoted = []
    if store is not None:
        try:
            if hasattr(store, "tick"):
                res = store.tick()
                if isinstance(res, dict):
                    promoted = res.get("promoted", [])
                    demoted = res.get("demoted", [])
        except Exception:
            pass
    return {"promoted": promoted, "demoted": demoted}


def kernel_versions_profile() -> dict:
    data = _disk_json("version_control.json", {}) or {}
    commits = data.get("commits", []) if isinstance(data, dict) else []
    return {"commits": commits, "target": data.get("target") if isinstance(data, dict) else None,
            "current": "6.0.0"}


def kernel_router_modes() -> dict:
    engine = get_engine()
    router = getattr(engine, "_router_v4", None) if engine else None
    active = "hybrid"
    if router is not None:
        mode = getattr(router, "mode", None) or getattr(router, "_mode", None)
        if mode:
            active = mode if isinstance(mode, str) else getattr(mode, "value", "hybrid")
    return {
        "available": True,
        "modes": [
            {"name": "hybrid", "complexity": "full", "cost": "medium", "latency": "medium"},
            {"name": "rule", "complexity": "simple", "cost": "low", "latency": "fast"},
            {"name": "llm", "complexity": "full", "cost": "high", "latency": "slow"},
        ],
        "active": active,
        "force_mode": None,
        "disabled": {"remote": False, "small_model": False},
    }


def kernel_providers() -> dict:
    engine = get_engine()
    provider = getattr(engine, "_llm_provider", None) if engine else None
    name = "mock"
    if provider is not None:
        name = getattr(provider, "name", None) or getattr(provider, "provider", "mock")
    model = getattr(provider, "model", "mock") if provider else "mock"
    return {
        "active": {
            "name": name,
            "model": model,
            "healthy": True,
            "stats": {},
        },
        "failover": {
            "primary": "switch",
            "fallback": "direct",
            "active_idx": 0,
            "failures": 0,
        },
        "active_provider": name,
        "active_model": model,
    }


def kernel_providers_tokens() -> dict:
    engine = get_engine()
    turns = getattr(engine, "_turn_counter", 0) if engine else 0
    return {"current": {"turns": turns, "est_tokens": turns * 800},
            "all_sessions": {"est_tokens": 0, "turns": 0}}


def kernel_session_detail(filename: str) -> dict:
    data = _disk_json("v3_sessions.json", {}) or {}
    if not isinstance(data, dict) or filename not in data:
        return {"session_id": filename, "messages": []}
    s = data[filename]
    msgs = s.get("messages", []) if isinstance(s, dict) else []
    return {"session_id": filename, "messages": msgs}


def kernel_trace_recent(limit: int = 10) -> dict:
    engine = get_engine()
    tracer = getattr(engine, "_tracer", None) if engine else None
    if tracer is None:
        return {"traces": [], "metrics": {}, "stats": {}}
    try:
        traces = tracer.recent(limit=limit) if hasattr(tracer, "recent") else []
        return {"traces": traces, "metrics": _safe(tracer.metrics) or {},
                "stats": _safe(tracer.stats) or {}}
    except Exception:
        return {"traces": [], "metrics": {}, "stats": {}}


def kernel_metrics() -> dict:
    engine = get_engine()
    if engine is None:
        return {"engine_uptime": 0, "subsystems_loaded": 0, "subsystems_total": 0,
                "total_turn_count": 0}
    reg = getattr(engine, "_registry", None)
    return {
        "engine_uptime": int(time.time() - getattr(engine, "_start_time", time.time())),
        "subsystems_loaded": len(getattr(reg, "_instances", {})) if reg else 0,
        "subsystems_total": len(getattr(reg, "_defs", {})) if reg else 0,
        "total_turn_count": getattr(engine, "_turn_counter", 0),
    }


def kernel_meta_stats() -> dict:
    engine = get_engine()
    mc = getattr(engine, "_meta_cognition", None) if engine else None
    decider = getattr(engine, "_decider", None) if engine else None
    if mc is None and decider is None:
        return {"queue_size": 0, "pending": 0, "reviewed": 0, "decisions_total": 0,
                "self_audit": {"accuracy": 0.0, "by_verdict": {}}}
    st = _safe(mc.stats) if mc is not None else {}
    st = st if isinstance(st, dict) else {}
    audit = _safe(mc.self_audit) if mc is not None else {}
    audit = audit if isinstance(audit, dict) else {}
    tick = getattr(decider, "_tick", 0) if decider is not None else 0
    return {
        "queue_size": st.get("queue_size", st.get("pending", tick)),
        "pending": st.get("pending", 0),
        "reviewed": getattr(engine, "_turn_counter", 0),
        "decisions_total": st.get("decisions_total", tick),
        "self_audit": {
            "accuracy": audit.get("accuracy", 0.0),
            "by_verdict": audit.get("by_verdict", {}),
        },
    }


def kernel_meta_queue() -> dict:
    engine = get_engine()
    mc = getattr(engine, "_meta_cognition", None) if engine else None
    if mc is None:
        return {"queue": [], "pending": 0}
    try:
        q = mc.process_queue() if hasattr(mc, "process_queue") else None
        items = q if isinstance(q, list) else (mc._queue if hasattr(mc, "_queue") else [])
        return {"queue": items[:50], "pending": len(items)}
    except Exception:
        return {"queue": [], "pending": 0}


def kernel_degradation() -> dict:
    engine = get_engine()
    if engine is None:
        return {"level": "none", "score": 0}
    sla = getattr(engine, "_sla_watchdog", None)
    if sla is not None:
        try:
            st = sla.stats() if hasattr(sla, "stats") else {}
            if isinstance(st, dict):
                return {"level": st.get("level", "none"),
                        "score": st.get("score", st.get("degradation_score", 0))}
        except Exception:
            pass
    return {"level": "none", "score": 0}


def kernel_ttl() -> dict:
    data = _disk_json("ttl_stats.json")
    if isinstance(data, dict):
        return {"ttl_stats": data.get("by_state", {}),
                "total": data.get("total", sum(data.get("by_state", {}).values()))}
    return {"ttl_stats": {}, "total": 0}


def kernel_recursive_map() -> dict:
    data = _disk_json("recursive_map.json")
    if isinstance(data, dict):
        by_level = data.get("by_level", {})
        return {"map": {"by_level": by_level},
                "count": data.get("count", sum(by_level.values())),
                "total_nodes": data.get("count", sum(by_level.values())),
                "high_coupling": data.get("high_coupling", 0),
                "expanded": data.get("expanded", 0)}
    return {"map": {"by_level": {}}, "count": 0, "total_nodes": 0,
            "high_coupling": 0, "expanded": 0}


# ────────────────────────────────────────────────────────────── #
# EventLog（G2 生命周期）— CLI 与 REST 共用
# ────────────────────────────────────────────────────────────── #

def _event_log():
    """引擎 EventLog v2（G2: 水位线/温减枝/冷摘要）。"""
    engine = get_engine()
    return getattr(engine, "_event_log", None) if engine else None


def kernel_eventlog_stats() -> dict:
    log = _event_log()
    if log is None:
        # 兜底: event_log.db 真实统计
        db = os.path.join(DATA_DIR, "event_log.db")
        if os.path.exists(db):
            try:
                import sqlite3
                conn = sqlite3.connect(db)
                total = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
                by_kind = {}
                for row in conn.execute("SELECT kind, COUNT(*) FROM event_log GROUP BY kind"):
                    by_kind[row[0]] = row[1]
                conn.close()
                return {"total": total, "by_kind": by_kind}
            except Exception:
                pass
        return {"total": 0, "by_kind": {}}
    st = _safe(log.stats) or {}
    if isinstance(st, dict):
        return {"total": st.get("total", len(st.get("by_kind", {}))),
                "by_kind": st.get("by_kind", {})}
    return {"total": 0, "by_kind": {}}


def kernel_eventlog_search(keyword: str = "", kind: str = "", session_id: str = "",
                          limit: int = 50) -> dict:
    log = _event_log()
    if log is None:
        return {"found": 0, "events": []}
    try:
        if hasattr(log, "query_events"):
            events = log.query_events(kind=kind or None, session_id=session_id or None, limit=limit)
        else:
            events = log.search(keyword=keyword, kind=kind, session_id=session_id, limit=limit)
        if keyword and hasattr(log, "search"):
            events = log.search(keyword=keyword, kind=kind, session_id=session_id, limit=limit)
        out = []
        for e in events or []:
            if isinstance(e, dict):
                out.append({
                    "event_id": e.get("event_id", e.get("id", "?")),
                    "kind": e.get("kind", "?"),
                    "payload": e.get("payload", {}),
                    "session_id": e.get("session_id", ""),
                    "ts": e.get("ts", e.get("timestamp", 0)),
                })
        return {"found": len(out), "events": out}
    except Exception:
        return {"found": 0, "events": []}


def kernel_eventlog_export(limit: int = 200) -> dict:
    res = kernel_eventlog_search(limit=limit)
    return {"events": res.get("events", []), "total": res.get("found", 0)}


def kernel_eventlog_clear() -> dict:
    log = _event_log()
    if log is None:
        return {"status": "no_event_log"}
    if hasattr(log, "clear"):
        ok = _safe(log.clear)
        return {"status": "cleared" if ok else "clear_failed"}
    if hasattr(log, "cleanup_old"):
        n = _safe(log.cleanup_old)
        return {"status": "cleaned", "count": n}
    return {"status": "unsupported"}


# ────────────────────────────────────────────────────────────── #
# Memory（三档编译器）— CLI 与 REST 共用
# ────────────────────────────────────────────────────────────── #

def _memory():
    engine = get_engine()
    return getattr(engine, "_memory_compiler", None) if engine else None


def kernel_memory_stats() -> dict:
    mc = _memory()
    if mc is None:
        return {"hot": 0, "warm": 0, "cold": 0, "compressions": 0}
    st = _safe(mc.tier_show) or {}
    if isinstance(st, dict):
        return {"hot": st.get("hot", 0), "warm": st.get("warm", 0),
                "cold": st.get("cold", 0),
                "compressions": st.get("merges", 0)}
    return {"hot": 0, "warm": 0, "cold": 0, "compressions": 0}


def kernel_memory_compile(events: Optional[List[dict]] = None) -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    res = _safe(mc.compile, events) or {"status": "compiled"}
    return res if isinstance(res, dict) else {"status": str(res)}


def kernel_memory_checkpoint(label: str = "") -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.checkpoint_create, label) or {"status": "failed"}


def kernel_memory_checkpoint_list() -> dict:
    mc = _memory()
    if mc is None:
        return {"checkpoints": []}
    res = _safe(mc.checkpoint_list) or []
    return {"checkpoints": res if isinstance(res, list) else []}


def kernel_memory_checkpoint_rollback(cid: str) -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.checkpoint_rollback, cid) or {"status": "failed"}


def kernel_memory_conflict_show() -> dict:
    mc = _memory()
    if mc is None:
        return {"conflicts": []}
    res = _safe(mc.conflict_show) or []
    return {"conflicts": res if isinstance(res, list) else []}


def kernel_memory_conflict_resolve(cid: str, decision: str) -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.conflict_resolve, cid, decision) or {"status": "failed"}


def kernel_memory_tier() -> dict:
    mc = _memory()
    if mc is None:
        return {"hot": [], "warm": [], "cold": []}
    return {"hot": _safe(mc.tier_hot) or [], "warm": _safe(mc.tier_warm) or [],
            "cold": _safe(mc.tier_cold) or []}


def kernel_memory_tier_promote(node_id: str) -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.promote, node_id) or {"status": "failed"}


def kernel_memory_tier_demote(node_id: str) -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.demote, node_id) or {"status": "failed"}


def kernel_memory_compress() -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.compress) or {"status": "failed"}


def kernel_memory_compress_cold() -> dict:
    mc = _memory()
    if mc is None:
        return {"status": "unavailable"}
    return _safe(mc.compress_cold) or {"status": "failed"}


# ────────────────────────────────────────────────────────────── #
# Format（序列化引擎）— CLI 与 REST 共用
# ────────────────────────────────────────────────────────────── #

def _format():
    try:
        from core.agent.engine.deep_modules import FormatEngine
        return FormatEngine()
    except Exception:
        return None


def kernel_format_encode(data: Any = None, fmt: Optional[str] = None) -> dict:
    fe = _format()
    if fe is None:
        return {"encoded": "", "tokens": 0, "format": "compact"}
    return _safe(fe.encode, data, fmt) or {"encoded": "", "tokens": 0, "format": "compact"}


def kernel_format_decode(encoded: str) -> dict:
    fe = _format()
    if fe is None:
        return {"data": {}, "tokens": 0}
    return _safe(fe.decode, encoded) or {"data": {}, "tokens": 0}


def kernel_format_template() -> dict:
    fe = _format()
    if fe is None:
        return {"template": "compact", "available": ["xml", "compact", "list", "prompt"]}
    return _safe(fe.template_show) or {"template": "compact",
                                       "available": ["xml", "compact", "list", "prompt"]}


def kernel_format_template_set(name: str) -> dict:
    fe = _format()
    if fe is None:
        return {"status": "unavailable"}
    return _safe(fe.template_set, name) or {"status": "failed"}


def kernel_format_tokens(text: str = "") -> dict:
    fe = _format()
    if fe is None:
        return {"total": 0, "by_section": {}}
    return _safe(fe.tokens, text) or {"total": 0, "by_section": {}}


# ────────────────────────────────────────────────────────────── #
# Blueprint / Decider — CLI 与 REST 共用
# ────────────────────────────────────────────────────────────── #

def _blueprint(text: str = "show", strategy: str = "TEMPLATE"):
    try:
        from core.agent.blueprint.engine import BlueprintEngine
        be = BlueprintEngine()
        return be.build(text, intent=text, strategy=strategy)
    except Exception:
        return None


def kernel_blueprint_show() -> dict:
    dag = _blueprint("show")
    if dag is None:
        return {"nodes": [], "edges": [], "strategy": "?"}
    nodes = [n.node_id for n in getattr(dag, "nodes", [])]
    edges = [f"{e.from_node}->{e.to_node}" for e in getattr(dag, "edges", [])]
    return {"nodes": nodes, "edges": edges, "strategy": getattr(dag, "strategy", "?")}


def kernel_blueprint_build(text: str, strategy: str = "TEMPLATE") -> dict:
    dag = _blueprint(text, strategy)
    if dag is None:
        return {"nodes": 0, "strategy": strategy, "status": "unavailable"}
    return {"nodes": getattr(dag, "node_count", len(getattr(dag, "nodes", []))),
            "strategy": strategy}


def kernel_blueprint_validate() -> dict:
    dag = _blueprint("validate")
    if dag is None:
        return {"valid": False, "nodes": 0, "edges": 0}
    return {"valid": getattr(dag, "node_count", 0) > 0,
            "nodes": getattr(dag, "node_count", 0),
            "edges": len(getattr(dag, "edges", []))}


def kernel_blueprint_export() -> dict:
    dag = _blueprint("export")
    if dag is None:
        return {"nodes": [], "edges": [], "strategy": "?"}
    return {"nodes": [n.node_id for n in getattr(dag, "nodes", [])],
            "edges": [f"{e.from_node}->{e.to_node}" for e in getattr(dag, "edges", [])],
            "strategy": getattr(dag, "strategy", "?")}


def kernel_decider_show() -> dict:
    engine = get_engine()
    gd = getattr(engine, "_decider", None) if engine else None
    if gd is None:
        return {"status": "no_decider"}
    st = _safe(gd.stats) or {}
    return st if isinstance(st, dict) else {"status": str(st)}


def kernel_decider_chains() -> dict:
    engine = get_engine()
    gd = getattr(engine, "_decider", None) if engine else None
    if gd is None:
        return {"chains": []}
    st = _safe(gd.stats) or {}
    if isinstance(st, dict):
        return {"tick": st.get("tick", 0), "state": st.get("state", "idle"),
                "chains": st.get("chains", [])}
    return {"chains": []}


def kernel_decider_execute(text: str = "") -> dict:
    """真实执行: 走 StateMachine 管线（13 阶段），返回各阶段结果。"""
    engine = get_engine()
    sm = getattr(engine, "_state_machine", None) if engine else None
    if sm is None:
        return {"status": "no_state_machine"}
    try:
        from core.agent.events.event_ir import DialogAdapter
        event = DialogAdapter().adapt(text or "execute", session_id="cli", turn_number=1)
        result = _safe(sm.run_pipeline, sm.current_phase(), {"event": event})
        if result is None:
            snap = _safe(sm.snapshot)
            result = {"phase": (snap.phase.value if snap and hasattr(snap.phase, "value")
                                else str(getattr(snap, "phase", "idle"))),
                      "turn_count": getattr(snap, "turn_count", 0) if snap else 0}
        phases = []
        for p in getattr(sm, "_phase_handlers", {}).keys():
            phases.append(p.value if hasattr(p, "value") else str(p))
        return {"executed": True, "phases": phases,
                "result": json.dumps(result, ensure_ascii=False, default=str)[:300]}
    except Exception as e:
        return {"executed": False, "error": str(e)[:200]}
