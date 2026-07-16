"""StanzaParser — Chinese dependency parsing via Stanza.

Replaces Tier 2's SpacyBeneparParser for Chinese text.
Stanza provides: POS tagging, dependency parsing, NER, constituency parsing.
Model: zh (Chinese, ~50MB), downloaded on first use.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional
from core.agent.v4.tiered.parser import ParsedClause

logger = logging.getLogger(__name__)


class StanzaParser:
    """Chinese dependency parser using Stanza."""

    def __init__(self, lang: str = "zh"):
        self._lang = lang
        self._nlp = None

    def _ensure_loaded(self):
        if self._nlp is not None:
            return
        try:
            import stanza
            self._nlp = stanza.Pipeline(self._lang, processors="tokenize,lemma,pos,depparse",
                                        verbose=False, use_gpu=False)
            logger.info("Stanza %s pipeline loaded", self._lang)
        except Exception as e:
            logger.warning("Stanza %s unavailable: %s", self._lang, e)

    def available(self) -> bool:
        self._ensure_loaded()
        return self._nlp is not None

    def parse(self, text: str, hint: ParsedClause = None) -> ParsedClause:
        """Parse a single Chinese sentence, returning subject/predicate/object."""
        self._ensure_loaded()
        if self._nlp is None:
            return ParsedClause(raw_text=text, parse_failed=True,
                                parse_failed_reason="stanza_unavailable", tier_used=2)

        doc = self._nlp(text)
        clause = ParsedClause(raw_text=text, tier_used=2)

        # Extract from first sentence
        for sent in doc.sentences:
            # Find root verb (predicate)
            for word in sent.words:
                if word.deprel == "root":
                    clause.predicate = word.text
                    break

            # Find subject (nsubj)
            for word in sent.words:
                if word.deprel == "nsubj":
                    clause.subject = word.text
                    break

            # Find object (obj)
            objs = []
            for word in sent.words:
                if word.deprel in ("obj", "obl"):
                    objs.append(word.text)
            if objs:
                clause.object = " ".join(objs)

            # Collect entities from NER + CamelCase
            import re
            camel = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', text)
            clause.entities = list(set(camel)) if camel else []
            if not clause.entities and clause.subject:
                clause.entities = [clause.subject]
            if clause.object and clause.object not in clause.entities:
                clause.entities.append(clause.object)

            # Confidence scoring
            if clause.predicate and clause.subject and clause.object:
                clause.confidence = 0.92
            elif clause.predicate and clause.subject:
                clause.confidence = 0.85
            elif clause.predicate:
                clause.confidence = 0.75
            else:
                clause.parse_failed = True
                clause.parse_failed_reason = "no_root_verb"
                clause.confidence = 0.0
            break

        return clause

    def extract_tuples(self, text: str) -> List[Dict]:
        """Extract entity-verb-entity tuples from Chinese text."""
        self._ensure_loaded()
        import re
        results = []
        if self._nlp is None:
            return results

        doc = self._nlp(text)
        for sent in doc.sentences:
            words = sent.words
            # Find (subject, root, object) patterns
            subj = None; root_verb = None; objs = []
            for w in words:
                if w.deprel == "nsubj": subj = w.text
                if w.deprel == "root": root_verb = w.text
                if w.deprel in ("obj", "obl"): objs.append(w.text)
            if subj and root_verb:
                obj_text = " ".join(objs) if objs else ""
                results.append({
                    "subject": subj, "predicate": root_verb,
                    "object": obj_text[:80], "type": "relation",
                    "confidence": 0.85,
                })
        return results
