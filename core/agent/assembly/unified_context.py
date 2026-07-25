"""Unified Context — merger of context/ pipeline + context_manager/ runtime.

Two independent subsystems merged into a single Context stack:

  context/ pipeline (Assembler + Budget + Prune + IR + Sources + Store + Window)
    ×
  context_manager/ runtime (DiscourseManager + SemanticIndex + ContextLayer)

→ DiscourseManager becomes a ContextSource for the pipeline.
→ ContextLayer injects system context at assembly final stage.
→ SemanticIndex backs the topic_tree source.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class UnifiedContext:
    """Single entry point for all context operations.

    Replaces: ContextAssembly wrapper + separate DiscourseManager.

    Architecture:
        pipeline layer: Assembler → BudgetAllocator → CrossDomainIR → Pruner
        runtime layer:  DiscourseManager → SemanticIndex → ContextLayer
        bridge:         DiscourseManager implements ContextSource interface
    """

    def __init__(self, token_budget: int = 2000,
                 discourse_db_path: str = None,
                 use_meta_perspective: bool = True):
        self._budget = token_budget
        self._meta_perspective = use_meta_perspective
        self._db_path = discourse_db_path or "data/discourse.db"
        self._loaded = False

        # Lazy-loaded components
        self._assembler = None
        self._budget_allocator = None
        self._pruner = None
        self._ir_compiler = None
        self._store = None
        self._window = None

        # context_manager/ components
        self._discourse_manager = None
        self._semantic_index = None
        self._context_layer = None

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True

        # ── context/ pipeline components ──
        try:
            from core.agent.context.assembler import ContextAssembler
            self._assembler = ContextAssembler()
        except Exception as e:
            logger.debug("ContextAssembler unavailable: %s", e)

        try:
            from core.agent.context.budget_allocator import BudgetAllocator
            self._budget_allocator = BudgetAllocator()
        except Exception as e:
            logger.debug("BudgetAllocator unavailable: %s", e)

        try:
            from core.agent.context.pruner import SubgraphPruner
            self._pruner = SubgraphPruner()
        except Exception as e:
            logger.debug("SubgraphPruner unavailable: %s", e)

        try:
            from core.agent.context.store import InMemoryContextStore
            self._store = InMemoryContextStore()
        except Exception as e:
            logger.debug("ContextStore unavailable: %s", e)

        try:
            from core.agent.context.window import ContextCompressor
            self._window = ContextCompressor()
        except Exception as e:
            logger.debug("ContextCompressor unavailable: %s", e)

        # ── context_manager/ runtime components ──
        try:
            from core.agent.context_manager.discourse_manager import DiscourseManager
            self._discourse_manager = DiscourseManager(self._db_path)
        except Exception as e:
            logger.debug("DiscourseManager unavailable: %s", e)

        try:
            from core.agent.context_manager.semantic_index import SemanticIndex
            self._semantic_index = SemanticIndex()
        except Exception as e:
            logger.debug("SemanticIndex unavailable: %s", e)

        try:
            from core.agent.context_manager.context_layer import ContextLayer
            self._context_layer = ContextLayer()
        except Exception as e:
            logger.debug("ContextLayer unavailable: %s", e)

    # ═══ Public API ═══

    def assemble(self, perception_output: dict, token_budget: int = None) -> dict:
        """Full assembly: runtime data → pipeline → compiled subgraph.

        Args:
            perception_output: {route, intents, edus, entities, ...}
            token_budget: override default

        Returns:
            {dialogue_context: str, meta_context: str, stats: dict}
        """
        budget = token_budget or self._budget
        self._ensure_loaded()

        # 1. Gather runtime data from DiscourseManager + SemanticIndex
        raw = self._gather_runtime(perception_output)

        # 2. Budget allocation
        allocation = self._allocate(raw, budget)

        # 3. Assemble into intermediate representation
        assembled = self._assemble(raw, allocation)

        # 4. Compile subgraphs (dialogue + meta)
        dialogue_ctx, meta_ctx = self._compile_subgraphs(assembled, budget)

        # 5. Prune
        dialogue_ctx = self._prune_if_needed(dialogue_ctx, budget)

        # 6. Inject system context layer
        dialogue_ctx = self._inject_system_layer(dialogue_ctx, perception_output)

        return {
            "dialogue_context": dialogue_ctx,
            "meta_context": meta_ctx,
            "stats": {
                "budget": budget,
                "actual_tokens": len(dialogue_ctx) // 4,
                "sources_used": list(raw.keys()),
                "discourse_turns": self._discourse_turn_count(),
            }
        }

    def record_turn(self, text: str, response: str, session_id: str = "default",
                    metadata: dict = None):
        """Record a conversation turn into DiscourseManager."""
        self._ensure_loaded()
        if self._discourse_manager:
            try:
                self._discourse_manager.add_turn(text, response, session_id)
            except Exception as e:
                logger.debug("record_turn failed: %s", e)

    # ═══ Internal pipeline stages ═══

    def _gather_runtime(self, perception: dict) -> dict:
        """Gather runtime data from DiscourseManager + SemanticIndex."""
        gathered = {}

        if self._discourse_manager:
            try:
                turns = getattr(self._discourse_manager, 'recent_turns', [])
                if turns:
                    gathered["discourse"] = turns
            except Exception:
                pass

        if self._semantic_index:
            try:
                query = perception.get("text", "")
                if query:
                    results = self._semantic_index.search(query, top_k=5)
                    if results:
                        gathered["semantic"] = results
            except Exception:
                pass

        return gathered

    def _allocate(self, raw: dict, budget: int) -> dict:
        if self._budget_allocator:
            try:
                return self._budget_allocator.allocate(raw, budget)
            except Exception:
                pass
        n = max(len(raw), 1)
        return {k: budget // n for k in raw}

    def _assemble(self, raw: dict, allocation: dict) -> list:
        if self._assembler:
            try:
                return self._assembler.assemble(raw, allocation)
            except Exception:
                pass
        return [f"[{k}] {str(v)[:200]}" for k, v in raw.items()]

    def _compile_subgraphs(self, assembled: list, budget: int) -> tuple:
        dialogue_ctx = ""
        meta_ctx = ""
        try:
            from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
            compiler = SubgraphCompiler(budget=budget)
            dialogue_ctx = str(compiler.compile_dialogue(assembled))
            if self._meta_perspective:
                meta_ctx = str(compiler.compile_meta(assembled))
        except Exception:
            dialogue_ctx = "\n".join(str(item) for item in assembled)
        return dialogue_ctx, meta_ctx

    def _prune_if_needed(self, ctx: str, budget: int) -> str:
        if self._pruner and len(ctx) > budget * 4:
            try:
                return self._pruner.prune(ctx, budget)
            except Exception:
                pass
        return ctx[:budget * 4]

    def _inject_system_layer(self, ctx: str, perception: dict) -> str:
        if self._context_layer:
            try:
                layer_context = self._context_layer.build(perception)
                return layer_context + "\n" + ctx if layer_context else ctx
            except Exception:
                pass
        return ctx

    def _discourse_turn_count(self) -> int:
        if self._discourse_manager:
            try:
                turns = getattr(self._discourse_manager, 'recent_turns', [])
                return len(turns)
            except Exception:
                pass
        return 0
