"""DiscourseBlockTree — conversation-to-tree compiler.

Design: docs/v3.0/design_discourse_block_tree_v2.md

Three-stage pipeline:
  1. HeaderInjector: pronoun resolution via session entity cache
  2. SyntacticDecomposer: EDU splitting (reuses TieredParser)
  3. MacroMicroQuantizer: BGE fast path + 9-dim full formula for gray zone

Output: DiscourseBlockTree with route decisions (continue/fork/attach/merge).
"""
from __future__ import annotations
import re, time, uuid, logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ── Stage 1: HeaderInjector ──
class HeaderInjector:
    """Pronoun resolution via session entity cache.

    Priority: same-turn explicit → session recent → causal KB → history pool.
    """

    NEG_MARKERS = {"不", "没", "非", "别", "not", "no", "don't"}
    UNC_MARKERS = {"可能", "也许", "大概", "maybe", "perhaps"}
    IMP_MARKERS = {"请", "帮我", "给我", "scan", "patch", "hook"}

    PRONOUNS = ["这个", "那个", "它", "他", "这", "那", "this", "that", "it"]

    def __init__(self):
        self._entity_cache: Dict[str, List[str]] = {}  # session_id → entities
        self._last_entity: Dict[str, Optional[str]] = {}

    def inject(self, text: str, session_id: str, history: List[str] = None) -> str:
        if history:
            self._update_cache(session_id, history)
        for pronoun in self.PRONOUNS:
            if pronoun in text:
                resolved = self._resolve(pronoun, text, session_id)
                if resolved:
                    return text.replace(pronoun, f"[{resolved}]", 1)
        return text

    def _update_cache(self, session_id: str, history: List[str]):
        cache = self._entity_cache.setdefault(session_id, [])
        for h in history[-5:]:
            for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', h):
                cache.append(m.group())
            for m in re.finditer(r'[\u4e00-\u9fff]{2,4}', h):
                cache.append(m.group())

    def _resolve(self, pronoun: str, text: str, session_id: str) -> Optional[str]:
        # Same-turn: entity before pronoun
        pos = text.find(pronoun)
        if pos > 0:
            before = text[:pos]
            ents = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', before)
            if ents:
                return ents[-1]
        # Session recent
        last = self._last_entity.get(session_id)
        if last:
            return last
        # History pool
        pool = self._entity_cache.get(session_id, [])
        return pool[-1] if pool else None


# ── Stage 2: SyntacticDecomposer ──
@dataclass
class EDU:
    edu_id: str
    raw_text: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    obj: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    negation: bool = False
    uncertainty: bool = False
    imperative: bool = False
    position: int = 0
    parse_failed: bool = False

    @property
    def signature(self) -> str:
        parts = []
        if self.negation: parts.append("NOT")
        if self.uncertainty: parts.append("MAYBE")
        if self.subject: parts.append(self.subject)
        if self.predicate: parts.append(self.predicate or "")
        if self.obj: parts.append(self.obj)
        return " ".join(filter(None, parts))


class SyntacticDecomposer:
    """EDU splitting via TieredParser + jieba."""

    MAX_CLAUSES = 5

    def decompose(self, text: str) -> List[EDU]:
        clauses = [s.strip() for s in re.split(r'[。！？；，.!?;,\n]+', text) if len(s.strip()) > 3]
        edus = []
        for i, clause in enumerate(clauses[:self.MAX_CLAUSES]):
            try:
                from core.agent.v4.tiered.parser import RuleDecomposer
                parsed = RuleDecomposer().parse(clause)
                entities = []
                for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', clause):
                    entities.append(m.group())
                # Also extract Chinese keywords as entities
                if not entities:
                    try:
                        import jieba
                        keywords = [w for w in jieba.cut(clause) if len(w) >= 2 and all(c >= '\u4e00' and c <= '\u9fff' for c in w)]
                        entities = keywords[:5]
                    except Exception:
                        pass
                edu = EDU(
                    edu_id=f"edu_{uuid.uuid4().hex[:8]}",
                    raw_text=clause,
                    subject=parsed.subject,
                    predicate=parsed.predicate,
                    obj=parsed.object,
                    entities=entities or parsed.entities,
                    negation=parsed.negation,
                    uncertainty=parsed.uncertainty,
                    imperative=parsed.imperative,
                    position=i,
                )
            except Exception:
                edu = EDU(edu_id=f"edu_{uuid.uuid4().hex[:8]}", raw_text=clause,
                         parse_failed=True, position=i)
            edus.append(edu)
        return edus


