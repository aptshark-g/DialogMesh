"""Subgraph Compiler — cross-chain context assembly with dual perspectives.

Design: BUSINESS_CHAIN_10
Two perspectives sharing one compiler:
  dialogue_subgraph: for LLM response generation (narrow+deep)
  meta_subgraph:     for meta-cognition review (wide+shallow)

Data sources: discourse tree, behavior chain, association chain, 
              engineering chain, profile/inertia, version control.
"""
from __future__ import annotations
import json, os, time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DomainEntry:
    domain: str
    content: str
    confidence: float
    source: str
    token_estimate: int = 0


@dataclass
class SubgraphContext:
    perspective: str          # "dialogue" | "meta"
    entries: List[DomainEntry]
    total_tokens: int
    budget: int
    domains: Dict[str, float]  # domain → budget allocation


class SubgraphCompiler:
    """Compiles cross-domain context for two perspectives.
    
    Perspective 1 — dialogue_subgraph:
      Purpose: provide context for LLM response generation
      Style: narrow+deep — focuses on current topic with high-quality detail
      Domains: D(35%) + K(20%) + E(5%) + B(15%) + R(10%) + P(10%) + F(5%)
    
    Perspective 2 — meta_subgraph:
      Purpose: provide context for meta-cognition review/retrospection
      Style: wide+shallow — covers multiple chains, summary-level evidence
      Domains: V(25%) + E(30%) + M(15%) + I(15%) + P(10%) + Q(5%)
    """

    def __init__(self, engine=None, budget: int = 2000):
        self._engine = engine
        self._budget = budget

    # ── Perspective 1: Dialogue Subgraph ──

    def compile_dialogue(self, intent: str = "general_query", 
                         extra_budget: int = 0) -> SubgraphContext:
        """Compile context for LLM response generation."""
        budget = self._budget + extra_budget
        alloc = {"D": 0.35, "K": 0.20, "E": 0.05, "B": 0.15, "R": 0.10, "P": 0.10, "F": 0.05}
        entries: List[DomainEntry] = []

        eng = self._engine
        if not eng: return SubgraphContext("dialogue", entries, 0, budget, alloc)

        # D: Discourse tree (current topic + related blocks)
        dt = getattr(eng, '_discourse_tree', None)
        if dt:
            trees = getattr(dt, '_trees', {})
            for tree_id, tree in list(trees.items())[:1]:
                blocks = getattr(tree, 'blocks', {})
                for bid, block in list(blocks.items())[:5]:
                    topic = getattr(block, 'topic', '')[:200]
                    if topic:
                        entries.append(DomainEntry("D", topic, 0.8, "discourse_tree", len(topic)//2))

        # K: Engineering constraints
        ek = getattr(eng, '_engineering_knowledge', None)
        if ek and hasattr(ek, 'get_by_type'):
            try:
                from core.agent.v3_2.engineering_chain.models import KnowledgeType
                for n in ek.get_by_type(KnowledgeType.CONSTRAINT)[:3]:
                    entries.append(DomainEntry("K", str(getattr(n, 'name', '?'))[:200], 0.8, "engineering", 50))
            except Exception: pass

        # E: Engineering module status
        objects = getattr(eng, '_world_objects', {})
        for name in list(objects.keys())[:3]:
            entries.append(DomainEntry("E", name[:100], 0.6, "world_objects", 30))

        # B: Behavior signals
        bg = getattr(eng, '_behavior_graph_adapter', None)
        if bg and hasattr(bg, 'stats'):
            try:
                stats = bg.stats() if callable(bg.stats) else {}
                s = str(stats)[:200]
                if s: entries.append(DomainEntry("B", s, 0.5, "behavior_graph", len(s)//2))
            except Exception: pass

        # P: Profile summary
        ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
        if ocean:
            top = ocean.top_dimensions(3) if hasattr(ocean, 'top_dimensions') else []
            mbti = ocean.to_mbti() if hasattr(ocean, 'to_mbti') else "?"
            entries.append(DomainEntry("P", f"MBTI≈{mbti} | top={top}", 0.7, "ocean_profile", 40))

        # F: OCEAN feedback
        if ocean:
            dims = getattr(ocean, 'dims', {})
            entries.append(DomainEntry("F", str(dict(list(dims.items())[:5]))[:200], 0.6, "ocean_dims", 60))

        return SubgraphContext("dialogue", entries, self._count_tokens(entries), budget, alloc)

    # ── Perspective 2: Meta Subgraph ──

    def compile_meta(self, review_target: str = "", extra_budget: int = 0) -> SubgraphContext:
        """Compile context for meta-cognition review."""
        budget = self._budget + extra_budget
        alloc = {"V": 0.25, "E": 0.30, "M": 0.15, "I": 0.15, "P": 0.10, "Q": 0.05}
        entries: List[DomainEntry] = []

        eng = self._engine
        if not eng: return SubgraphContext("meta", entries, 0, budget, alloc)

        # V: Version diff
        vcs = getattr(eng, '_vcs', None)
        if vcs and review_target:
            # Try to find relevant version history
            for cat in ["parameters", "rules", "profile"]:
                store = vcs.store(cat)
                latest = store.latest(review_target)
                if latest:
                    entries.append(DomainEntry("V", str(latest.diff_summary)[:200], 0.9, "version_control", 80))

        # E: Multi-chain evidence
        # Association chain
        rs = getattr(getattr(eng, '_world_provider', None), 'relation_substrate', None)
        if rs and hasattr(rs, 'query'):
            edges = rs.query()[:3] if callable(getattr(rs, 'query', None)) else []
            for e in edges:
                s = f"{getattr(e,'source','?')}→{getattr(e,'target','?')} strength={getattr(e,'semantic_strength','?')}"
                entries.append(DomainEntry("E", s[:150], 0.6, "relation_substrate", 40))

        # M: Meta operation history
        meta = getattr(eng, '_meta', None)
        if meta:
            audit = meta.self_audit()
            entries.append(DomainEntry("M", str(audit)[:200], 0.8, "meta_self_audit", 60))

        # I: Inertia impact (placeholder)
        entries.append(DomainEntry("I", "inertia: pending implementation", 0.5, "inertia", 30))

        # P: Profile summary
        ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
        if ocean:
            mbti = ocean.to_mbti() if hasattr(ocean, 'to_mbti') else "?"
            entries.append(DomainEntry("P", f"MBTI≈{mbti}", 0.7, "ocean_profile", 20))

        # Q: Review target detail
        if review_target:
            entries.append(DomainEntry("Q", review_target[:200], 0.9, "review_target", 40))

        return SubgraphContext("meta", entries, self._count_tokens(entries), budget, alloc)

    # ── Helpers ──

    def _count_tokens(self, entries: List[DomainEntry]) -> int:
        return sum(e.token_estimate or len(e.content) // 2 for e in entries)

    def assemble_prompt(self, ctx: SubgraphContext) -> str:
        """Convert subgraph context to LLM prompt format."""
        lines = [f"[Context — {ctx.perspective} perspective]"]
        for e in ctx.entries:
            lines.append(f"  [{e.domain}] {e.content}")
        return "\n".join(lines)
