"""Visualization Interaction API — user-editable graph/tree/object/relation (B5-3).

Design principle: 白盒化 — every graph node, tree block, concept edge
is user-visible AND user-editable. Modifications are journaled (A17) and
feed back into Mind learning + ABC rule refinement.

This closes the IR loop: IR is not just a data format, it's the editable
intermediate representation between raw observations and LLM context.

M2 (2026-08-04) — 白盒编辑后端:
  * /v6/edit/revert  — 恢复端点: 读 journal before → 应用回滚 (B5-3-P2)
  * /v6/edit/mode    — 三档模式开关: smart / whitebox / fullwhite (B5-3-P5)
  * /v6/edit/journal — 白盒检查: 全部修正记录 (A19/A17)
  * 5 端点 journal 结构化 before/after → revert 可精确回滚
  * 引擎白盒状态懒初始化 (_init_whitebox) — 无引擎时 503, 无数据 404
"""
import json, os, time, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/edit")
_engine = None

# 三档模式 (B5-3-P5): 默认智能 / 白盒可改 / 全白 (Comfy 式)
EDIT_MODES = {
    "smart": "系统默认编译子图（A16 快反馈）",
    "whitebox": "系统编译 + 用户图编辑层调整（A19 落地）",
    "fullwhite": "用户关掉默认编译，自己搓上下文（Comfy 式全白）",
}


def init(engine):
    global _engine
    _engine = engine


def _ensure_whitebox():
    """懒初始化引擎白盒状态（_correction_journal / _interaction_graph / IR）。"""
    eng = _engine
    if eng is None:
        return None
    init_fn = getattr(eng, "_init_whitebox", None)
    if init_fn:
        try:
            init_fn()
        except Exception as e:
            logger.debug("whitebox init failed: %s", e)
    return eng


def _journal(dimension: str, before: Any, after: Any,
             reason: str = "user_edit") -> Optional[dict]:
    """Record modification to correction journal (A17). Returns entry dict."""
    eng = _ensure_whitebox()
    if not eng:
        return None
    journal = getattr(eng, "_correction_journal", None)
    if journal:
        try:
            entry = journal.record(
                dimension, before, after, reason=reason,
                turn=getattr(eng, "_turn_counter", 0),
            )
            return entry.__dict__
        except Exception as e:
            logger.debug("journal record failed: %s", e)
    # B5-3-P4: 用户编辑 = 一等行为事件 → 行为链学习（A6 用户纠正权重最高）
    _emit_behavior_edit(eng, dimension, reason)
    return None


def _emit_behavior_edit(eng, dimension: str, reason: str) -> None:
    """把用户编辑行为显式送入行为链（BehaviorGraphAdapter.record_step）。

    行为类型 user_edit: 用户对系统决策的白盒修正 → 行为链学习用户习惯
    （A6/P6: 用户纠正 > 系统自纠; 一次纠正影响层级）。
    """
    if eng is None or reason not in ("user_edit", "user_mode", "user_revert"):
        return
    try:
        bg = getattr(eng, "_behavior_graph", None)
        if bg is None or not hasattr(bg, "record_step"):
            return
        bg.record_step(
            action_summary=f"user_{reason}: {dimension}",
            action_type="user_edit",
            entities={"dimension": dimension, "reason": reason},
            result="",
            success=True,
            correction=True,   # 用户纠正标记（行为链可见）
        )
        logger.debug("behavior edit recorded: %s (%s)", dimension, reason)
    except Exception as e:
        logger.debug("behavior edit record failed: %s", e)


def _find_block(block_id: str):
    """Find a discourse block by id across all trees."""
    eng = _ensure_whitebox()
    if not eng:
        return None
    dt = getattr(eng, "_discourse_tree", None)
    if not dt:
        return None
    trees = getattr(dt, "_trees", {})
    for tree in trees.values():
        blocks = getattr(tree, "blocks", {})
        if block_id in blocks:
            return blocks[block_id]
    return None


