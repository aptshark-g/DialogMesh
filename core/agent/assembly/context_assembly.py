"""Context Assembly — thin integration layer for v6 pipeline.

Wraps the existing context/ modules into a single Assembly point.
Delegates to: ContextAssembler → BudgetAllocator → SubgraphCompiler → Pruner.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ContextAssembly:
    """Unified context assembly for agent_native pipeline.

    Usage:
        ca = ContextAssembly(return_source_funcs={'discourse':..., 'behavior':...})
        result = ca.assemble(route, intents, token_budget=2000)

    Returns compiled subgraph ready for LLM injection.
    """

    def __init__(self, source_funcs: Dict[str, callable] = None,
                 token_budget: int = 2000,
                 use_meta_perspective: bool = True,
                 topic_tree_manager=None):
        """
        Args:
            source_funcs: {'discourse': fn, 'behavior': fn, ...}
            token_budget: max tokens for assembled context
            use_meta_perspective: also compile meta subgraph
            topic_tree_manager: TopicTreeManagerV2 instance for topic context
        """
        self._sources = source_funcs or {}
        self._budget = token_budget
        self._meta_perspective = use_meta_perspective
        self._topic_tree = topic_tree_manager
        self._assembler = None
        self._subgraph_compiler = None
        self._budget_allocator = None
        self._pruner = None

    def _ensure_components(self):
        """Lazy-load context pipeline components."""
        if self._assembler is None:
            try:
                from core.agent.context.assembler import ContextAssembler
                self._assembler = ContextAssembler()
            except Exception:
                logger.debug("ContextAssembler not available, using minimal fallback")
                self._assembler = None

        if self._subgraph_compiler is None:
            try:
                from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
                self._subgraph_compiler = SubgraphCompiler()
            except Exception:
                self._subgraph_compiler = None

        if self._budget_allocator is None:
            try:
                from core.agent.context.budget_allocator import BudgetAllocator
                self._budget_allocator = BudgetAllocator()
            except Exception:
                self._budget_allocator = None

        if self._pruner is None:
            try:
                from core.agent.context.pruner import SubgraphPruner
                self._pruner = SubgraphPruner()
            except Exception:
                self._pruner = None

    def assemble(self, perception_output: dict, token_budget: int = None) -> dict:
        """Main entry: perception output → compiled subgraph context.

        Args:
            perception_output: {route, intents, edus, entities, ...}
            token_budget: override default budget

        Returns:
            {dialogue_context: str, meta_context: str, stats: dict}
        """
        budget = token_budget or self._budget
        self._ensure_components()

        # 1. Gather data from all available sources
        raw_context = self._gather_sources(perception_output)

        # 2. Budget allocation (domain → entity → turn)
        if self._budget_allocator:
            try:
                allocation = self._budget_allocator.allocate(raw_context, budget)
            except Exception:
                allocation = self._fallback_budget(raw_context, budget)
        else:
            allocation = self._fallback_budget(raw_context, budget)

        # 3. Assemble into unified IR
        if self._assembler:
            try:
                assembled = self._assembler.assemble(raw_context, allocation)
            except Exception:
                assembled = self._fallback_assemble(raw_context)
        else:
            assembled = self._fallback_assemble(raw_context)

        # 4. Compile subgraphs (dialogue + meta)
        dialogue_ctx = ""
        meta_ctx = ""
        if self._subgraph_compiler:
            try:
                dialogue_ctx = str(self._subgraph_compiler.compile_dialogue(assembled))
                if self._meta_perspective:
                    meta_ctx = str(self._subgraph_compiler.compile_meta(assembled))
            except Exception:
                dialogue_ctx = self._fallback_to_text(assembled)
        else:
            dialogue_ctx = self._fallback_to_text(assembled)

        # 5. Prune if over budget
        if self._pruner and len(dialogue_ctx) > budget * 4:
            try:
                dialogue_ctx = self._pruner.prune(dialogue_ctx, budget)
            except Exception:
                dialogue_ctx = dialogue_ctx[:budget * 4]

        return {
            "dialogue_context": dialogue_ctx,
            "meta_context": meta_ctx,
            "stats": {
                "budget": budget,
                "actual_tokens": len(dialogue_ctx) // 4,
                "sources_used": list(raw_context.keys()),
            }
        }

    def _gather_sources(self, perception: dict) -> dict:
        """Gather data from all registered sources + built-in topic_tree."""
        gathered = {}
        # Built-in: TopicTree
        if self._topic_tree:
            try:
                # T2: V2 get_current_branch 返回 TopicNode 列表 → 序列化为 dict
                branch = self._topic_tree.get_current_branch()
                gathered["topic_tree"] = [
                    n.to_dict() if hasattr(n, "to_dict") else str(n)
                    for n in branch
                ]
            except Exception:
                pass
        for name, fn in self._sources.items():
            try:
                data = fn(perception)
                if data:
                    gathered[name] = data
            except Exception:
                pass
        return gathered

    def _fallback_budget(self, raw: dict, budget: int) -> dict:
        """Uniform budget when allocator unavailable."""
        n = max(len(raw), 1)
        per_source = budget // n
        return {k: per_source for k in raw}

    def _fallback_assemble(self, raw: dict) -> list:
        """Linear concatenation when assembler unavailable."""
        return [f"[{k}] {str(v)[:200]}" for k, v in raw.items()]

    def _fallback_to_text(self, assembled: list) -> str:
        return "\n".join(str(item) for item in (assembled or []))
