# -*- coding: utf-8 -*-
"""Topic Tree Manager V1 — 已归档（A17 记录不删）。

归档原因（T4 归一，2026-08-05）:
  V2（manager_v2.py）= 唯一话题树内核；V1 包装类零真实消费方
  （engine._topic_tree 从未被赋值；integration_bridge 期望的
  route/get_node/save_to_graph_store API 本就不存在于 V1，路径早已断链）。
  本文件仅作历史保留，不再被 core/agent/topic_tree/manager.py 引用。

独特组件资产（保留原位，供后续接线）:
  - heat_model.AdaptiveHeatModel: A15 温度系统（ARC T1/T2）素材
  - fact_store.FactStore/RelationMetadataStore: 画像/上下文接线素材
  - context.DualPerspectiveContext 等: 双视角上下文素材
"""

from __future__ import annotations
from typing import List, Optional
import time, logging
from core.agent.topic_tree.fact_store import FactBlock, FactStore, RelationMetadataStore
from core.agent.topic_tree.heat_model import AdaptiveHeatModel
from core.agent.topic_tree.context import (
    DualPerspectiveContext, MultiPerspectiveBranchView, BehaviorDrivenRefresh, Summary
)

logger = logging.getLogger(__name__)


class TopicTreeManager:
    """Entry point for Topic Tree in the engine pipeline.

    Usage in engine.on_event():
        tree.touch(message_id, content_text)
        tree.record_entities(message_id, ["entity1", "entity2"])
        tree.record_relation(message_id, prev_message_id, "sequential")

        ctx = tree.assemble_context(active_node=message_id, token_budget=2000)
        # Inject ctx into LLM prompt
    """

    def __init__(self):
        self.facts = FactStore()
        self.relations = RelationMetadataStore()
        self.heat = AdaptiveHeatModel()
        self.context = DualPerspectiveContext(self.facts, self.relations)
        self.branches = MultiPerspectiveBranchView()
        self.refresh = BehaviorDrivenRefresh()
        self._last_message_id: Optional[str] = None
        self._summary_cache: dict = {}  # {node_id: Summary}

    # ── Ingestion (called from engine.on_event) ──

    def touch(self, message_id: str, content: str, entities: List[str] = None):
        """Record a new message — creates FactBlock, updates heat."""
        fact = FactBlock(
            block_id=message_id,
            content=content,
            entities=entities or [],
            source_chain="discourse"
        )
        self.facts.put(fact)
        self.heat.touch(message_id)
        self.context.touch(message_id)

        # Record relation to previous message
        if self._last_message_id and self._last_message_id != message_id:
            self.relations.update(self._last_message_id, message_id, "sequential")

        self._last_message_id = message_id

    def on_correction(self, message_id: str, detail: str = ""):
        """User corrected — penalize heat, mark dirty."""
        self.heat.on_correction(message_id)
        self.context.on_correction(message_id)
        self.refresh.on_correction(message_id, detail)

    def on_topic_switch(self):
        """Topic changed — adjust heat model, trigger refresh."""
        self.heat.on_branch_switch()
        self.context.on_branch_switch()
        # Mark active area as potentially dirty
        if self._last_message_id:
            self.refresh.on_topic_switch(self._last_message_id)

    # ── Context Assembly (called before LLM) ──

    def assemble_context(self, active_node: str = None, token_budget: int = 2000) -> List[Summary]:
        """Build the dual-perspective context for LLM injection."""
        node = active_node or self._last_message_id
        if not node:
            return []

        # Refresh any dirty summaries
        self._refresh_if_needed(node)

        return self.context.assemble(node, token_budget)

    def _refresh_if_needed(self, node_id: str):
        """Check and regenerate summaries for dirty blocks."""
        for layer in [1, 2, 3]:
            if self.refresh.should_refresh(node_id, layer):
                fact = self.facts.get(node_id)
                if fact:
                    # L1: simple truncation (no LLM needed for <200 tokens)
                    content = fact.content[:200]
                    summary = Summary(
                        node_id=node_id, content=content, layer=layer,
                        token_count=len(content)
                    )
                    self._summary_cache[node_id] = summary
                    self.refresh.mark_refreshed(node_id)

    # ── Branch management ──

    def register_branch_perspective(self, module: str, node_id: str, branch_id: str, reason: str = ""):
        """Register a branch definition from any module (discourse/graph/association/engineering)."""
        self.branches.register(module, node_id, branch_id, reason)

    def get_branch_view(self, node_id: str) -> dict:
        return self.branches.get_view(node_id)

    # ── Stats ──

    @property
    def stats(self) -> dict:
        return {
            "facts": len(self.facts),
            "relations": len(self.relations._current),
            "heat": self.heat.stats(),
            "dirty_blocks": len(self.refresh._dirty_blocks),
            "branch_perspectives": sum(len(v) for v in self.branches._perspectives.values()),
        }