def _parse_pair(key: str):
    """Parse 'A→B' (or 'A->B') into (source, target)."""
    for sep in ("→", "->", "—>"):
        if sep in key:
            parts = key.split(sep)
            return parts[0].strip(), parts[1].strip()
    return key.strip(), ""


def _relation_substrate():
    eng = _ensure_whitebox()
    if not eng:
        return None
    wp = getattr(eng, "_world_provider", None)
    if wp is not None:
        rs = getattr(wp, "relation_substrate", None)
        if rs is not None:
            return rs
    return getattr(eng, "_relation_substrate", None)


# ── Viz versioning (B1 同型推广: 内存态 + 版本冲突检测) ────────────────

def _viz_version() -> int:
    """当前可视化编辑版本（engine 热态, 懒初始化 0）。"""
    if _engine is None:
        return 0
    return int(getattr(_engine, "_viz_version", 0) or 0)


def _bump_viz_version() -> int:
    """编辑成功后版本 +1（内存态=热）。"""
    v = _viz_version() + 1
    if _engine is not None:
        setattr(_engine, "_viz_version", v)
    return v


def _guard_viz_version(version: Optional[int]) -> None:
    """请求带 version 且落后于当前 → 409（前端乐观更新冲突检测）。"""
    cur = _viz_version()
    if version is not None and version < cur:
        raise HTTPException(status_code=409, detail={
            "error": "version_conflict",
            "current_version": cur,
        })


# ── 三档模式开关 (B5-3-P5) ─────────────────────────────────────────────

class ModeRequest(BaseModel):
    mode: str = "smart"  # smart | whitebox | fullwhite


@router.get("/mode")
async def get_mode():
    """Get current edit mode + available modes (A19 白盒开关)."""
    if not _engine:
        raise HTTPException(503, "engine not initialized")
    _ensure_whitebox()
    return {
        "mode": getattr(_engine, "_edit_mode", "smart"),
        "modes": [{"key": k, "desc": v} for k, v in EDIT_MODES.items()],
    }


@router.put("/mode")
async def set_mode(req: ModeRequest):
    """Switch edit mode (smart / whitebox / fullwhite). Journaled (A17)."""
    if not _engine:
        raise HTTPException(503, "engine not initialized")
    if req.mode not in EDIT_MODES:
        raise HTTPException(422, f"invalid mode: {req.mode}, must be one of {list(EDIT_MODES)}")
    _ensure_whitebox()
    old = getattr(_engine, "_edit_mode", "smart")
    _engine._edit_mode = req.mode
    _journal("mode", old, req.mode, reason="user_mode")
    return {"mode": req.mode, "before": old, "desc": EDIT_MODES[req.mode]}


# ── Journal 白盒检查 (A19/A17) ─────────────────────────────────────────

@router.get("/journal")
async def get_journal(dimension: str = "", limit: int = 50):
    """White-box: inspect correction journal entries (A19/A17)."""
    if not _engine:
        raise HTTPException(503, "engine not initialized")
    _ensure_whitebox()
    journal = getattr(_engine, "_correction_journal", None)
    if not journal:
        return {"entries": [], "stats": {"total_corrections": 0}}
    entries = [e.__dict__ for e in journal.entries_since(dimension, limit)]
    return {"entries": entries, "stats": journal.stats()}


# ── 恢复端点 (B5-3-P2): 读 journal before → 应用回滚 (A17) ─────────────

class RevertRequest(BaseModel):
    dimension: str = ""  # journal dimension to revert; empty = last correction


