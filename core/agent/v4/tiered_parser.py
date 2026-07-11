"""TieredParser: three-tier progressive syntactic parsing pipeline."""
from __future__ import annotations
import re, logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


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
    tier_used: int = 1


# Tier 1: Rule-based decomposer (self-contained, zero dependencies)
class RuleDecomposer:
    NEG = {"not","no","never","dont","wont","cant","isnt","arent",
           "\u4e0d","\u6ca1","\u522b","\u7981\u6b62","\u52ff","\u65e0"}
    UNC = {"maybe","perhaps","probably","might","could","likely",
           "\u53ef\u80fd","\u4e5f\u8bb8","\u5927\u6982","\u5e94\u8be5","\u4f30\u8ba1"}
    IMP = {"please","need","must",
           "\u8bf7","\u5e2e\u6211","\u7ed9\u6211","\u9ebb\u70e6","\u9700\u8981","\u5fc5\u987b"}

    PREDICATE_DICT = {
        "create_add": ["add","create","new","build","generate","make",
                       "\u52a0","\u6dfb\u52a0","\u589e\u52a0","\u65b0\u589e","\u521b\u5efa","\u5199","\u751f\u6210","\u6784\u5efa"],
        "modify": ["modify","change","update","adjust","edit","alter",
                   "\u6539","\u4fee\u6539","\u8c03\u6574","\u66f4\u65b0","\u53d8\u66f4","\u6362\u6210","\u6539\u6210"],
        "remove": ["remove","delete","drop","kill","stop","disable",
                   "\u5220","\u5220\u9664","\u79fb\u9664","\u53bb\u6389","\u505c","\u505c\u6389"],
        "query": ["check","query","find","search","look","inspect","get",
                  "\u67e5","\u67e5\u8be2","\u770b","\u68c0\u67e5","\u627e","\u641c\u7d22"],
        "control": ["start","stop","restart","run","execute","reset",
                    "\u542f\u52a8","\u505c\u6b62","\u91cd\u542f","\u8fd0\u884c","\u8dd1","\u6267\u884c"],
        "move": ["move","put","place","insert",
                 "\u79fb\u5230","\u653e\u5165","\u653e\u5230","\u52a0\u5230","\u63d2\u5165"],
        "configure": ["config","set","configure","setup","\u914d\u7f6e","\u8bbe\u7f6e","\u8c03"],
    }

    def parse(self, text: str) -> ParsedClause:
        if not text.strip():
            return ParsedClause(raw_text=text, parse_failed=True, parse_failed_reason="empty_input", tier_used=1)
        clause = ParsedClause(raw_text=text, tier_used=1)
        tl = text.lower()
        clause.negation = any(m in tl for m in self.NEG)
        clause.uncertainty = any(m in tl for m in self.UNC)
        clause.imperative = any(m in tl for m in self.IMP)
        clause.question = text.strip().endswith("?") or text.strip().endswith("\uff1f")
        clause.predicate = self._find_predicate(tl)
        if clause.predicate:
            clause.object = self._find_object(text, clause.predicate)
        clause.entities = self._find_entities(text)
        clause.modifiers = self._find_modifiers(text)
        clause.confidence = self._compute_confidence(clause)
        return clause

    def _find_predicate(self, text_lower: str) -> Optional[str]:
        for verbs in self.PREDICATE_DICT.values():
            for verb in sorted(verbs, key=len, reverse=True):
                if verb in text_lower:
                    return verb
        return None

    def _find_object(self, text: str, predicate: str) -> Optional[str]:
        pos = text.lower().find(predicate.lower())
        if pos < 0: return None
        after = text[pos + len(predicate):].strip()
        return after if after else None

    def _find_entities(self, text: str) -> List[str]:
        entities = []
        entities.extend(re.findall(r'[A-Z][a-z]+[A-Z][a-zA-Z]+', text))
        entities.extend(re.findall(r'\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b', text))
        return list(set(entities))

    def _find_modifiers(self, text: str) -> List[str]:
        mods = []
        tl = text.lower()
        if any(m in tl for m in self.UNC): mods.append("uncertain")
        if any(m in tl for m in self.NEG): mods.append("negated")
        return mods

    def _compute_confidence(self, clause: ParsedClause) -> float:
        if clause.negation and clause.uncertainty: return 0.4
        if clause.negation or not clause.predicate: return 0.55
        if clause.predicate and clause.object: return 0.75
        return 0.65