# ── Stage 3: MacroMicroQuantizer ──
@dataclass
class CohesionScore:
    total: float
    macro: float
    micro: float
    decision: str  # "continue" | "fork" | "gray_zone"

    @property
    def is_extreme(self) -> bool:
        return self.total > 0.75 or self.total < 0.25


class MacroMicroQuantizer:
    """Cohesion computation: BGE fast path + 9-dim full formula for gray zone."""

    GRAY_LOW, GRAY_HIGH = 0.25, 0.75
    MACRO_WEIGHTS = {"cos_sim": 0.35, "intent": 0.25, "topic_embed": 0.20, "time_decay": 0.20}
    MICRO_WEIGHTS = {"entity": 0.30, "causal": 0.25, "subject_cont": 0.20,
                     "ref_inherit": 0.15, "lexical": 0.10}

    def __init__(self):
        self._bge = None

    def _ensure_bge(self):
        if self._bge is not None:
            return
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            self._bge = SemanticEncoder()
        except Exception:
            self._bge = False

    def compute(self, edu_a: EDU, edu_b: EDU) -> CohesionScore:
        self._ensure_bge()

        # Entity overlap fast path: primary signal for topic continuation
        a_ents = set(edu_a.entities)
        b_ents = set(edu_b.entities)
        union = a_ents | b_ents
        if union:
            entity_overlap = len(a_ents & b_ents) / len(union)
            if entity_overlap > 0.5:
                return CohesionScore(0.8, 0.6, entity_overlap, "continue")
            if entity_overlap == 0 and len(a_ents) > 0 and len(b_ents) > 0:
                return CohesionScore(0.15, 0.1, 0.0, "fork")

        # BGE semantic fast path
        if self._bge and self._bge is not False:
            import numpy as np
            try:
                va = self._bge.encode(edu_a.raw_text)
                vb = self._bge.encode(edu_b.raw_text)
                total = float(np.dot(va, vb))
                if total > 0.70:
                    return CohesionScore(total, total, 0.0, "continue")
                if total < 0.20:
                    return CohesionScore(total, total, 0.0, "fork")
            except Exception:
                pass

        # Full 9-dim formula (gray zone or BGE unavailable)
        return self._compute_full(edu_a, edu_b)

    def _compute_full(self, a: EDU, b: EDU) -> CohesionScore:
        macro = self._macro_score(a, b)
        micro = self._micro_score(a, b)
        total = 0.6 * macro + 0.4 * micro
        if total > self.GRAY_HIGH:
            return CohesionScore(total, macro, micro, "continue")
        elif total < self.GRAY_LOW:
            return CohesionScore(total, macro, micro, "fork")
        return CohesionScore(total, macro, micro, "gray_zone")

    def _macro_score(self, a: EDU, b: EDU) -> float:
        scores = []
        # cos_sim placeholder (already computed by BGE if available)
        scores.append(0.5 * self.MACRO_WEIGHTS["cos_sim"])
        # intent match
        if a.imperative == b.imperative or a.negation == b.negation:
            scores.append(1.0 * self.MACRO_WEIGHTS["intent"])
        else:
            scores.append(0.3 * self.MACRO_WEIGHTS["intent"])
        # topic embedding (simplified: entity overlap)
        overlap = len(set(a.entities) & set(b.entities))
        total_e = len(set(a.entities) | set(b.entities)) or 1
        scores.append((overlap / total_e) * self.MACRO_WEIGHTS["topic_embed"])
        # time decay (adjacent EDUs = no decay)
        scores.append(1.0 * self.MACRO_WEIGHTS["time_decay"])
        return sum(scores)

    def _micro_score(self, a: EDU, b: EDU) -> float:
        scores = []
        # entity overlap
        overlap = len(set(a.entities) & set(b.entities))
        total = len(set(a.entities) | set(b.entities)) or 1
        scores.append((overlap / total) * self.MICRO_WEIGHTS["entity"])
        # causal chain: same predicate = likely same action chain
        if a.predicate and b.predicate and a.predicate == b.predicate:
            scores.append(0.8 * self.MICRO_WEIGHTS["causal"])
        else:
            scores.append(0.2 * self.MICRO_WEIGHTS["causal"])
        # subject continuity
        if a.subject and b.subject and a.subject == b.subject:
            scores.append(1.0 * self.MICRO_WEIGHTS["subject_cont"])
        else:
            scores.append(0.1 * self.MICRO_WEIGHTS["subject_cont"])
        # reference inheritance: obj of A appears in B
        if a.obj and b.raw_text and a.obj in b.raw_text:
            scores.append(0.9 * self.MICRO_WEIGHTS["ref_inherit"])
        else:
            scores.append(0.1 * self.MICRO_WEIGHTS["ref_inherit"])
        # lexical chain
        a_words = set(re.findall(r'\w+', a.raw_text.lower()))
        b_words = set(re.findall(r'\w+', b.raw_text.lower()))
        lex_overlap = len(a_words & b_words)
        lex_total = len(a_words | b_words) or 1
        scores.append((lex_overlap / lex_total) * self.MICRO_WEIGHTS["lexical"])
        return sum(scores)