def _apply_revert(dim: str, entry) -> dict:
    """Apply rollback for one journaled dimension. Returns result dict."""
    eng = _ensure_whitebox()
    before = entry.before

    # graph.edge.{source}→{target} — before = weight (float)
    if dim.startswith("graph.edge."):
        ig = getattr(eng, "_interaction_graph", None)
        if not ig:
            raise HTTPException(404, "InteractionGraph not available")
        src, tgt = _parse_pair(dim[len("graph.edge."):])
        # 先移除现有同源同目标边, 再以 before 权重加回 — 避免重复边
        edges = ig._adjacency.get(src, [])
        for i, e in enumerate(edges):
            if e.target == tgt:
                del edges[i]
                break
        from core.agent.state.interaction_graph import InteractionType
        weight = float(before) if before not in (None, "", "?") else 0.5
        ig.add_edge(src, tgt, InteractionType.DEPENDS_ON, weight)
        return {"reverted": "graph.edge", "source": src, "target": tgt, "weight": weight}

    # graph.node.{node_id} — before = state dict
    if dim.startswith("graph.node."):
        ig = getattr(eng, "_interaction_graph", None)
        if not ig:
            raise HTTPException(404, "InteractionGraph not available")
        node_id = dim[len("graph.node."):]
        state = before if isinstance(before, dict) else {}
        ig.set_node_state(node_id, state)
        return {"reverted": "graph.node", "node": node_id, "state": state}

    # tree.{block_id}.{field} — before = value
    if dim.startswith("tree."):
        parts = dim.split(".")
        block_id = parts[1] if len(parts) > 1 else ""
        field = parts[2] if len(parts) > 2 else "temperature"
        block = _find_block(block_id)
        if not block:
            raise HTTPException(404, f"Block {block_id} not found")
        if not hasattr(block, field):
            raise HTTPException(422, f"Block field not editable: {field}")
        setattr(block, field, before)
        return {"reverted": f"tree.{field}", "block": block_id, "value": before}

    # object.{source}.relations — before = relations dict
    if dim.startswith("object.") and dim.endswith(".relations"):
        source = dim[len("object."):-len(".relations")]
        obj = getattr(eng, "_world_objects", {}).get(source)
        if not obj:
            raise HTTPException(404, f"Object {source} not found")
        obj.relations = list(before) if isinstance(before, list) else (
            before if isinstance(before, dict) else [])
        return {"reverted": "object.relations", "source": source, "relations": obj.relations}

    # object.{source}.name / .lifespan — before = old value
    if dim.startswith("object."):
        suffix = None
        for cand in (".name", ".lifespan"):
            if dim.endswith(cand):
                suffix = cand
                break
        if suffix:
            source = dim[len("object."):-len(suffix)]
            obj = getattr(eng, "_world_objects", {}).get(source)
            if not obj:
                raise HTTPException(404, f"Object {source} not found")
            field = suffix[1:]
            if field == "lifespan":
                from core.agent.state.state_object import Lifespan
                try:
                    before = Lifespan(before) if isinstance(before, str) else before
                except ValueError:
                    pass
            setattr(obj, field, before)
            return {"reverted": f"object.{field}", "source": source, "value": before}

    # relation.{source}→{target} — before = {"kind":..., "strength":...}
    if dim.startswith("relation."):
        rs = _relation_substrate()
        if not rs:
            raise HTTPException(404, "RelationSubstrate not available")
        src, tgt = _parse_pair(dim[len("relation."):])
        edges = rs.query(source=src, target=tgt)
        if before == "none":  # 该边是用户新增 → revert = 删除
            if not edges:
                raise HTTPException(404, f"Relation {src}→{tgt} not found")
            e = edges[0]
            if hasattr(rs, "_edges") and e.identity in rs._edges:
                del rs._edges[e.identity]
            if hasattr(rs, "_by_source"):
                rs._by_source.get(src, set()).discard(e.identity)
            if hasattr(rs, "_by_target"):
                rs._by_target.get(tgt, set()).discard(e.identity)
            return {"reverted": "relation_removed", "source": src, "target": tgt}
        if isinstance(before, dict):
            if not edges:  # 该边被用户删除 → revert = 重新加回
                from core.agent.compiler.relation_substrate import RelationEdge
                kind = before.get("kind") or "depends_on"
                strength = before.get("strength")
                eid = f"user:{src}→{tgt}:{int(time.time()*1000)}"
                edge = RelationEdge(
                    identity=eid, source=src, target=tgt,
                    predicate=kind, inverse=f"inv_{kind}",
                    relation_kind="structural", semantic_strength="association",
                    confidence=float(strength) if isinstance(strength, (int, float)) else 0.5,
                )
                rs.add(edge)
                return {"reverted": "relation_added_back", "source": src,
                        "target": tgt, "identity": eid}
            e = edges[0]
            if "kind" in before:
                e.relation_kind = before["kind"]
            if "strength" in before:
                if isinstance(before["strength"], (int, float)):
                    e.confidence = min(1.0, max(0.0, float(before["strength"])))
                else:
                    e.semantic_strength = before["strength"]
            return {"reverted": "relation", "source": src, "target": tgt,
                    "kind": getattr(e, "relation_kind", None),
                    "strength": getattr(e, "confidence", None)}
        raise HTTPException(422, f"unsupported before type for relation revert: {type(before)}")

    # ir.{domain}.{type} — before = "none"(added) | content(edited)
    if dim.startswith("ir."):
        lc = getattr(eng, "_last_context", None)
        if not lc:
            raise HTTPException(404, "No context assembled yet")
        rest = dim[len("ir."):]
        dom, _, etype = rest.partition(".")
        target_content = entry.after if isinstance(entry.after, str) else ""
        # 找到内容匹配的条目并移除/还原
        removed = 0
        for e in list(lc.entries):
            if e.domain == dom and (not etype or e.type == etype):
                if before in (None, "none", "-") or str(getattr(e, "content", "")) == target_content:
                    lc.entries.remove(e)
                    removed += 1
        if before not in (None, "none", "-") and removed == 0:
            from core.agent.context.cross_domain_ir import IREntry
            lc.entries.append(IREntry(domain=dom, type=etype or "user_edited",
                                      content=str(before)[:500], confidence=0.8))
        lc.recalc_total()
        return {"reverted": "ir", "domain": dom, "type": etype or "user_edited",
                "entries_removed": removed}

    # mode — before = previous mode str
    if dim == "mode":
        if before not in EDIT_MODES:
            raise HTTPException(422, f"cannot revert to invalid mode: {before}")
        eng._edit_mode = before
        return {"reverted": "mode", "mode": before}

    # note.* — 移除对应注释 (api_annotate 写的 JSONL)
    if dim.startswith("note."):
        path = "data/annotations/user_notes.jsonl"
        removed = 0
        if os.path.exists(path):
            kept = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except Exception:
                        kept.append(line)
                        continue
                    if (e.get("comment") == entry.after and
                            f"note.{e.get('domain','')}.{e.get('target','')}" == dim):
                        removed += 1
                        continue
                    kept.append(line)
            if removed:
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(kept)
        return {"reverted": "note", "removed": removed}

    raise HTTPException(422, f"unsupported dimension for revert: {dim}")


