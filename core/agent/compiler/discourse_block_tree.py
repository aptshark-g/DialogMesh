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
    """Pronoun resolution via session entity cache + SyntacticDecomposer.

    Priority: same-turn explicit → session recent → syntactic subject resolution → history pool.
    """

    def __init__(self):
        self._sessions: Dict[str, List[str]] = {}
        self._decomposer = SyntacticDecomposer()
        self._entity_cache: Dict[str, List[str]] = {}  # session_id → entities
        self._last_entity: Dict[str, str] = {}
        self._last_entity: Dict[str, Optional[str]] = {}

    def inject(self, text: str, session_id: str, history: List[str] = None) -> str:
        if history:
            self._update_cache(session_id, history)
        # Structural pronoun detection — SyntacticDecomposer checks empty-subject slots
        edus = self._decomposer.decompose(text)
        for edu in edus:
            if edu.subject is None and edu.obj:
                resolved = self._resolve_reference(edu.object, 
                    self._entity_cache.get(session_id, []))
                if resolved:
                    return text  # SyntacticDecomposer handles substitution
        return text

    def _update_cache(self, session_id: str, history: List[str]):
        cache = self._entity_cache.setdefault(session_id, [])
        for h in history[-5:]:
            for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', h):
                cache.append(m.group())
            # Chinese: only keep the LAST matched phrase (tends to be the object)
            zh = re.findall(r'[\u4e00-\u9fff]{2,3}', h)
            if zh:
                cache.append(zh[-1])  # last short phrase = most likely object

    def _resolve_reference(self, text: str, recent_entities: List[str]) -> str:
        """Structural reference resolution via SyntacticDecomposer output.
        If subject is empty/trivial and object exists, this is a reference — return the entity cleanly."""
        if not recent_entities:
            return text
        try:
            edus = self._decomposer.decompose(text)
            if edus and (not edus[0].subject or len(edus[0].subject or '') <= 2) and edus[0].obj:
                return recent_entities[0]
        except Exception:
            pass
        return text

    def _resolve(self, pronoun: str, text: str, session_id: str) -> Optional[str]:
        # Same-turn: check content before pronoun for entities
        pos = text.find(pronoun)
        if pos > 0:
            before = text[:pos]
            # English proper nouns
            ents = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', before)
            if ents: return ents[-1]
            # Chinese trailing phrase (last 2+ char word before pronoun)
            zh = re.findall(r'[\u4e00-\u9fff]{2,}', before)
            if zh: return zh[-1]
        # Session entity cache from history
        cache = self._entity_cache.get(session_id, [])
        return cache[-1] if cache else None
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
                from core.agent.tiered.parser import RuleDecomposer
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
@dataclass
class CohesionScore:
    total: float
    macro: float
    micro: float
    decision: str  # "continue" | "fork" | "gray_zone"
    # 9 individual dimensions for traceability
    cos_sim: float = 0.5
    intent_match: float = 0.5
    topic_embed: float = 0.5
    time_decay: float = 0.5
    entity_overlap: float = 0.5
    causal_link: float = 0.5
    subject_cont: float = 0.5
    ref_inherit: float = 0.5
    lexical: float = 0.5

    @property
    def is_extreme(self) -> bool:
        return self.total > 0.75 or self.total < 0.25
    
    def dimension_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ['cos_sim','intent_match','topic_embed','time_decay',
                 'entity_overlap','causal_link','subject_cont','ref_inherit','lexical']}


