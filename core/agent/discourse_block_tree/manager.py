"""DiscourseBlockTreeManager - core orchestrator"""
import hashlib
from typing import Dict, List, Optional
from .models import DiscourseBlock, DiscourseEntity
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

    def ingest_turn(self, turn_index, text):
        self.turn_count = turn_index
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