@router.put("/revert")
async def revert_edit(req: RevertRequest):
    """Revert a prior user edit: read journal 'before' → apply rollback (A17)."""
    if not _engine:
        raise HTTPException(503, "engine not initialized")
    _ensure_whitebox()
    journal = getattr(_engine, "_correction_journal", None)
    if not journal:
        raise HTTPException(404, "CorrectionJournal not available")
    # 跳过已回滚条目 (user_revert): 回滚本身不可再回滚。
    # 指定维度 → 找该维度最近一次未回滚的用户编辑；
    # 未指定 → 全局最近一次未回滚的用户编辑。
    # 已回滚维度的判断: 该维度最近一条记录是 user_revert → 已回滚, 跳过。
    entry = None
    for e in reversed(journal._entries):
        if req.dimension and e.dimension != req.dimension:
            continue
        if e.reason == "user_revert":
            continue
        last_for_dim = journal.last_entry(e.dimension)
        if last_for_dim is not None and last_for_dim.reason == "user_revert":
            continue  # 该维度最近一次是回滚 → 已回滚, 跳过
        entry = e
        break
    if not entry:
        raise HTTPException(404, f"No correction for '{req.dimension or 'last'}'")
    result = _apply_revert(entry.dimension, entry)
    # 回滚本身也 journaled — 可追溯 (A17)
    _journal(entry.dimension, entry.after, entry.before, reason="user_revert")
    result["dimension"] = entry.dimension
    return result