class MacroMicroQuantizer:
    """Cohesion computation: BGE fast path + 9-dim full formula for gray zone."""

    GRAY_LOW, GRAY_HIGH = 0.25, 0.75
    MACRO_WEIGHTS = {"cos_sim": 0.35, "intent": 0.25, "topic_embed": 0.20, "time_decay": 0.20}
    MICRO_WEIGHTS = {"entity": 0.30, "causal": 0.25, "subject_cont": 0.20,
                     "ref_inherit": 0.15, "lexical": 0.10}

    def __init__(self):
        self._bge = None

    def _bge_similarity(self, text_a: str, text_b: str) -> float:
        """BGE cosine similarity fallback when entity overlap is low (Chinese short text)."""
        self._ensure_bge()
        if not self._bge or self._bge is False:
            return 0.5  # neutral
        try:
            import numpy as np
            v_a = self._bge.encode(text_a)
            v_b = self._bge.encode(text_b)
            return float(np.dot(v_a, v_b) / (np.linalg.norm(v_a) * np.linalg.norm(v_b) + 1e-8))
        except Exception:
            return 0.5

    _QUESTION_PATTERNS = {
        "self_reflection": ["你觉得", "你认为", "你对自己", "你如何看"],
        "causal_query":   ["为什么", "原因", "怎么会"],
        "definition":     ["是什么", "什么类型", "属于"],
        "comparison":     ["有没有可能", "是不是", "还是"],
        "meta_cognition": ["元认知", "镜子", "视角", "双视角"],
    }

    def _question_type(self, text: str) -> str:
        """Classify Chinese question type for cohesion scoring."""
        for qtype, patterns in self._QUESTION_PATTERNS.items():
            if any(p in text for p in patterns):
                return qtype
        return "general"

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
                # Flatten: sentence-transformers returns (1,512)
                a = va.flatten() if len(va.shape) > 1 else va
                b = vb.flatten() if len(vb.shape) > 1 else vb
                total = float(np.dot(a, b))
                fork_threshold = 0.20 if union else 0.10  # n-gram features are sparse
                if total > 0.70:
                    return CohesionScore(total, total, 0.0, "continue")
                if total < fork_threshold:
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
        # topic embedding: entity overlap + BGE fallback for Chinese short text
        overlap = len(set(a.entities) & set(b.entities))
        total_e = len(set(a.entities) | set(b.entities)) or 1
        entity_score = overlap / total_e
        if entity_score < 0.3 and self._bge is not False:
            # Low entity overlap (Chinese short text): use BGE semantic similarity
            bge_score = self._bge_similarity(getattr(a, 'raw_text', ''), getattr(b, 'raw_text', ''))
            # Blend: BGE weight increases as entity overlap decreases
            blend_weight = 1.0 - entity_score
            entity_score = entity_score * (1 - blend_weight) + bge_score * blend_weight
        scores.append(entity_score * self.MACRO_WEIGHTS["topic_embed"])
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
    temperature: int = 0  # 0=Hot, 1=Warm, 2=Cold, 3=Frozen
    last_access: float = field(default_factory=time.time)
    summary: str = ""
    
    def summarize(self, llm_provider=None) -> str:
        """Temperature-gated summary generation.
        Hot(t=0): keep original text
        Warm(t=1): entity extraction + key action
        Cold(t=2): LLM compression (LM Studio nemotron)
        Frozen(t=3): index only
        """
        if not self.edus:
            return "(empty)"
        
        texts = [getattr(e, 'raw_text', str(e)) for e in self.edus]
        full_text = " ".join(texts)
        
        if self.temperature == 0:  # Hot — keep original
            self.summary = full_text[:300]
        elif self.temperature == 1:  # Warm — entity + action extraction
            entities = []
            for e in self.edus:
                entities.extend(getattr(e, 'entities', []))
            verbs = [getattr(e, 'predicate', '') for e in self.edus if getattr(e, 'predicate', '')]
            self.summary = f"[{', '.join(set(entities[:5]))}] {' → '.join(verbs[:3])}"
            self.summary = self.summary[:120]
        elif self.temperature == 2:  # Cold — LLM compression
            self.summary = self._llm_summarize(full_text, llm_provider)
        else:  # Frozen — index only
            keywords = []
            for e in self.edus:
                keywords.extend(getattr(e, 'entities', [])[:3])
            self.summary = f"[{self.block_id}] {' '.join(set(keywords[:5]))}"[:60]
        
        self.last_access = time.time()
        return self.summary
    
    def _llm_summarize(self, text: str, llm_provider=None) -> str:
        """LLM compression via LM Studio nemotron. Falls back to BM25+kurtosis."""
        if not llm_provider:
            try:
                import urllib.request, json
                prompt = f"Extract the key action and entity from this reverse engineering conversation. Output 1 short sentence:\n{text[:300]}"
                req = urllib.request.Request(
                    "http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps({
                        "model": "nvidia/nemotron-3-nano-4b",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 100, "temperature": 0.1
                    }).encode(),
                    headers={"Content-Type": "application/json"}
                )
                resp = urllib.request.urlopen(req, timeout=10)
                result = json.loads(resp.read())
                content = result["choices"][0]["message"].get("content", "")
                if not content:
                    content = result["choices"][0]["message"].get("reasoning_content", "")
                if content and len(content) > 5:
                    return content[:120]
                raise ValueError("empty LLM response")
            except Exception as e:
                logger.debug("LM Studio failed: %s, using BM25 fallback", e)
                return self._bm25_fallback(text)
        
        result = llm_provider.generate(prompt=f"Extract key action: {text[:200]}", max_tokens=80)
        return (result.text if hasattr(result, 'text') else str(result))[:120]
    
    def _bm25_fallback(self, text: str) -> str:
        """BM25+kurtosis topic matching when LLM unavailable."""
        try:
            from core.agent.compiler.topic_quick_match import TopicQuickMatcher
            matcher = TopicQuickMatcher()
            # Index common reverse engineering domains
            matcher.index("memory_scan", ["scan memory address entry point find offset"])
            matcher.index("code_patch", ["patch binary modify nop change instruction"])
            matcher.index("crypto_analysis", ["encrypt decrypt algorithm cipher AES key"])
            matcher.index("function_hook", ["hook detour intercept function frida inline"])
            matcher.index("packer_detect", ["packer unpack upx aspack peid detect identify"])
            matcher.index("debug_analysis", ["debug trace breakpoint step anti-debug bypass"])
            return matcher.summarize(text)
        except Exception:
            entities = __import__('re').findall(r'0x[0-9a-fA-F]+|[A-Z]{2,}', text)
            return f"[{', '.join(set(entities[:5]))}]" if entities else text[:100]
            text = " ".join(getattr(e, 'raw_text', '') for e in self.edus[:5])
            prompt = (
                f"Summarize this conversation fragment in one Chinese sentence (max 40 characters). "
                f"Include: topic, user intent, key information.\n\n"
                f"Fragment: {text[:500]}\n\nSummary:"
            )
            result = llm_provider.generate(GenerateRequest(prompt=prompt, max_tokens=80, temperature=0.1))
            summary = result.text.strip() if hasattr(result, 'text') else str(result).strip()
            return summary[:120]
        except Exception:
            return self.serialize_edus_summary()[:120]
    children: List[str] = field(default_factory=list)  # child block_ids
    parent: Optional[str] = None
    depth: int = 0
    summary: str = ""
    created_at: float = field(default_factory=time.time)
    temperature: str = "active"  # active | paused | cold | frozen
    importance: float = 0.3      # 0-1: LOW(0.3), MEDIUM(0.6), HIGH(0.9)

    CORRECTION_SIGNALS = None  # loaded from soft_config
    SWITCH_SIGNALS = None

    @classmethod
    def _ensure_signals(cls):
        """Lazy-load importance signals from soft_config."""
        if cls.CORRECTION_SIGNALS is not None:
            return
        try:
            from core.agent.compiler.soft_config import load_importance_config
            cfg = load_importance_config()
            cls.CORRECTION_SIGNALS = [s["pattern"] for s in cfg.get("correction_signals", [])]
            cls.SWITCH_SIGNALS = [s["pattern"] for s in cfg.get("switch_signals", [])]
            cls._METACOGNITION_SIGNALS = [s["pattern"] for s in cfg.get("metacognition_signals", [])]
        except Exception:
            cls.CORRECTION_SIGNALS = ["不是", "不对", "我才是", "你搞错了"]
            cls.SWITCH_SIGNALS = ["switch", "切换"]
            cls._METACOGNITION_SIGNALS = ["元认知", "对话树"]

    def compute_importance(self, encoder=None):
        """Auto-score block importance using BGE semantic similarity.

        Falls back to signal matching if no encoder available.
        """
        text = " ".join(getattr(e, 'raw_text', '') for e in self.edus)
        if not text.strip():
            self.importance = 0.3
            return

        # Try BGE semantic first
        try:
            from core.agent.compiler.lsh_index import bge_importance_score
            self.importance = bge_importance_score(text, {
                "correction": "用户纠正了系统的错误理解 否定了之前的回答 澄清了身份",
                "metacognition": "讨论元认知 对话树设计 系统架构反思 颗粒度控制",
                "switch": "话题切换 换个方向 跳跃式提问",
            })
            return
        except Exception:
            pass

        # Fallback: string matching
        self._ensure_signals()
        if any(sig in text for sig in (self.CORRECTION_SIGNALS or [])):
            self.importance = 0.9
        elif any(sig in text for sig in (self._METACOGNITION_SIGNALS or [])):
            self.importance = 0.85
        elif any(sig in text for sig in (self.SWITCH_SIGNALS or [])):
            self.importance = 0.6
        else:
            self.importance = 0.3

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

    def update_temperature(self, block_id: str):
        """Update block temperature based on time since last access + importance.

        Important blocks (user corrections, meta-cognition) decay slower.
        """
        if block_id not in self.blocks:
            return
        blk = self.blocks[block_id]
        now = time.time()
        age = now - blk.created_at
        # Importance-weighted thresholds: high importance = longer active window
        factor = 1.0 + blk.importance  # range: 1.3 (low) to 1.9 (high)
        if age < 300 * factor:
            blk.temperature = "active"
        elif age < 1800 * factor:
            blk.temperature = "paused"
        elif age < 7200 * factor:
            blk.temperature = "cold"
        else:
            blk.temperature = "frozen"

    def active_blocks(self) -> List[DiscourseBlock]:
        """Return blocks that are active or paused (should be injected into context)."""
        now = time.time()
        active = []
        for blk in self.blocks.values():
            if now - blk.created_at < 1800:
                active.append(blk)
        return active

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


