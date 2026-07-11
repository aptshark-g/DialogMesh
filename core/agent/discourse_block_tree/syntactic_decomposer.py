"""Stage 2: SyntacticDecomposer ? ??????????????"""
import re
from typing import List
from .models import EDU, DiscourseEntity
from .header_injector import HEADER_INJECTOR, PRONOUNS
from .topic_markers import DETECTOR


BOUNDARY_MARKS = set([chr(12290), chr(65281), chr(65311), chr(65307), chr(10), "!", "?", ";", ","])
TOPIC_SWITCH_MARKS = {"??", "??", "??", "????", "??", "????",
                      "by the way", "btw", "also", "another thing"}
LOGIC_TURN_MARKS = {"??", "??", "??", "??", "but", "however",
                    "??", "??", "though", "although"}
CONJUNCTIONS = {"?", "?", "?", "?", "?", "?", "and", "or", "with", "??"}

# ?????????
VERBS = {"?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?",
         "??", "??", "??", "??", "??", "??", "??", "??", "??",
         "??", "??", "??", "??", "??", "??", "??", "??", "??",
         "??", "??", "??", "??",
         "write", "read", "run", "execute", "scan", "debug", "deploy",
         "create", "delete", "modify", "check", "analyze", "monitor",
         "test", "update", "build", "compile", "install", "configure",
         "recommend", "find", "search", "compare", "show", "list"}


def _split_into_clauses(text: str) -> List[str]:
    """????????????"""
    clauses = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in BOUNDARY_MARKS and len(buf.strip()) > 2:
            clauses.append(buf.strip())
            buf = ""
    if buf.strip():
        clauses.append(buf.strip())
    return clauses if clauses else [text.strip()]


def _detect_topic_switch(text: str) -> list:
    '''?????????????????'''
    positions = []
    for marker in TOPIC_SWITCH_MARKS:
        idx = text.find(marker)
        while idx >= 0:
            # Only count if at start of a clause (after punctuation)
            prefix = text[max(0, idx-1):idx]
            if not prefix or prefix in BOUNDARY_MARKS:
                positions.append(idx)
            idx = text.find(marker, idx + 1)
    return positions


def _fallback_split(text: str) -> list:
    '''?????????????????'''
    clauses = _split_into_clauses(text)
    if len(clauses) >= 2:
        return clauses
    # Try splitting on topic switch markers
    parts = [text]
    for marker in TOPIC_SWITCH_MARKS:
        new_parts = []
        for p in parts:
            if marker in p:
                segs = p.split(marker, 1)
                new_parts.append(segs[0].strip())
                new_parts.append(marker + segs[1].strip())
            else:
                new_parts.append(p)
        parts = new_parts
    return [p.strip() for p in parts if p.strip()]


def _fast_extract(clause: str) -> dict:
    """Fast Path: ??+?????????"""
    prag = HEADER_INJECTOR.detect_pragmatics(clause)

    subject = ""
    obj = ""
    predicate = ""
    entities = HEADER_INJECTOR.extract_entities(clause)

    # ??????: ???? -> ???? -> ????
    for p in PRONOUNS:
        if p in clause:
            subject = p
            break
    if not subject:
        em = re.search(r"([A-Z]\w+(?:\s+[A-Z]\w+)*)", clause)
        if em:
            subject = em.group(1).strip()

    # ????: ??????
    verb_matches = [v for v in VERBS if v in clause]
    predicate = verb_matches[0] if verb_matches else ""

    # ????: ?????????/????
    if predicate:
        idx = clause.find(predicate) + len(predicate)
        after = clause[idx:].strip().rstrip(".????")
        after = after.split("?")[0].split("?")[0].split(",")[0].split(".")[0].strip()
        if after and len(after) < 30:
            obj = after

    return {
        "subject": subject,
        "predicate": predicate,
        "obj": obj,
        "negation": prag["negation"],
        "imperative": prag["imperative"],
        "uncertainty": prag["uncertainty"],
        "question": prag["question"],
        "entities": [e.text for e in entities],
    }


class SyntacticDecomposer:
    """
    ?????: ?????? List[EDU]?
    Fast Path (???) ?? 90% ???Hybrid Path ??????
    """

    def __init__(self, use_llm=False):
        self.use_llm = use_llm

    def decompose(self, text: str) -> List[EDU]:
        """??: ????????, ?? List[EDU]"""
        text = HEADER_INJECTOR.inject(text)
        raw_clauses = _split_into_clauses(text)
        edus = []
        for i, clause in enumerate(raw_clauses):
            if len(clause) > 30 and sum(1 for c in CONJUNCTIONS if c in clause) >= 2:
                # Hybrid Path: ?????
                edus.append(EDU(
                    index=i, raw_text=clause,
                    subject="", predicate="", obj="",
                    attrs={"hybrid": True, "parse_failed": True},
                ))
            else:
                parsed = _fast_extract(clause)
                edus.append(EDU(
                    index=i, raw_text=clause,
                    subject=parsed["subject"],
                    predicate=parsed["predicate"],
                    obj=parsed["obj"],
                    negation=parsed["negation"],
                    imperative=parsed["imperative"],
                    uncertainty=parsed["uncertainty"],
                    question=parsed["question"],
                    entities=parsed["entities"],
                ))
        return edus


SYNTACTIC_DECOMPOSER = SyntacticDecomposer()