# ── Graph editing (层1: InteractionGraph) ──────────────────────────────

class GraphEditRequest(BaseModel):
    action: str = "update_weight"  # update_weight | add_edge | remove_edge | set_node
    source: str = ""
    target: str = ""
    weight: Optional[float] = None
    edge_type: Optional[str] = None
    node_id: str = ""
    node_state: Optional[dict] = None
    version: Optional[int] = None


@router.put("/graph")
async def edit_graph(req: GraphEditRequest):
    """Edit InteractionGraph — re-weight edges, add/remove, set node state."""
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    _guard_viz_version(req.version)
    ig = getattr(_engine, "_interaction_graph", None)
    if not ig:
        raise HTTPException(404, "InteractionGraph not available")

    from core.agent.state.interaction_graph import InteractionType
    edge_key = f"{req.source}→{req.target}"

    if req.action in ("update_weight", "add_edge") and req.source and req.target:
        # before = 当前权重 (edge-level; 无则 0.5 默认)
        old = 0.5
        for e in ig._adjacency.get(req.source, []):
            if e.target == req.target:
                old = e.influence_weight
                break
        ig.add_edge(req.source, req.target,
                    InteractionType.DEPENDS_ON,
                    req.weight if req.weight is not None else old)
        _journal(f"graph.edge.{edge_key}", old,
                 req.weight if req.weight is not None else old)
        _bump_viz_version()
        return {"edited": "edge", "source": req.source, "target": req.target,
                "weight": req.weight if req.weight is not None else old}

    elif req.action == "remove_edge" and req.source and req.target:
        old = None
        edges = ig._adjacency.get(req.source, [])
        for i, e in enumerate(edges):
            if e.target == req.target:
                old = e.influence_weight
                del edges[i]
                break
        if old is None:
            raise HTTPException(404, f"Edge {edge_key} not found")
        _journal(f"graph.edge.{edge_key}", old, 0.0, reason="user_remove")
        _bump_viz_version()
        return {"edited": "edge_removed", "source": req.source, "target": req.target}

    elif req.action == "set_node" and req.node_id and req.node_state:
        old = ig.get_node_state(req.node_id)
        ig.set_node_state(req.node_id, req.node_state)
        _journal(f"graph.node.{req.node_id}", old, req.node_state)
        _bump_viz_version()
        return {"edited": "node", "node": req.node_id, "state": req.node_state}

    return {"error": f"unknown action: {req.action}"}


# ── Discourse tree editing ─────────────────────────────────────────────

class TreeEditRequest(BaseModel):
    action: str = "reclassify"  # reclassify | merge | split | rename
    block_id: str = ""
    temperature: Optional[str] = None  # hot/warm/cold
    topic: Optional[str] = None
    parent_id: Optional[str] = None
    version: Optional[int] = None