# ── DiscourseBlock + Tree ──
@dataclass
class DiscourseBlock:
    block_id: str
    edus: List[EDU] = field(default_factory=list)
    children: List[str] = field(default_factory=list)  # child block_ids
    parent: Optional[str] = None
    depth: int = 0
    summary: str = ""
    created_at: float = field(default_factory=time.time)
    temperature: str = "active"  # active | paused | cold | frozen

    @property
    def text(self) -> str:
        return " ".join(e.raw_text for e in self.edus)

    @property
    def entity_signature(self) -> List[str]:
        ents = set()
        for e in self.edus:
            ents.update(e.entities)
        return list(ents)


class DiscourseBlockTree:
    """Conversation tree: root + branches keyed by block_id."""

    def __init__(self):
        self.blocks: Dict[str, DiscourseBlock] = {}
        self.root_id: Optional[str] = None
        self.current_branch: Optional[str] = None

    def add_block(self, block: DiscourseBlock, parent_id: str = None):
        self.blocks[block.block_id] = block
        if parent_id and parent_id in self.blocks:
            block.parent = parent_id
            block.depth = self.blocks[parent_id].depth + 1
            self.blocks[parent_id].children.append(block.block_id)
        if self.root_id is None:
            self.root_id = block.block_id

    def path_to_root(self, block_id: str) -> List[DiscourseBlock]:
        path = []
        bid = block_id
        while bid and bid in self.blocks:
            path.append(self.blocks[bid])
            bid = self.blocks[bid].parent
        return list(reversed(path))

    def serialize_for_context(self, block_id: str, max_blocks: int = 8) -> str:
        """Build tree context string for LLM injection."""
        path = self.path_to_root(block_id)
        lines = []

        # Active branch: full text
        lines.append("[Active Branch]")
        for blk in path[-3:]:  # last 3 blocks on current path
            indent = "  " * blk.depth
            text = blk.text[:200]
            lines.append(f"{indent}[B{blk.block_id[:6]}] {text}")

        # Sibling context
        if path:
            parent = path[-1].parent if len(path) > 1 else None
            if parent and parent in self.blocks:
                siblings = [b for b in self.blocks[parent].children if b != block_id]
                if siblings:
                    lines.append("\n[Related Topics]")
                    for sib in siblings[:3]:
                        blk = self.blocks.get(sib)
                        if blk:
                            lines.append(f"  → {blk.text[:100]}")
        return "\n".join(lines)


# ── DiscourseBlockTreeManager ──
class RouteDecision(Enum):
    CONTINUE = "continue"
    FORK = "fork"
    ATTACH = "attach"
    MERGE = "merge"


@dataclass
class RouteResult:
    decision: RouteDecision
    target_block_id: Optional[str] = None
    cohesion: Optional[CohesionScore] = None


