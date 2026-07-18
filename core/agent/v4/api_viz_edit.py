"""Visualization Interaction API — user-editable graph/tree/object/relation.

Design principle: 白盒化 — every graph node, tree block, concept edge
is user-visible AND user-editable. Modifications are journaled and feed
back into Mind learning + ABC rule refinement.

This closes the IR loop: IR is not just a data format, it's the editable
intermediate representation between raw observations and LLM context.
"""
import json, time, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/edit")
_engine = None

def init(engine):
    global _engine
    _engine = engine


def _journal(dimension: str, before, after, reason: str = "user_edit"):
    """Record modification to correction journal."""
    eng = _engine
    if not eng: return
    journal = getattr(eng, '_correction_journal', None)
    if journal:
        journal.record(dimension, before, after, reason=reason,
                       turn=getattr(eng, '_turn_counter', 0))


# ── Graph editing ──

class GraphEditRequest(BaseModel):
    action: str = "update_weight"  # update_weight | add_edge | remove_edge | set_node
    source: str = ""
    target: str = ""
    weight: Optional[float] = None
    edge_type: Optional[str] = None
    node_id: str = ""
    node_state: Optional[dict] = None


@router.put("/graph")
async def edit_graph(req: GraphEditRequest):
    """Edit InteractionGraph — re-weight edges, add/remove, set node state."""
    if not _engine: raise HTTPException(503)
    ig = getattr(_engine, '_interaction_graph', None)
    if not ig: raise HTTPException(404, "InteractionGraph not available")

    if req.action == "update_weight" and req.source and req.target and req.weight is not None:
        old = ig.get_node_state(f"{req.source}→{req.target}") if hasattr(ig, 'get_node_state') else {}
        if hasattr(ig, 'add_edge'):
            ig.add_edge(req.source, req.target,
                       getattr(ig, 'InteractionType', type('E',(),{'DEPENDS_ON':'DEPENDS_ON'})).DEPENDS_ON,
                       req.weight)
        _journal(f"graph.{req.source}→{req.target}", old.get('weight', '?'), req.weight)
        return {"edited": "edge", "source": req.source, "target": req.target, "weight": req.weight}

    elif req.action == "set_node" and req.node_id and req.node_state:
        old = ig.get_node_state(req.node_id) if hasattr(ig, 'get_node_state') else {}
        if hasattr(ig, 'set_node_state'):
            ig.set_node_state(req.node_id, req.node_state)
        _journal(f"graph.node.{req.node_id}", str(old)[:100], str(req.node_state)[:100])
        return {"edited": "node", "node": req.node_id, "state": req.node_state}

    return {"error": f"unknown action: {req.action}"}


# ── Discourse tree editing ──

class TreeEditRequest(BaseModel):
    action: str = "reclassify"  # reclassify | merge | split | rename
    block_id: str = ""
    temperature: Optional[str] = None  # hot/warm/cold
    topic: Optional[str] = None
    parent_id: Optional[str] = None


@router.put("/discourse-tree")
async def edit_tree(req: TreeEditRequest):
    """Edit DiscourseBlockTree — reclassify blocks, rename topics, merge/split."""
    if not _engine: raise HTTPException(503)
    dt = getattr(_engine, '_discourse_tree', None)
    if not dt: raise HTTPException(404, "DiscourseTree not available")

    trees = getattr(dt, '_trees', {})
    block = None
    for tree in trees.values():
        blocks = getattr(tree, 'blocks', {})
        if req.block_id in blocks:
            block = blocks[req.block_id]
            break

    if not block:
        raise HTTPException(404, f"Block {req.block_id} not found")

    if req.action == "reclassify" and req.temperature:
        old_temp = getattr(block, 'temperature', 'warm')
        block.temperature = req.temperature
        _journal(f"tree.{req.block_id}.temperature", old_temp, req.temperature)
        return {"edited": "temperature", "block": req.block_id, "before": old_temp, "after": req.temperature}

    elif req.action == "rename" and req.topic:
        old_topic = getattr(block, 'topic', '')
        block.topic = req.topic
        _journal(f"tree.{req.block_id}.topic", old_topic[:100], req.topic[:100])
        return {"edited": "topic", "block": req.block_id, "before": old_topic[:100], "after": req.topic[:100]}

    elif req.action == "merge" and req.parent_id:
        old_parent = str(getattr(block, 'parent', 'root'))
        block.parent = req.parent_id
        _journal(f"tree.{req.block_id}.parent", old_parent, req.parent_id)
        return {"edited": "parent", "block": req.block_id, "before": old_parent, "after": req.parent_id}

    return {"error": f"unknown action: {req.action}"}