@router.put("/discourse-tree")
async def edit_tree(req: TreeEditRequest):
    """Edit DiscourseBlockTree — reclassify blocks, rename topics, merge/split."""
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    _guard_viz_version(req.version)
    block = _find_block(req.block_id)
    if not block:
        raise HTTPException(404, f"Block {req.block_id} not found")

    if req.action == "reclassify" and req.temperature:
        # 真实模型: active | paused | cold | frozen
        # 兼容旧前端: hot→active, warm→paused
        _TEMP_MAP = {
            "hot": "active", "warm": "paused",
            "active": "active", "paused": "paused",
            "cold": "cold", "frozen": "frozen",
        }
        new_temp = _TEMP_MAP.get(req.temperature)
        if new_temp is None:
            raise HTTPException(422, f"invalid temperature: {req.temperature}")
        old_temp = getattr(block, "temperature", "active")
        block.temperature = new_temp
        _journal(f"tree.{req.block_id}.temperature", old_temp, req.temperature)
        _bump_viz_version()
        return {"edited": "temperature", "block": req.block_id,
                "before": old_temp, "after": new_temp}

    elif req.action == "rename" and req.topic:
        old_topic = getattr(block, "topic", "")
        block.topic = req.topic
        _journal(f"tree.{req.block_id}.topic", old_topic, req.topic)
        _bump_viz_version()
        return {"edited": "topic", "block": req.block_id,
                "before": old_topic, "after": req.topic}

    elif req.action == "merge" and req.parent_id:
        old_parent = str(getattr(block, "parent", "root"))
        block.parent = req.parent_id
        _journal(f"tree.{req.block_id}.parent", old_parent, req.parent_id)
        _bump_viz_version()
        return {"edited": "parent", "block": req.block_id,
                "before": old_parent, "after": req.parent_id}

    return {"error": f"unknown action: {req.action}"}


# ── Object/Concept editing ─────────────────────────────────────────────

class ObjectEditRequest(BaseModel):
    action: str = "relate"    # relate | unrelate | rename | set_lifespan
    source: str = ""
    target: str = ""
    relation_type: str = "depends_on"
    lifespan: Optional[str] = None
    new_name: Optional[str] = None
    version: Optional[int] = None


@router.put("/objects")
async def edit_objects(req: ObjectEditRequest):
    """Edit SemanticObject graph — add/remove relations, rename, change lifespan."""
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    _guard_viz_version(req.version)
    objects = getattr(_engine, "_world_objects", {})
    if not objects:
        raise HTTPException(404, "no objects loaded")

    if req.action == "relate" and req.source and req.target:
        obj = objects.get(req.source)
        if not obj:
            raise HTTPException(404, f"Object {req.source} not found")
        rels = list(getattr(obj, "relations", []))
        old_rels = list(rels)
        if not any(r.get("target") == req.target and r.get("type") == req.relation_type
                   for r in rels):
            rels.append({"target": req.target, "type": req.relation_type,
                         "confidence": 0.8})
        obj.relations = rels
        _journal(f"object.{req.source}.relations", old_rels, list(rels))
        _bump_viz_version()
        return {"edited": "relation_added", "source": req.source,
                "target": req.target, "type": req.relation_type}

    elif req.action == "unrelate" and req.source and req.target:
        obj = objects.get(req.source)
        if not obj:
            raise HTTPException(404, f"Object {req.source} not found")
        rels = list(getattr(obj, "relations", []))
        old_rels = list(rels)
        before_len = len(rels)
        rels = [r for r in rels
                if not (r.get("target") == req.target and
                        (not req.relation_type or r.get("type") == req.relation_type))]
        if len(rels) == before_len:
            raise HTTPException(404, f"Relation {req.source}-{req.target} not found")
        obj.relations = rels
        _journal(f"object.{req.source}.relations", old_rels, list(rels))
        _bump_viz_version()
        return {"edited": "relation_removed", "source": req.source,
                "target": req.target}

    elif req.action == "rename" and req.new_name:
        obj = objects.get(req.source)
        if not obj:
            raise HTTPException(404, f"Object {req.source} not found")
        old = getattr(obj, "name", req.source)
        obj.name = req.new_name
        _journal(f"object.{req.source}.name", old, req.new_name)
        _bump_viz_version()
        return {"edited": "renamed", "source": req.source, "before": old,
                "after": req.new_name}

    elif req.action == "set_lifespan" and req.lifespan:
        obj = objects.get(req.source)
        if not obj:
            raise HTTPException(404, f"Object {req.source} not found")
        old = getattr(obj, "lifespan", None)
        from core.agent.state.state_object import Lifespan
        try:
            if isinstance(req.lifespan, str):
                # 支持名称 (MIND/WORKSPACE/...) 与整数值 ("3")
                new_ls = Lifespan[req.lifespan] if req.lifespan in Lifespan.__members__ \
                    else Lifespan(int(req.lifespan))
            else:
                new_ls = Lifespan(req.lifespan)
        except ValueError:
            raise HTTPException(422, f"invalid lifespan: {req.lifespan}")
        obj.lifespan = new_ls
        _journal(f"object.{req.source}.lifespan", old, req.lifespan)
        _bump_viz_version()
        return {"edited": "lifespan", "source": req.source,
                "before": old, "after": req.lifespan}

    return {"error": "action not completed"}