class DiscourseBlockTreeManager:
    """Orchestrates the three-stage pipeline per conversation turn.

    Usage:
        mgr = DiscourseBlockTreeManager()
        mgr.feed("帮我写Python函数。对了，召回那个方案怎么样？", session_id="s1")
        ctx = mgr.build_context(session_id="s1")
    """

    def __init__(self):
        self._trees: Dict[str, DiscourseBlockTree] = {}
        self._injector = HeaderInjector()
        self._decomposer = SyntacticDecomposer()
        self._quantizer = MacroMicroQuantizer()
        self._last_block: Dict[str, str] = {}  # session_id → last block_id

    def feed(self, text: str, session_id: str, history: List[str] = None) -> RouteResult:
        """Process one user turn. Returns route decision."""
        tree = self._trees.setdefault(session_id, DiscourseBlockTree())

        # Stage 1: resolve pronouns
        resolved = self._injector.inject(text, session_id, history)

        # Stage 2: decompose into EDUs
        edus = self._decomposer.decompose(resolved)
        if not edus:
            return RouteResult(RouteDecision.CONTINUE)

        # Stage 3: segment EDUs into blocks, route each
        last_bid = self._last_block.get(session_id)
        decisions = []
        turn_started = False  # ensure first EDU of each turn gets its own block

        for i, edu in enumerate(edus):
            if i == 0:
                # First EDU of turn: always check if we should fork from previous turn
                if last_bid and last_bid in tree.blocks:
                    prev_edus = tree.blocks[last_bid].edus
                    if prev_edus:
                        cohesion = self._quantizer.compute(prev_edus[-1], edu)
                        if cohesion.decision == "fork":
                            # Fork from last turn's block
                            parent = tree.blocks[last_bid].parent if last_bid in tree.blocks else tree.root_id
                            block = self._new_block([edu], tree, parent)
                            last_bid = block.block_id
                            decisions.append(RouteDecision.FORK)
                            continue
                # Otherwise continue: add to last block or create new
                if last_bid and last_bid in tree.blocks:
                    tree.blocks[last_bid].edus.append(edu)
                    decisions.append(RouteDecision.CONTINUE)
                else:
                    block = self._new_block([edu], tree)
                    last_bid = block.block_id
                    decisions.append(RouteDecision.CONTINUE)
            elif self._should_merge(edus[i - 1], edu):
                # Continue with previous block
                if last_bid and last_bid in tree.blocks:
                    tree.blocks[last_bid].edus.append(edu)
                    decisions.append(RouteDecision.CONTINUE)
                else:
                    block = self._new_block([edu], tree)
                    last_bid = block.block_id
                    decisions.append(RouteDecision.CONTINUE)
            else:
                # Fork: new block
                cohesion = self._quantizer.compute(edus[i - 1], edu)
                if cohesion.decision == "fork":
                    parent = tree.blocks[last_bid].parent if last_bid and last_bid in tree.blocks else tree.root_id
                    block = self._new_block([edu], tree, parent)
                    last_bid = block.block_id
                    decisions.append(RouteDecision.FORK)
                else:
                    # Continue (cohesion > 0.25)
                    if last_bid and last_bid in tree.blocks:
                        tree.blocks[last_bid].edus.append(edu)
                    else:
                        block = self._new_block([edu], tree)
                        last_bid = block.block_id
                    decisions.append(RouteDecision.CONTINUE)

        self._last_block[session_id] = last_bid
        tree.current_branch = last_bid
        final = decisions[-1] if decisions else RouteDecision.CONTINUE
        return RouteResult(final, last_bid)

    def _new_block(self, edus: List[EDU], tree: DiscourseBlockTree,
                   parent: str = None) -> DiscourseBlock:
        block = DiscourseBlock(
            block_id=f"blk_{uuid.uuid4().hex[:8]}",
            edus=edus,
        )
        tree.add_block(block, parent or tree.root_id)
        return block

    def _should_merge(self, prev: EDU, curr: EDU) -> bool:
        cohesion = self._quantizer.compute(prev, curr)
        return cohesion.decision == "continue"

    def build_context(self, session_id: str, max_blocks: int = 8) -> str:
        tree = self._trees.get(session_id)
        if not tree or not tree.current_branch:
            return ""
        return tree.serialize_for_context(tree.current_branch, max_blocks)

    def get_tree(self, session_id: str) -> Optional[DiscourseBlockTree]:
        return self._trees.get(session_id)

    def get_stats(self, session_id: str) -> dict:
        tree = self._trees.get(session_id)
        if not tree:
            return {}
        return {
            "total_blocks": len(tree.blocks),
            "root_id": tree.root_id,
            "current_branch": tree.current_branch,
            "max_depth": max(b.depth for b in tree.blocks.values()) if tree.blocks else 0,
        }
