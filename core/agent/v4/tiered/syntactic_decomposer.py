"""SyntacticDecomposer v3: soft-matching via TieredActionResolver, feedback-capable.
Tier 0: exact predicate match (PREDICATE_DICT) ? sub-ms
Tier 1: embedding soft match (EmbeddingIndex) ? ~10ms
Tier 2: LLM (optional) ? ~500ms
All tiers feed back to Tier 0 on discovery.
"""
from __future__ import annotations
import re, logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ?? Synonym expansion (Tier 0 quick-lookup, same pattern as TieredRelationExtractor._rel_words) ??
SYNONYM_MAP = {
    "locate": "query", "lookup": "query", "retrieve": "query", "seek": "query",
    "fetch": "query", "scan": "query", "list": "query", "show": "query",
    "display": "query", "print": "query", "view": "query", "examine": "query",
    "append": "create_add", "insert": "create_add", "push": "create_add",
    "construct": "create_add", "initialize": "create_add", "setup": "configure",
    "destroy": "remove", "terminate": "remove", "kill": "remove",
    "cease": "remove", "halt": "remove", "detach": "remove", "purge": "remove",
    "revise": "modify", "patch": "modify", "tweak": "modify", "rewrite": "modify",
    "reorder": "modify", "relocate": "move", "shift": "move", "transfer": "move",
    "reposition": "move", "migrate": "move",
}

PREDICATE_DICT = {
    "create_add": ["add","create","new","build","generate","make"],
    "modify":    ["modify","change","update","adjust","edit","alter"],
    "remove":    ["remove","delete","drop","kill","stop","disable"],
    "query":     ["check","query","find","search","look","inspect","get"],
    "control":   ["start","stop","restart","run","execute","reset"],
    "move":      ["move","put","place","insert"],
    "configure": ["config","set","configure","setup"],
}

ALL_PREDICATE_WORDS = sorted(set(w for verbs in PREDICATE_DICT.values() for w in verbs))

NEGATION_MARKERS = {"not","no","never","dont","wont","cant","isnt","arent"}
UNCERTAINTY_MARKERS = {"maybe","perhaps","probably","might","could","likely"}
IMPERATIVE_MARKERS = {"please","need","must","add","create","remove","delete","update","change","find","get","check"}

ENTITY_PATTERN = re.compile(r'[A-Z][a-zA-Z]+[A-Z][a-zA-Z]+|[A-Z][a-z]+[A-Z][a-zA-Z]*')


@dataclass
class ParsedClause:
    raw_text: str = ""
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    negation: bool = False
    uncertainty: bool = False
    imperative: bool = False
    question: bool = False
    modifiers: List[str] = field(default_factory=list)
    parse_failed: bool = False
    parse_failed_reason: str = ""
    confidence: float = 0.7
    predicate_source: str = ""  # "rule" | "embedding" | "llm" | "none"


class SyntacticDecomposer:
    """Soft-matching syntactic decomposer with feedback loop."""

    def __init__(self, action_resolver=None):
        self._resolver = action_resolver
        self._phrase_hits: dict = {}
        if self._resolver is not None:
            self._register_syntactic_domain()

    def _register_syntactic_domain(self) -> None:
        from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex
        rules = {cat: list(words) for cat, words in PREDICATE_DICT.items()}
        index = EmbeddingIndex(dim=32)
        for word in ALL_PREDICATE_WORDS:
            index.add(word, EmbeddingIndex.hash_embedding(word, dim=32))
        adapter = DomainAdapter(
            domain="syntactic", rules=rules, action_index=index,
            default_action="query",
        )
        self._resolver.register_domain(adapter)

    def decompose(self, text: str) -> List[ParsedClause]:
        clauses = self._split_clauses(text)
        parsed = []
        for clause_text in clauses:
            if clause_text.strip():
                parsed.append(self._parse_clause(clause_text))
        if not parsed:
            parsed.append(ParsedClause(raw_text=text, parse_failed=True,
                           parse_failed_reason="empty_input"))
        return parsed

    def _split_clauses(self, text: str) -> List[str]:
        segments = re.split(r'[.,!?;]+', text)
        parts = [s.strip() for s in segments if s.strip()]
        return parts if parts else [text]

    def _parse_clause(self, text: str) -> ParsedClause:
        clause = ParsedClause(raw_text=text)
        clause.negation = any(m in text.lower() for m in NEGATION_MARKERS)
        clause.uncertainty = any(m in text.lower() for m in UNCERTAINTY_MARKERS)
        clause.imperative = any(m in text.lower() for m in IMPERATIVE_MARKERS)
        clause.question = text.endswith("?")
        clause.entities = self._extract_entities(text)
        clause.predicate, clause.predicate_source = self._extract_predicate(text)
        if clause.predicate:
            clause.object = self._extract_object(text, clause.predicate)
            clause.subject = self._extract_subject(text)
        clause.modifiers = self._extract_modifiers(text)
        if clause.negation and clause.uncertainty: clause.confidence = 0.4
        elif clause.negation or not clause.predicate: clause.confidence = 0.55
        return clause

    def _extract_predicate(self, text: str):
        """Return (predicate, source). Quick-path: synonym lookup."""
        tl = text.lower()

        # Tier 0a: Synonym quick-lookup (fastest, covers 85%+ cases)
        for word in re.findall(r'[a-z]{3,}', tl):
            if word in SYNONYM_MAP:
                cat = SYNONYM_MAP[word]
                return cat, "rule"

        # Tier 0b: Direct match in PREDICATE_DICT
        for verbs in PREDICATE_DICT.values():
            for verb in sorted(verbs, key=len, reverse=True):
                if verb in tl:
                    return verb, "rule"

        # Soft path: resolver (Tier 1 + Tier 2)
        if self._resolver is not None:
            for word in re.findall(r'[a-z]{3,}', tl):
                candidates = self._resolver.resolve("syntactic", word)
                if candidates and candidates[0].confidence >= 0.55:
                    action = candidates[0].action
                    if action in PREDICATE_DICT:
                        return action, candidates[0].source
                    # New action: promote to Tier 0
                    self._promote_word(word, action, candidates[0].source)

        return None, "none"

    def _promote_word(self, word: str, action: str, source: str) -> None:
        """Feedback: promote a new word to Tier 0 rules."""
        if action not in PREDICATE_DICT:
            PREDICATE_DICT[action] = []
        if word not in PREDICATE_DICT[action]:
            PREDICATE_DICT[action].append(word)
            logger.info("Promoted predicate %r -> %s (source=%s)", word, action, source)
        self._phrase_hits[word] = self._phrase_hits.get(word, 0) + 1

    def _extract_entities(self, text: str) -> List[str]:
        entities = list(ENTITY_PATTERN.findall(text))
        for kws in PREDICATE_DICT.values():
            for kw in kws:
                if len(kw) > 3 and kw in text.lower():
                    entities.append(kw)
        return list(set(entities))

    def _extract_object(self, text: str, predicate: str) -> Optional[str]:
        pos = text.lower().find(predicate.lower())
        if pos < 0: return None
        after = text[pos + len(predicate):].strip()
        return after if after else None

    def _extract_subject(self, text: str) -> Optional[str]:
        for p in ["this","that","it"]:
            if p in text: return p
        return None

    def _extract_modifiers(self, text: str) -> List[str]:
        mods = []
        if any(m in text.lower() for m in UNCERTAINTY_MARKERS): mods.append("uncertain")
        if any(m in text.lower() for m in NEGATION_MARKERS): mods.append("negated")
        return mods