# ── Relation edge editing (RelationSubstrate) ──────────────────────────

class RelationEditRequest(BaseModel):
    action: str = "update"   # update | add | remove
    source: str = ""
    target: str = ""
    kind: Optional[str] = None
    strength: Optional[float] = None
    version: Optional[int] = None


@router.put("/relations")
async def edit_relations(req: RelationEditRequest):
    """Edit RelationSubstrate edges — update strength, change kind, add/remove."""
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    _guard_viz_version(req.version)
    rs = _relation_substrate()
    if not rs:
        raise HTTPException(404, "RelationSubstrate not available")

    if req.action == "update" and req.source and req.target:
        edges = rs.query(source=req.source, target=req.target)
        if not edges:
            raise HTTPException(404, f"Relation {req.source}→{req.target} not found")
        e = edges[0]
        old = {"kind": getattr(e, "relation_kind", None),
               "strength": getattr(e, "confidence", None)}
        if req.kind:
            e.relation_kind = req.kind
        if req.strength is not None:
            e.confidence = min(1.0, max(0.0, req.strength))
        _journal(f"relation.{req.source}→{req.target}", old,
                 {"kind": req.kind or old["kind"],
                  "strength": (req.strength if req.strength is not None
                               else old["strength"])})
        _bump_viz_version()
        return {"edited": "relation", "source": req.source, "target": req.target}

    elif req.action == "add" and req.source and req.target:
        from core.agent.compiler.relation_substrate import RelationEdge
        edges = rs.query(source=req.source, target=req.target)
        if edges:
            raise HTTPException(409, f"Relation {req.source}→{req.target} already exists")
        eid = f"user:{req.source}→{req.target}:{int(time.time()*1000)}"
        edge = RelationEdge(
            identity=eid, source=req.source, target=req.target,
            predicate=req.kind or "depends_on",
            inverse=f"inv_{req.kind or 'depends_on'}",
            relation_kind="structural",
            semantic_strength="association",
            confidence=req.strength if req.strength is not None else 0.5,
        )
        rs.add(edge)
        _journal(f"relation.{req.source}→{req.target}", "none",
                 {"kind": req.kind or "depends_on",
                  "strength": edge.confidence})
        _bump_viz_version()
        return {"edited": "added", "source": req.source, "target": req.target,
                "identity": eid}

    elif req.action == "remove" and req.source and req.target:
        edges = rs.query(source=req.source, target=req.target)
        if not edges:
            raise HTTPException(404, f"Relation {req.source}→{req.target} not found")
        e = edges[0]
        old = {"kind": getattr(e, "relation_kind", None),
               "strength": getattr(e, "confidence", None)}
        if hasattr(rs, "_edges") and e.identity in rs._edges:
            del rs._edges[e.identity]
        if hasattr(rs, "_by_source"):
            rs._by_source.get(req.source, set()).discard(e.identity)
        if hasattr(rs, "_by_target"):
            rs._by_target.get(req.target, set()).discard(e.identity)
        _journal(f"relation.{req.source}→{req.target}", old, "none", reason="user_remove")
        _bump_viz_version()
        return {"edited": "removed", "source": req.source, "target": req.target}

    return {"error": "action not completed"}


# ── IR (Intermediate Representation) direct edit ───────────────────────