# Tier 2: spaCy + Benepar (optional, graceful fallback)
class SpacyBeneparParser:

    def __init__(self):
        self._nlp = None
        self._benepar = None

    def _ensure_loaded(self):
        if self._nlp is not None: return
        try:
            import spacy
            self._nlp = spacy.load("en_core_web_sm")
            try:
                import benepar
                self._nlp.add_pipe("benepar", config={"model": "benepar_en3"})
                self._benepar = True
            except Exception:
                logger.info("Benepar not available, using spaCy only")
        except Exception:
            logger.info("spaCy not available, tier 2 disabled")

    def parse(self, text: str, hint: ParsedClause = None) -> ParsedClause:
        self._ensure_loaded()
        if self._nlp is None:
            return ParsedClause(raw_text=text, parse_failed=True,
                                parse_failed_reason="spacy_unavailable", tier_used=2)
        doc = self._nlp(text)
        clause = ParsedClause(raw_text=text, tier_used=2)
        if doc.has_annotation("DEP"):
            root = [t for t in doc if t.dep_ == "ROOT"]
            if root:
                clause.predicate = root[0].text
                clause.object = " ".join([t.text for t in root[0].children
                                          if t.dep_ in ("dobj","pobj","attr","npadvmod")])
                subj = [t for t in doc if t.dep_ == "nsubj"]
                if subj: clause.subject = subj[0].text
        if clause.predicate and clause.object:
            clause.confidence = 0.92 if self._benepar else 0.85
        elif clause.predicate:
            clause.confidence = 0.80
        else:
            clause.parse_failed = True
            clause.parse_failed_reason = "no_root_verb"
            clause.confidence = 0.0
        return clause


# Tier 3: LLM + Schema Guard
class LLMSchemaParser:

    def __init__(self, llm_callable=None):
        self._llm = llm_callable

    def parse(self, text: str, hint: ParsedClause = None) -> ParsedClause:
        if self._llm is None:
            logger.warning("LLM not configured for tier 3, returning hint result")
            return hint or ParsedClause(raw_text=text, parse_failed=True,
                                        parse_failed_reason="llm_unavailable", tier_used=3)
        hint_text = ""
        if hint and hint.predicate:
            hint_text = f"Hint: predicate may be '{hint.predicate}'."
        try:
            result = self._llm(f"Analyze: {text}. {hint_text} Return JSON with keys: predicate, object, subject, negation(bool), uncertainty(bool), imperative(bool).")
            import json
            parsed = json.loads(result)
            clause = ParsedClause(raw_text=text, tier_used=3, confidence=0.95)
            clause.predicate = parsed.get("predicate")
            clause.object = parsed.get("object")
            clause.subject = parsed.get("subject")
            clause.negation = parsed.get("negation", False)
            clause.uncertainty = parsed.get("uncertainty", False)
            clause.imperative = parsed.get("imperative", False)
            return self._schema_guard(clause)
        except Exception:
            logger.exception("LLM parse failed")
            return hint or ParsedClause(raw_text=text, parse_failed=True,
                                        parse_failed_reason="llm_error", tier_used=3)

    def _schema_guard(self, clause: ParsedClause) -> ParsedClause:
        VALID_PREDICATES = set()
        for verbs in RuleDecomposer.PREDICATE_DICT.values():
            VALID_PREDICATES.update(verbs)
        if clause.predicate and clause.predicate not in VALID_PREDICATES:
            clause.confidence = max(0.5, clause.confidence - 0.3)
            logger.warning("SchemaGuard: unknown predicate '%s', confidence reduced", clause.predicate)
        if clause.negation and clause.predicate:
            if clause.predicate in RuleDecomposer.PREDICATE_DICT.get("create_add", []):
                clause.parse_failed = True
                clause.parse_failed_reason = "contradiction: negation + create_add"
                clause.confidence = 0.3
        return clause


# Orchestrator
class TieredParser:

    def __init__(self, llm_callable=None):
        self._tier1 = RuleDecomposer()
        self._tier2 = SpacyBeneparParser()
        self._tier3 = LLMSchemaParser(llm_callable=llm_callable)

    def parse(self, text: str) -> ParsedClause:
        result = self._tier1.parse(text)
        if result.confidence >= 0.7 and not result.parse_failed:
            return result
        result = self._tier2.parse(text, hint=result)
        if result.confidence >= 0.85 and not result.parse_failed:
            return result
        return self._tier3.parse(text, hint=result)