# ── Object/Concept editing ──

class ObjectEditRequest(BaseModel):
    action: str = "relate"    # relate | unrelate | rename | set_lifespan
    source: str = ""
    target: str = ""
    relation_type: str = "depends_on"
    lifespan: Optional[str] = None
    new_name: Optional[str] = None


@router.put("/objects")
async def edit_objects(req: ObjectEditRequest):
    """Edit SemanticObject graph — add/remove relations, rename, change lifespan."""
    if not _engine: raise HTTPException(503)
    objects = getattr(_engine, '_world_objects', {})
    if not objects: return {"edited": False, "reason": "no objects loaded"}

    if req.action == "relate" and req.source and req.target:
        obj = objects.get(req.source)
        if not obj: raise HTTPException(404, f"Object {req.source} not found")
        rels = getattr(obj, 'relations', {})
        old_rels = dict(rels)
        if req.relation_type not in rels:
            rels[req.relation_type] = []
        if req.target not in rels[req.relation_type]:
            rels[req.relation_type].append(req.target)
        _journal(f"object.{req.source}.relations", str(old_rels)[:200], str(rels)[:200])
        return {"edited": "relation_added", "source": req.source, "target": req.target, "type": req.relation_type}

    elif req.action == "unrelate" and req.source and req.target:
        obj = objects.get(req.source)
        if not obj: raise HTTPException(404)
        rels = getattr(obj, 'relations', {})
        for rt, targets in rels.items():
            if req.target in targets:
                targets.remove(req.target)
                _journal(f"object.{req.source}.relations", f"had {req.target}", f"removed {req.target}")
                return {"edited": "relation_removed", "source": req.source, "target": req.target}

    return {"error": "action not completed"}


# ── Relation edge editing ──

class RelationEditRequest(BaseModel):
    action: str = "update"   # update | add | remove
    source: str = ""
    target: str = ""
    kind: Optional[str] = None
    strength: Optional[float] = None


@router.put("/relations")
async def edit_relations(req: RelationEditRequest):
    """Edit RelationSubstrate edges — update strength, change kind, add/remove."""
    if not _engine: raise HTTPException(503)
    rs = None
    if hasattr(_engine, '_world_provider') and _engine._world_provider:
        rs = getattr(_engine._world_provider, 'relation_substrate', None)
    if not rs: raise HTTPException(404, "RelationSubstrate not available")

    if req.action == "update" and req.source and req.target:
        edges = rs.query(source=req.source, target=req.target)
        if edges:
            e = edges[0]
            old = f"kind={getattr(e,'relation_kind','?')} strength={getattr(e,'semantic_strength','?')}"
            if req.kind: e.relation_kind = req.kind
            if req.strength is not None: e.semantic_strength = req.strength
            _journal(f"relation.{req.source}→{req.target}", old,
                     f"kind={req.kind} strength={req.strength}")
            return {"edited": "relation", "source": req.source, "target": req.target}

    elif req.action == "add" and req.source and req.target and req.strength:
        if hasattr(rs, 'add_edge'):
            rs.add_edge(req.source, req.target, req.kind or "depends_on", req.strength)
            _journal(f"relation.{req.source}→{req.target}", "none", f"strength={req.strength}")
            return {"edited": "added", "source": req.source, "target": req.target}

    return {"error": "action not completed"}


# ── IR (Intermediate Representation) direct edit ──

class IREditRequest(BaseModel):
    domain: str = ""
    entry_type: str = ""
    content: str = ""
    confidence: Optional[float] = None


@router.put("/ir")
async def edit_ir(req: IREditRequest):
    """Directly edit the Intermediate Representation context entries.
    This is the deepest level of 白盒化 — users can modify what the LLM sees."""
    if not _engine: raise HTTPException(503)
    lc = getattr(_engine, '_last_context', None)
    if not lc: raise HTTPException(404, "No context assembled yet")

    # Find existing entry or add new one
    from core.agent.v4.context.cross_domain_ir import IREntry
    if req.content:
        entry = IREntry(domain=req.domain, type=req.entry_type or "user_edited",
                        content=req.content[:500], confidence=req.confidence or 0.8)
        lc.add_entry(domain=req.domain, entry=entry)
        _journal(f"ir.{req.domain}.{req.entry_type}", "none", req.content[:100])
        return {"edited": "ir_entry_added", "domain": req.domain, "type": req.entry_type}

    return {"error": "content required"}
