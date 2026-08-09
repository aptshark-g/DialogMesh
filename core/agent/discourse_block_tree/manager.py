"""DiscourseBlockTreeManager - core orchestrator"""
import hashlib
from typing import Dict, List, Optional
from .models import DiscourseBlock, DiscourseEntity, GroupReference
from .header_injector import HeaderInjector, EntityCache
from .syntactic_decomposer import SyntacticDecomposer
from .macro_micro_quantizer import QUANTIZER
from .segmenter import SEGMENTER
from .granularity_regulator import REGULATOR
from .summary_engine import SUMMARY_ENGINE
from .context_builder import CONTEXT_BUILDER
from .indexer import Indexer, INDEXER
from .topic_markers import DETECTOR as TOPIC_MARKER_DETECTOR
from .models import CrossReference


class DiscourseBlockTreeManager:
    """DiscourseBlockTree core orchestrator"""

    def __init__(self, llm_provider=None, max_tokens=4096,
                 global_split_threshold=0.5):
        self.llm = llm_provider
        self.blocks = {}
        self.current_block_id = None
        self.turn_count = 0
        self.entity_cache = EntityCache()
        self.header_injector = HeaderInjector(self.entity_cache)
        self.decomposer = SyntacticDecomposer(use_llm=llm_provider is not None)
        self.segmenter = SEGMENTER
        self.segmenter.global_split_threshold = global_split_threshold
        self.regulator = REGULATOR
        self.regulator.global_split_threshold = global_split_threshold
        self.summary_engine = SUMMARY_ENGINE
        self.summary_engine.llm = llm_provider
        self.context_builder = CONTEXT_BUILDER
        self.context_builder.max_tokens = max_tokens
        self.indexer = Indexer()
        self.group_ref_index: dict[str, GroupReference] = {}

    def ingest_turn(self, turn_index, text, cognitive_hints=None):
        self.turn_count = turn_index
        # P5 (画像 R5 ③): Track A 认知状态 → 组块边界判据输入。
        # 消费方：segmenter 可读 self._last_cognitive_hints 调整合并/切分倾向
        # （KERNEL §八.8.4 疲劳/注意力/惯性）。白盒 get_stats 亦暴露。
        self._last_cognitive_hints = cognitive_hints or {}
        injected = self.header_injector.inject(text)
        entities = self.header_injector.extract_entities(text)
        self.entity_cache.push(entities)

        # 话题切换检测
        prev_blocks = list(self.blocks.values())
        prev_ents = [e.text for b in prev_blocks[-3:] for e in getattr(b, 'entities', []) if hasattr(e, 'text')]
        curr_ents = [e.text for e in entities if hasattr(e, 'text')] if entities else []
        is_switch, switch_conf, switch_src = TOPIC_MARKER_DETECTOR.detect(text, curr_ents, prev_ents)

        edus = self.decomposer.decompose(text)
        scores = QUANTIZER.score_all(edus) if len(edus) > 1 else []
        new_blocks = self.segmenter.segment(edus, scores)
        if not new_blocks:
            return []
        block_ids = []
        for i, block in enumerate(new_blocks):
            block.created_at_turn = turn_index
            block.last_active_turn = turn_index
            block.entities = entities[:]
            # 话题切换标记
            if is_switch:
                block.parent_id = self.current_block_id  # 链接回前一个块
                block.topic_switch = True
                block.topic_switch_confidence = switch_conf
                # 查找被引用的块并建立双向链接
                refs = self.find_reference(text) or []
                for ref_bid in refs[:3]:
                    ref_parent = self.blocks.get(ref_bid)
                    if ref_parent:
                        ref_parent.child_ids.append(block.block_id)
                # Cross-topic reference detection
                cross_refs = TOPIC_MARKER_DETECTOR.detect_cross_ref(text)
                if cross_refs and self.current_block_id:
                    for ref_type, ref_conf in cross_refs:
                        candidates = self.search(text) or []
                        for tid in candidates[:2]:
                            if self.blocks.get(tid) and tid != block.block_id:
                                cr = CrossReference(target_block_id=tid, ref_type=ref_type, strength=ref_conf, created_at_turn=turn_index, source='manual')
                                block.cross_refs.append(cr)
                                self._last_cross_ref = (ref_type, ref_conf, tid)
                        break
            if i < len(scores):
                block.cohesion_boundary = scores[i].total_score
            if i == 0 and self.current_block_id:
                block.parent_id = self.current_block_id
                parent = self.blocks.get(self.current_block_id)
                if parent: parent.child_ids.append(block.block_id)
            elif i > 0 and block_ids:
                block.parent_id = block_ids[i-1]
                parent = self.blocks.get(block_ids[i-1])
                if parent: parent.child_ids.append(block.block_id)
            self.blocks[block.block_id] = block
            self.indexer.index_block(block)
            block_ids.append(block.block_id)
        self.current_block_id = block_ids[0] if block_ids else self.current_block_id
        # 话题切换标记传递到 get_tree_summary
        self._last_switch = (is_switch, switch_conf, switch_src) if is_switch else None

        for bid in block_ids:
            block = self.blocks.get(bid)
            if block:
                self.summary_engine.check_upgrade(block, turn_index)
        if turn_index % 5 == 0:
            modified = self.regulator.regulate(self.blocks, turn_index)
            if modified:
                self.segmenter.set_threshold(self.regulator.global_split_threshold)
        self._update_temperature(turn_index)
        return block_ids

    def build_context(self, block_id=None):
        active = block_id or self.current_block_id
        if not active:
            return ""
        return self.context_builder.build(self.blocks, active)

    def build_session_context(self, session_id: str = None, max_blocks: int = 8) -> str:
        """A-compatible session context: blocks -> SummaryEngine build_context.

        CLI p10_cmd calls ``build_context(sid, max_blocks=8)`` and needs a
        session-level context; B's native ``build_context(block_id)`` is
        block-level. This is the A-facade-on-B-kernel mapping.
        """
        block_list = list(self.blocks.values())[:max_blocks]
        if not block_list:
            return ""
        return self.summary_engine.build_context(block_list, max_tokens=2000)

    def build_context(self, block_id=None, session_id=None, max_blocks: int = 8) -> str:
        """A-compatible facade: ``build_context(session_id, max_blocks=8)``
        or ``build_context(block_id)`` (B native block-level).

        R6 D3 facade unification: p10_cmd calls with (sid, max_blocks);
        B tests/internal call with (block_id) or no args. Dispatch: when
        ``session_id`` is given (or first arg is not a block id) -> session
        level; otherwise block level.
        """
        if block_id is not None and session_id is None:
            if block_id in self.blocks:
                return self.context_builder.build(self.blocks, block_id)
            session_id = block_id
        if session_id is not None:
            return self.build_session_context(session_id, max_blocks)
        active = self.current_block_id
        if not active:
            return ""
        return self.context_builder.build(self.blocks, active)

    def find_reference(self, ref):
        return self.context_builder.find_by_reference(self.blocks, ref)

    def search(self, query):
        return self.indexer.find_by_reference(query)

    def get_status(self, block_id=None):
        target = block_id or self.current_block_id
        if target and target in self.blocks:
            return self.blocks[target].to_dict()
        return {"error": "block not found"}

    def add_cross_ref(self, source_id, target_id, ref_type='see_also', strength=0.5, source='manual'):
        src = self.blocks.get(source_id)
        tgt = self.blocks.get(target_id)
        if not src or not tgt:
            return False
        src.cross_refs.append(CrossReference(target_block_id=target_id, ref_type=ref_type, strength=strength, created_at_turn=self.turn_count, source=source))
        return True

    def get_cross_refs(self, block_id=None):
        if block_id:
            b = self.blocks.get(block_id)
            return list(getattr(b, 'cross_refs', [])) if b else []
        result = []
        for b in self.blocks.values():
            for cr in getattr(b, 'cross_refs', []):
                result.append({'from': b.block_id, 'to': cr.target_block_id, 'type': cr.ref_type, 'strength': cr.strength})
        return result

    def resolve_reference(self, block_id: str, ref_type: str = "see_also",
                          context: str = "") -> Optional[str]:
        """Resolve a reference from block. Resolution hierarchy:
        1. Explicit cross_refs matching ref_type (like hash bucket lookup)
        2. If >1 match: pick highest strength (hash collision resolved by strength)
        3. If 0 match: fall back to parent_id (tree default)
        4. If no parent: return None
        """
        block = self.blocks.get(block_id)
        if not block:
            return None
        # Step 1: Filter cross_refs by type
        candidates = [cr for cr in getattr(block, "cross_refs", [])
                      if cr.ref_type == ref_type]
        # Step 2: Pick best match
        if candidates:
            best = max(candidates, key=lambda x: x.strength)
            return best.target_block_id
        # Step 3: Fall back to tree parent
        if ref_type in ("continuation", "see_also") and block.parent_id:
            return block.parent_id
        return None

    def get_reachable_blocks(self, block_id: str, max_depth: int = 3) -> list:
        """BFS traversal across tree + cross_ref edges.
        Returns list of (block_id, path_type, depth)."""
        visited = {block_id}
        queue = [(block_id, "root", 0)]
        result = []
        while queue and len(result) < 20:
            bid, ptype, depth = queue.pop(0)
            if depth > 0:
                result.append((bid, ptype, depth))
            if depth >= max_depth:
                continue
            b = self.blocks.get(bid)
            if not b:
                continue
            # Tree edges: children
            for cid in b.child_ids:
                if cid not in visited:
                    visited.add(cid)
                    queue.append((cid, "child", depth+1))
            # Tree edges: parent
            if b.parent_id and b.parent_id not in visited:
                visited.add(b.parent_id)
                queue.append((b.parent_id, "parent", depth+1))
            # Graph edges: cross_refs
            for cr in getattr(b, "cross_refs", []):
                if cr.target_block_id not in visited:
                    visited.add(cr.target_block_id)
                    queue.append((cr.target_block_id, cr.ref_type, depth+1))
        return result

    def get_tree_summary(self):
        v = self.blocks.values()
        ts = getattr(self, '_last_switch', None)
        return {
            "total_blocks": len(self.blocks),
            "active": sum(1 for b in v if b.status == "active"),
            "paused": sum(1 for b in v if b.status == "paused"),
            "cold": sum(1 for b in v if b.status == "cold"),
            "frozen": sum(1 for b in v if b.status == "frozen"),
            "current_block": self.current_block_id,
            "turn": self.turn_count,
            "threshold": self.regulator.global_split_threshold,
            "topic_switch": ts[0] if ts else False,
            "switch_confidence": round(ts[1], 2) if ts else 0.0,
            "switch_source": ts[2] if ts else "",
            'cross_refs_count': sum(1 for b in self.blocks.values() for _ in getattr(b, 'cross_refs', [])),
            'last_cross_ref': str(getattr(self, '_last_cross_ref', '')),
        }

    def _update_temperature(self, current_turn):
        for block in self.blocks.values():
            if block.block_id == self.current_block_id:
                block.status = "active"
            elif current_turn - block.last_active_turn > 30:
                if block.status != "frozen":
                    block.status = "frozen"
                    self.summary_engine.check_upgrade(block, current_turn)
            elif current_turn - block.last_active_turn > 10:
                if block.status != "cold":
                    block.status = "cold"
                    self.summary_engine.check_upgrade(block, current_turn)
            elif current_turn - block.last_active_turn > 5:
                if block.status == "active":
                    block.status = "paused"

    def add_group_reference(self, group_id: str, block_ids: list[str], ref_type: str = "analogy",
                            strength: float = 0.5, context_summary: str = "") -> GroupReference:
        """Add a high-order GroupReference and attach it to all member blocks."""
        gr = GroupReference(group_id=group_id, block_ids=list(block_ids), ref_type=ref_type,
                            strength=strength, context_summary=context_summary,
                            created_at_turn=self.turn_count)
        self.group_ref_index[group_id] = gr
        for bid in block_ids:
            block = self.blocks.get(bid)
            if block:
                block.group_refs.append(gr)
        return gr

    def find_activated_groups(self, block_id: str) -> list[GroupReference]:
        """Return all GroupReferences that contain the given block_id."""
        activated = []
        for gr in self.group_ref_index.values():
            if block_id in gr.block_ids:
                activated.append(gr)
        return activated

    # ── A-compatible facade (Phase 3.1: B kernel behind the A wiring) ──────

    @property
    def _trees(self) -> dict:
        """A-compatible multi-session view over the single B kernel.

        A's manager kept ``_trees: {session_id: DiscourseBlockTree}``; engine,
        subscribers and the monitor all read ``_trees``. B is a single-session
        kernel, so every session maps to this same manager instance (blocks
        are shared). Multi-session isolation is out of scope for Phase 3 and
        noted in IMPL_PROGRESS.
        """
        if not getattr(self, "_session_ids", None):
            self._session_ids = set()
        return {sid: self for sid in self._session_ids}

    def feed(self, text: str, session_id: str, history: list = None,
             cognitive_hints: dict = None) -> object:
        """A-compatible ``feed(text, session_id)`` → B kernel ``ingest_turn``.

        Returns a minimal RouteResult-compatible object so the A wiring
        (engine/subscribers) keeps working unchanged. ``history`` is accepted
        for signature parity; B's header injector maintains its own entity
        cache across turns.
        """
        if not getattr(self, "_session_ids", None):
            self._session_ids = set()
        self._session_ids.add(session_id)
        # C4 (R6): semantic wake — semantically-close sleeping blocks return
        # to Hot before this turn's segmentation.
        try:
            self.summary_engine.semantic_wake(self.blocks, text)
        except Exception:
            pass
        block_ids = self.ingest_turn(self.turn_count + 1, text,
                                     cognitive_hints=cognitive_hints)
        # 多会话隔离（B 内核单实例共享 blocks）: 给本回合块打会话标签，
        # 供图/树按会话过滤（TREE_TIERING 2026-08-07）
        for bid in block_ids or []:
            blk = self.blocks.get(bid)
            if blk is not None:
                blk._session_id = session_id
        # TREE_TIERING: feed 后自动 Hot→Warm 落盘（engine 侧 debounce）
        hook = getattr(self, "_persist_hook", None)
        if hook:
            try:
                hook(session_id)
            except Exception:
                pass
        decision = "continue"
        try:
            if getattr(self, "_last_switch", None) and self._last_switch[0]:
                decision = "fork"
        except Exception:
            pass
        return _RouteResultCompat(decision=decision, block_ids=block_ids or [])

    def get_block_relations(self, session_id: str) -> dict:
        """A-compatible block relationship graph for the association chain."""
        blocks_info = {}
        for bid, b in self.blocks.items():
            blocks_info[bid] = {
                "parent": b.parent_id,
                "children": list(b.child_ids),
                "edus": len(b.atomic_units),
                "entities": list(
                    dict.fromkeys(
                        str(e.text) if hasattr(e, "text") else str(e)
                        for e in getattr(b, "entities", [])
                    )
                ),
                "temperature": getattr(b, "status", "active"),
                # TREE_TIERING（2026-08-07）: 导入块用落盘文本；活块用 summary
                "summary": (
                    getattr(b, "_summary_text", "") or
                    (b.summary.get_best() if getattr(b, "summary", None) else "")
                )[:200],
                "raw_text": (
                    getattr(b, "_raw_text", "") or " ".join(
                        getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
                    )
                ),
                "intent": getattr(b, "primary_intent", "unknown"),
                "depth": getattr(b, "depth", 0),
            }
        relations = []
        for bid, b in self.blocks.items():
            if b.parent_id:
                relations.append({"from": bid, "to": b.parent_id, "type": "child_of"})
            for child in b.child_ids:
                relations.append({"from": bid, "to": child, "type": "parent_of"})
        return {"session_id": session_id, "blocks": blocks_info, "relations": relations}

    # ── OS 式分层持久化（TREE_TIERING_DECISION_20260807）────────────
    # Hot=内存 blocks / Warm=序列化 JSON / Cold=v3_sessions 原文（重建）。
    # export=Hot→Warm（page-out），import=Warm→Hot（page-in）。

    def export_blocks(self, session_id: Optional[str] = None) -> dict:
        """Hot→Warm 落盘序列化（含结构 + 文本，足够重建图与详情视图）。

        session_id 给定 → 只导出该会话的块（Warm 文件按会话隔离）。
        """
        blocks = []
        for bid, b in self.blocks.items():
            if session_id is not None and getattr(b, "_session_id", "") != session_id:
                continue
            blocks.append({
                "block_id": bid,
                "session_id": getattr(b, "_session_id", ""),
                "name": b.name,
                "parent_id": b.parent_id,
                "child_ids": list(b.child_ids),
                "status": b.status,
                "depth": b.depth,
                "created_at_turn": b.created_at_turn,
                "last_active_turn": b.last_active_turn,
                "primary_intent": b.primary_intent,
                "summary": (
                    getattr(b, "_summary_text", "") or
                    (b.summary.get_best() if getattr(b, "summary", None) else "")
                ),
                "raw_text": getattr(b, "_raw_text", "") or " ".join(
                    getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
                ),
                "entities": [
                    str(e.text) if hasattr(e, "text") else str(e)
                    for e in getattr(b, "entities", [])
                ],
                "cross_refs": [
                    {"target": r.target_block_id, "type": r.ref_type,
                     "strength": r.strength}
                    for r in getattr(b, "cross_refs", [])
                ],
            })
        return {
            "blocks": blocks,
            "turn_count": self.turn_count,
            "current_block_id": self.current_block_id,
            "session_ids": list(getattr(self, "_session_ids", set())),
        }

    def import_blocks(self, payload: dict) -> int:
        """Warm→Hot 换入（page-in）。重建结构块，文本挂扩展字段。"""
        from .models import DiscourseBlock
        entries = (payload or {}).get("blocks", []) or []
        for e in entries:
            b = DiscourseBlock(
                block_id=e["block_id"],
                name=e.get("name", ""),
                parent_id=e.get("parent_id"),
                child_ids=list(e.get("child_ids", [])),
                status=e.get("status", "active"),
                depth=int(e.get("depth", 0)),
                created_at_turn=int(e.get("created_at_turn", 0)),
                last_active_turn=int(e.get("last_active_turn", 0)),
                primary_intent=e.get("primary_intent", "unknown"),
            )
            b._session_id = e.get("session_id", "")
            b._summary_text = e.get("summary", "")
            b._raw_text = e.get("raw_text", "")
            b._exported_entities = list(e.get("entities", []))
            b._exported_cross_refs = list(e.get("cross_refs", []))
            self.blocks[b.block_id] = b
        self.turn_count = int((payload or {}).get("turn_count", 0))
        self.current_block_id = (payload or {}).get("current_block_id")
        sids = (payload or {}).get("session_ids")
        if sids:
            self._session_ids = set(sids)
        return len(entries)

    def get_tree(self, session_id: str):
        """A-compatible ``get_tree`` — returns the shared B kernel instance."""
        return self

    # ── A-compatible read helpers (R6 D3: A wiring reads these) ────────────

    @property
    def root_id(self):
        """A-compatible root node id (first block with no parent, else first)."""
        for bid, b in self.blocks.items():
            if not b.parent_id:
                return bid
        return next(iter(self.blocks), "_root")

    @property
    def current_branch(self):
        """A-compatible current branch = current block id."""
        return self.current_block_id

    def get_stats(self, session_id: str) -> dict:
        """A-compatible stats dict (CLI cmd_show / batch3 memory)."""
        return {
            "total_blocks": len(self.blocks),
            "root_id": self.root_id,
            "current_branch": self.current_block_id,
            "max_depth": max(
                (getattr(b, "depth", 0) for b in self.blocks.values()), default=0
            ),
            "turn": self.turn_count,
            # P5: Track A 认知状态（白盒 A19 — 组块边界判据可观测）
            "cognitive_hints": getattr(self, "_last_cognitive_hints", {}),
        }

    def find_block_by_reference(self, session_id: str, reference: str):
        """A-compatible entity/phrase search → block_id or None."""
        ref_lower = (reference or "").lower()
        if not ref_lower:
            return None
        for bid, b in self.blocks.items():
            name = str(getattr(b, "name", "") or "").lower()
            if name and ref_lower in name:
                return bid
            for e in getattr(b, "entities", []):
                ent = str(getattr(e, "text", "") or "").lower()
                if ent and ref_lower in ent:
                    return bid
            for edu in getattr(b, "atomic_units", []):
                raw = str(getattr(edu, "raw_text", "") or "").lower()
                if raw and ref_lower in raw:
                    return bid
        return None

    # ── A-compatible write ops (CLI write_cmd / p7_cmd / api_viz_edit) ─────

    def split_block(self, session_id: str, block_id: str, position: int = 0) -> bool:
        """Split a B block at an EDU position. Returns True on success."""
        b = self.blocks.get(block_id)
        if not b or len(b.atomic_units) <= 1:
            return False
        split_at = max(1, min(position, len(b.atomic_units) - 1))
        left = b.atomic_units[:split_at]
        right = b.atomic_units[split_at:]
        b.atomic_units = left
        import hashlib
        nb = DiscourseBlock(
            block_id="blk_" + hashlib.md5(
                " ".join(getattr(e, "raw_text", "") for e in right).encode()
            ).hexdigest()[:8],
            name=getattr(right[0], "raw_text", "split")[:30],
        )
        for edu in right:
            nb.add_edu(edu)
        nb.parent_id = b.parent_id
        self.blocks[nb.block_id] = nb
        b.child_ids.append(nb.block_id)
        return True

    def merge_blocks(self, session_id: str, block_ids: list) -> bool:
        """Merge sibling blocks into the first one. Returns True on success."""
        if not block_ids or len(block_ids) < 2:
            return False
        target = self.blocks.get(block_ids[0])
        if not target:
            return False
        for bid in block_ids[1:]:
            b = self.blocks.get(bid)
            if not b:
                continue
            for edu in b.atomic_units:
                target.add_edu(edu)
            if b.parent_id and b.parent_id in self.blocks:
                parent = self.blocks[b.parent_id]
                if bid in parent.child_ids:
                    parent.child_ids.remove(bid)
            del self.blocks[bid]
        return True

    def delete_block(self, session_id: str, block_id: str) -> bool:
        """Delete a block; children are reparented to its parent."""
        b = self.blocks.get(block_id)
        if not b:
            return False
        parent_id = b.parent_id
        for child in list(b.child_ids):
            child_b = self.blocks.get(child)
            if child_b:
                child_b.parent_id = parent_id
        if parent_id and parent_id in self.blocks:
            parent = self.blocks[parent_id]
            if block_id in parent.child_ids:
                parent.child_ids.remove(block_id)
        del self.blocks[block_id]
        if self.current_block_id == block_id:
            self.current_block_id = next(iter(self.blocks), None)
        return True

    def promote_block(self, session_id: str, block_id: str, levels: int = 1) -> bool:
        """Move block up in hierarchy. Returns True on success."""
        b = self.blocks.get(block_id)
        if not b:
            return False
        for _ in range(max(1, levels)):
            parent = self.blocks.get(b.parent_id) if b.parent_id else None
            if not parent:
                break
            b.parent_id = parent.parent_id
        return True

    def demote_block(self, session_id: str, block_id: str, levels: int = 1) -> bool:
        """Move block under its first sibling. Returns True on success."""
        b = self.blocks.get(block_id)
        if not b:
            return False
        for _ in range(max(1, levels)):
            parent = self.blocks.get(b.parent_id) if b.parent_id else None
            if not parent:
                break
            siblings = [c for c in parent.child_ids
                        if c != block_id and c in self.blocks]
            if siblings:
                b.parent_id = siblings[0]
        return True

    def compress_cold_blocks(self, session_id: str, llm=None) -> int:
        """Upgrade cold/frozen blocks to v4 summary. Returns upgraded count."""
        upgraded = 0
        current = self.turn_count
        for block in list(self.blocks.values()):
            if getattr(block, "status", "active") not in ("cold", "frozen"):
                continue
            try:
                if self.summary_engine.check_upgrade(block, current):
                    upgraded += 1
            except Exception:
                continue
        return upgraded

    def set_block_summary(self, block_id: str, text: str) -> bool:
        """Set a block's summary text (A-compatible cmd_summary)."""
        b = self.blocks.get(block_id)
        if not b:
            return False
        b.summary.v1_raw = (text or "")[:200]
        if b.summary.version < 2:
            b.summary.version = 2
        return True


class _RouteResultCompat:
    """Minimal stand-in for A's RouteResult (decision + block_ids)."""

    def __init__(self, decision: str = "continue", block_ids: list = None):
        self.decision = decision
        self.block_ids = block_ids or []

    def __repr__(self):
        return f"_RouteResultCompat(decision={self.decision!r}, blocks={len(self.block_ids)})"
