"""Stage 2: SyntacticDecomposer ? model-first clause decomposition.

Decomposition layers (2026-08-03 decision: use the model, don't hand-roll
keyword lists):
  1. Stanza dependency tree (grammar_tagger.tag_text) ? subject/verb/object
     + mood features, zero hardcoded patterns (same source as pronoun_resolver).
  2. jieba POS fallback (v/vn -> predicate, n/nr/nz -> subject/object) when
     Stanza is unavailable (e.g. broken numpy environment).
  3. Punctuation-boundary fallback ? clause splitting only.
The previous VERBS/CONJUNCTIONS/TOPIC_SWITCH keyword constants were removed:
they were GBK-damaged (all '?') and had no generalization value anyway.
"""
import re
from typing import List
from .models import EDU, DiscourseEntity
from .header_injector import HEADER_INJECTOR, PRONOUNS
from .topic_markers import DETECTOR


# Punctuation boundaries (unicode code points ? immune to the GBK damage that
# hit the keyword constants).
BOUNDARY_MARKS = set([
    chr(12290),  # 。
    chr(65281),  # ！
    chr(65311),  # ？
    chr(65307),  # ；
    chr(65292),  # ，
    chr(10), "!", "?", ";", ",",
])


def _split_into_clauses(text: str) -> List[str]:
    """Split text on punctuation boundaries (structure-only)."""
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


def _fast_extract(clause: str) -> dict:
    """Fast Path: Stanza dependency tree -> jieba POS -> structural fallback."""
    prag = HEADER_INJECTOR.detect_pragmatics(clause)

    subject = ""
    obj = ""
    predicate = ""
    entities = HEADER_INJECTOR.extract_entities(clause)

    # Layer 1: Stanza dependency tree (grammar_tagger) ? zero hardcoded lists.
    try:
        from core.agent.pcr.grammar_tagger import tag_text
        tags = tag_text(clause)
        if tags is not None:
            subject = tags.subject or subject
            predicate = tags.verb or predicate
            obj = tags.object or obj
            prag = {
                "negation": prag["negation"] or tags.has_negation,
                "imperative": prag["imperative"] or tags.is_imperative,
                "uncertainty": prag["uncertainty"],
                "question": prag["question"] or tags.is_question,
            }
    except Exception:
        pass

    # Layer 2: jieba POS fallback (broken-numpy environments kill Stanza).
    if not predicate:
        try:
            import jieba.posseg as pseg
            words = list(pseg.cut(clause))
            verbs = [w.word for w in words if w.flag and w.flag.startswith(("v", "V"))]
            nouns = [w.word for w in words if w.flag and w.flag.startswith(("n", "N"))]
            if verbs:
                predicate = verbs[0]
            if nouns and not subject:
                subject = nouns[0]
            if predicate and nouns:
                idx = clause.find(predicate)
                if idx >= 0:
                    after = clause[idx + len(predicate):].strip()
                    obj = next((n for n in nouns if n in after), "")
        except Exception:
            pass

    # Layer 3: structural fallback (English camelCase entities / pronouns).
    if not subject:
        for p in PRONOUNS:
            if p in clause:
                subject = p
                break
    if not subject:
        em = re.search(r"([A-Z]\w+(?:\s+[A-Z]\w+)*)", clause)
        if em:
            subject = em.group(1).strip()

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
    """Decompose text into EDUs using the model-first pipeline."""

    def __init__(self, use_llm=False):
        self.use_llm = use_llm

    def decompose(self, text: str) -> List[EDU]:
        """Split text into clauses, then extract grammar from each."""
        text = HEADER_INJECTOR.inject(text)
        raw_clauses = _split_into_clauses(text)
        edus = []
        for i, clause in enumerate(raw_clauses):
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