class DiscourseBlockGranularityRegulator:
    """Dynamic granularity: split over-dense blocks, merge over-fragmented ones.

    Design: design_discourse_block_tree_v2.md §6 BDI + BOR."""

    OPTIMAL_BLOCKS_PER_TOPIC = 4
    COOLDOWN_TURNS = 5

    def __init__(self):
        self.global_split_threshold = 0.25
        self._last_regulation_turn = 0
        self._turn_counter = 0
        self.bor_history: list = []  # BOR tracking for adaptive threshold
        self.target_bor_min = 0.8
        self.target_bor_max = 1.5
    
    def _compute_bor(self, tree: "DiscourseBlockTree") -> float:
        """Block Overlap Ratio — measures block fragmentation.
        BOR < 0.8 = too fragmented (need merge)
        BOR > 1.5 = too dense (need split)
        BOR 0.8-1.5 = healthy
        """
        blocks = list(tree.blocks.values()) if hasattr(tree, 'blocks') else []
        if len(blocks) < 2:
            return 1.0
        total_edus = sum(len(b.edus) for b in blocks)
        return total_edus / len(blocks) / self.OPTIMAL_BLOCKS_PER_TOPIC
    
    def _adapt_threshold(self):
        """Adapt split threshold based on BOR history."""
        if len(self.bor_history) < 3:
            return
        recent = self.bor_history[-3:]
        avg_bor = sum(recent) / len(recent)
        if avg_bor < self.target_bor_min:
            self.global_split_threshold = max(0.15, self.global_split_threshold - 0.02)
        elif avg_bor > self.target_bor_max:
            self.global_split_threshold = min(0.40, self.global_split_threshold + 0.02)

    def regulate(self, tree: "DiscourseBlockTree", current_turn: int):
        """Apply BDI+BOR regulation to tree. Called after feed()."""
        self._turn_counter = current_turn
        if current_turn - self._last_regulation_turn < self.COOLDOWN_TURNS:
            return
        # BDI: how healthy is block distribution?
        non_root = [b for bid, b in tree.blocks.items() if bid != tree.root_id]
        if not non_root:
            return
        bdi = len(non_root) / self.OPTIMAL_BLOCKS_PER_TOPIC
        # BOR: boundary over-representation
        actual_boundaries = len(non_root)
        expected_boundaries = max(1, len(non_root) * 0.5)
        bor = actual_boundaries / expected_boundaries

        if bdi < 0.5 or bor < 0.6:
            # Too sparse: merge similar adjacent blocks
            self._merge_adjacent(tree)
        elif bdi > 2.0 or bor > 1.5:
            # Too dense: raise threshold to reduce splits
            self.global_split_threshold = min(self.global_split_threshold * 1.2, 0.9)
        self._last_regulation_turn = current_turn

    def _merge_adjacent(self, tree: "DiscourseBlockTree"):
        """Merge blocks with high entity overlap in the same branch."""
        import itertools
        merged = 0
        for bid in list(tree.blocks.keys()):
            if bid == tree.root_id:
                continue
            siblings = [b for b in tree.blocks.values()
                        if b.parent == tree.blocks[bid].parent and b.block_id != bid]
            for sib in siblings:
                if sib.block_id not in tree.blocks or bid not in tree.blocks:
                    continue
                overlap = self._entity_overlap(tree.blocks[bid], sib)
                if overlap > 0.6:
                    # Merge sib into bid
                    tree.blocks[bid].edus.extend(sib.edus)
                    del tree.blocks[sib.block_id]
                    merged += 1

    @staticmethod
    def _entity_overlap(a, b) -> float:
        ea = set()
        for edu in getattr(a, 'edus', []):
            ea.update(getattr(edu, 'entities', []))
        eb = set()
        for edu in getattr(b, 'edus', []):
            eb.update(getattr(edu, 'entities', []))
        union = len(ea | eb)
        return len(ea & eb) / union if union > 0 else 0.0


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
        self._last_block: Dict[str, str] = {}
        import threading
        self._cold_queue: list = []
        self._cold_lock = threading.Lock()
        self._cold_thread: Optional[threading.Thread] = None
        self._cold_running = False

    def _schedule_cold_compress(self, blocks: list):
        with self._cold_lock:
            self._cold_queue.extend(blocks)
        if not self._cold_running and self._cold_queue:
            self._cold_running = True
            self._cold_thread = threading.Thread(target=self._cold_worker, daemon=True)
            self._cold_thread.start()

    def _cold_worker(self):
        import time as _time
        while True:
            block = None
            with self._cold_lock:
                if self._cold_queue:
                    block = self._cold_queue.pop(0)
                else:
                    self._cold_running = False
                    return
            if block:
                try:
                    block.temperature = 2
                    block.summarize()
                except Exception:
                    pass
                _time.sleep(0.5)  # 2 blocks/sec rate limit

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
        # Update temperature on all blocks for this tree
        for bid in list(tree.blocks.keys()):
            tree.update_temperature(bid)
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

    def get_block_relations(self, session_id: str) -> dict:
        """Association chain query interface — returns block-level relationship graph."""
        tree = self._trees.get(session_id)
        if not tree:
            return {"session_id": session_id, "blocks": {}, "relations": []}
        blocks_info = {}
        for bid, b in tree.blocks.items():
            blocks_info[bid] = {
                "parent": b.parent,
                "children": list(b.children),
                "edus": len(b.edus),
                "entities": list(set(e for edu in b.edus for e in getattr(edu, 'entities', []))),
                "temperature": b.temperature,
                "summary": b.summary[:100] if b.summary else "",
            }
        relations = []
        for bid, b in tree.blocks.items():
            if b.parent and b.parent != "_root":
                relations.append({"from": bid, "to": b.parent, "type": "child_of"})
            for child in b.children:
                relations.append({"from": bid, "to": child, "type": "parent_of"})
        return {"session_id": session_id, "blocks": blocks_info, "relations": relations}

    def find_block_by_reference(self, session_id: str, reference: str):
        """Find block by entity name or key phrase. Returns block_id or None."""
        tree = self._trees.get(session_id)
        if not tree: return None
        ref_lower = reference.lower()
        for block in tree.blocks.values():
            for e in getattr(block, 'entities', []):
                name = e.name if hasattr(e, 'name') else str(e)
                if name.lower() in ref_lower or ref_lower in name.lower():
                    return getattr(block, 'block_id', '')
        for block in tree.blocks.values():
            if ref_lower in (getattr(block, 'raw_text', '') or '').lower():
                return getattr(block, 'block_id', '')
        return None

    def compress_cold_blocks(self, session_id: str, llm=None):
        """Background task: upgrade cold blocks to v4 summary."""
        tree = self._trees.get(session_id)
        if not tree: return 0
        from core.agent.discourse_block_tree.summary_engine import SummaryEngine
        engine = SummaryEngine(llm=llm)
        upgraded = 0
        current = getattr(tree, '_turn_count', 0)
        for block in list(tree.blocks.values()):
            if getattr(block, 'status', 'active') in ('cold', 'frozen'): continue
            if current - getattr(block, 'last_active_turn', 0) > 10:
                if engine.check_upgrade(block, current):
                    upgraded += 1
        if upgraded:
            import logging
            logging.getLogger(__name__).info('Compressed %d cold blocks', upgraded)
        return upgraded

    def build_context(self, session_id: str, max_blocks: int = 8) -> str:
        tree = self._trees.get(session_id)
        if not tree or not tree.blocks:
            return ""
        
        # Temperature-based context via SummaryEngine
        from core.agent.discourse_block_tree.summary_engine import SummaryEngine
        engine = SummaryEngine()
        
        # Update summaries before building context
        current_turn = getattr(tree, '_turn_count', 0)
        block_list = list(tree.blocks.values())[:max_blocks]
        for block in block_list:
            engine.check_upgrade(block, current_turn)
        
        return engine.build_context(block_list)

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

    # ── CLI write ops ──

    def split_block(self, session_id: str, block_id: str, position: int = 0) -> bool:
        """Split a block at the given EDU position. Returns True on success."""
        tree = self._trees.get(session_id)
        if not tree or block_id not in tree.blocks:
            return False
        block = tree.blocks[block_id]
        if len(block.edus) <= 1:
            return False
        split_at = max(1, min(position, len(block.edus) - 1))
        left_edus = block.edus[:split_at]
        right_edus = block.edus[split_at:]
        block.edus = left_edus
        new_block = DiscourseBlock(
            block_id=f"blk_{uuid.uuid4().hex[:8]}",
            edus=right_edus,
        )
        tree.add_block(new_block, parent=block.parent or tree.root_id)
        return True

    def merge_blocks(self, session_id: str, block_ids: list) -> bool:
        """Merge blocks into the first one. Returns True on success."""
        tree = self._trees.get(session_id)
        if not tree or len(block_ids) < 2:
            return False
        target = tree.blocks.get(block_ids[0])
        if not target:
            return False
        for bid in block_ids[1:]:
            b = tree.blocks.get(bid)
            if b:
                target.edus.extend(b.edus)
                del tree.blocks[bid]
        return True

    def delete_block(self, session_id: str, block_id: str) -> bool:
        """Delete a block. Children are reparented to the deleted block's parent."""
        tree = self._trees.get(session_id)
        if not tree or block_id not in tree.blocks:
            return False
        block = tree.blocks[block_id]
        parent_id = block.parent
        for child in list(block.children):
            if child in tree.blocks:
                tree.blocks[child].parent = parent_id
        del tree.blocks[block_id]
        if block_id == tree.current_branch:
            tree.current_branch = next(iter(tree.blocks.keys())) if tree.blocks else tree.root_id
        return True

    def promote_block(self, session_id: str, block_id: str, levels: int = 1) -> bool:
        """Move block up in the hierarchy. Returns True on success."""
        tree = self._trees.get(session_id)
        if not tree or block_id not in tree.blocks:
            return False
        block = tree.blocks[block_id]
        for _ in range(levels):
            parent = tree.blocks.get(block.parent)
            if not parent or block.parent == tree.root_id:
                break
            block.parent = parent.parent or tree.root_id

    def demote_block(self, session_id: str, block_id: str, levels: int = 1) -> bool:
        """Move block down (under its first sibling). Returns True on success."""
        tree = self._trees.get(session_id)
        if not tree or block_id not in tree.blocks:
            return False
        block = tree.blocks[block_id]
        for _ in range(levels):
            parent = tree.blocks.get(block.parent)
            if not parent:
                break
            siblings = [c for c in parent.children if c != block_id and c in tree.blocks]
            if siblings:
                block.parent = siblings[0]
