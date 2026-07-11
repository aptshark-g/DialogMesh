"""SyntacticDecomposer v2: self-contained entity extraction, no NLP model needed."""
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

class SyntacticDecomposer:
    NEGATION_MARKERS = {"not","no","never","dont","wont","cant","isnt","arent"}
    UNCERTAINTY_MARKERS = {"maybe","perhaps","probably","might","could","likely"}
    IMPERATIVE_MARKERS = {"please","need","must","add","create","remove","delete","update","change","find","get","check"}
    PREDICATE_DICT = {
        "create_add": ["add","create","new","build","generate","make"],
        "modify":   ["modify","change","update","adjust","edit","alter"],
        "remove":   ["remove","delete","drop","kill","stop","disable"],
        "query":    ["check","query","find","search","look","inspect","get"],
        "control":  ["start","stop","restart","run","execute","reset"],
        "move":     ["move","put","place","insert"],
        "configure":["config","set","configure","setup"],
    }

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
        if not parts:
            return [text]
        return parts

    def _parse_clause(self, text: str) -> ParsedClause:
        clause = ParsedClause(raw_text=text)
        clause.negation = any(m in text.lower() for m in self.NEGATION_MARKERS)
        clause.uncertainty = any(m in text.lower() for m in self.UNCERTAINTY_MARKERS)
        clause.imperative = any(m in text.lower() for m in self.IMPERATIVE_MARKERS)
        clause.question = text.endswith("?")
        clause.entities = self._extract_entities(text)
        clause.predicate = self._extract_predicate(text)
        if clause.predicate:
            clause.object = self._extract_object(text, clause.predicate)
            clause.subject = self._extract_subject(text)
        clause.modifiers = self._extract_modifiers(text)
        if clause.negation and clause.uncertainty: clause.confidence = 0.4
        elif clause.negation or not clause.predicate: clause.confidence = 0.55
        return clause

    def _extract_entities(self, text: str) -> List[str]:
        entities = []
        entities.extend(re.findall(r'[A-Z][a-zA-Z]+[A-Z][a-zA-Z]+', text))
        entities.extend(re.findall(r'\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b', text))
        for kws in self.PREDICATE_DICT.values():
            for kw in kws:
                if len(kw) > 3 and kw in text.lower():
                    entities.append(kw)
        return list(set(entities))

    def _extract_predicate(self, text: str) -> Optional[str]:
        tl = text.lower()
        for verbs in self.PREDICATE_DICT.values():
            for verb in sorted(verbs, key=len, reverse=True):
                if verb in tl: return verb
        return None

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
        if any(m in text.lower() for m in self.UNCERTAINTY_MARKERS): mods.append("uncertain")
        if any(m in text.lower() for m in self.NEGATION_MARKERS): mods.append("negated")
        return mods