class IREditRequest(BaseModel):
    domain: str = ""
    entry_type: str = ""
    content: str = ""
    confidence: Optional[float] = None
    version: Optional[int] = None


class SerializeRequest(BaseModel):
    fmt: str = "json"  # json | xml | markdown | natural


class FormatRequest(BaseModel):
    fmt: str = "json"


@router.post("/serialize")
async def serialize_context(req: SerializeRequest):
    """B5-3-P3: 层2 渲染为指定形态（用户可选给 LLM 的形态）。

    数据源: _last_context IR（用户可编辑层2）→ serializer 家族。
    """
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    try:
        from core.agent.v4.cognitive.serializers import serialize, normalize_format
    except Exception as e:
        raise HTTPException(500, f"serializer import failed: {e}")
    lc = getattr(_engine, "_last_context", None)
    if lc is None:
        return {"format": normalize_format(req.fmt), "text": "", "tokens": 0,
                "source": "no_context"}
    try:
        ir = lc.to_dict() if hasattr(lc, "to_dict") else lc.__dict__
    except Exception:
        ir = {"entries": [{"domain": getattr(e, "domain", "?"),
                           "content": str(getattr(e, "content", ""))}
                          for e in getattr(lc, "entries", [])]}
    res = serialize(ir, req.fmt)
    res["source"] = "last_context"
    return res


@router.get("/format")
async def get_serialize_format():
    """B5-3-P3: 当前形态 + 可选形态。"""
    from core.agent.v4.cognitive.serializers import FORMATS
    return {"format": "json", "available": list(FORMATS)}


@router.put("/format")
async def set_serialize_format(req: FormatRequest):
    """B5-3-P3: 切换层2 默认形态（持久化到引擎 subgraph compiler）。"""
    if not _engine:
        raise HTTPException(503)
    from core.agent.v4.cognitive.serializers import normalize_format
    fmt = normalize_format(req.fmt)
    comp = getattr(_engine, "_subgraph", None)
    if comp is None:
        reg = getattr(_engine, "_registry", None)
        if reg is not None:
            comp = getattr(reg, "_instances", {}).get("subgraph")
    if comp is not None and hasattr(comp, "set_format"):
        try:
            comp.set_format(fmt)
        except Exception:
            pass
    _journal("serialize_format", getattr(_engine, "_serialize_format", "json"),
             fmt, reason="user_mode")
    _engine._serialize_format = fmt
    return {"format": fmt, "status": "set"}


@router.put("/ir")
async def edit_ir(req: IREditRequest):
    """Directly edit the Intermediate Representation context entries.
    This is the deepest level of 白盒化 — users can modify what the LLM sees."""
    if not _engine:
        raise HTTPException(503)
    _ensure_whitebox()
    _guard_viz_version(req.version)
    lc = getattr(_engine, "_last_context", None)
    if not lc:
        raise HTTPException(404, "No context assembled yet")

    from core.agent.context.cross_domain_ir import IREntry
    if req.content:
        # 同 domain+type 已存在 → 编辑 (before = 旧内容)；否则新增 (before = "none")
        old_content = "none"
        for e in lc.entries:
            if e.domain == req.domain and e.type == (req.entry_type or "user_edited"):
                old_content = getattr(e, "content", "")
                e.content = req.content[:500]
                if req.confidence is not None:
                    e.confidence = req.confidence
                break
        else:
            entry = IREntry(domain=req.domain, type=req.entry_type or "user_edited",
                            content=req.content[:500],
                            confidence=req.confidence or 0.8)
            lc.add_entry(domain=req.domain, entry=entry)
        lc.recalc_total()
        _journal(f"ir.{req.domain}.{req.entry_type or 'user_edited'}",
                 old_content, req.content[:100])
        _bump_viz_version()
        return {"edited": "ir_entry_upserted", "domain": req.domain,
                "type": req.entry_type or "user_edited",
                "before": old_content, "entries": len(lc.entries)}

    return {"error": "content required"}
