"""PCR Grammar Tagger — Stanza-based dual-track structural tagging.

Tags: S(subject), V(verb), O(object), C(complement), M(modifier),
      Q(question), IMP(imperative), EMO(emotional), NEG(negation).

Returns tagged structure + raw feature counts for PCR routing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class GrammarTags:
    """Tagged grammatical structure extracted from text."""
    subject: str = ""
    verb: str = ""
    object: str = ""
    complement: str = ""
    modifiers: List[str] = field(default_factory=list)
    
    # Mood/speech-act features
    is_question: bool = False
    is_imperative: bool = False
    is_emotional: bool = False
    has_negation: bool = False
    
    # Counts
    verb_count: int = 0
    entity_count: int = 0
    word_count: int = 0
    
    def to_tag_string(self) -> str:
        """Compact tag string for LLM consumption."""
        parts = []
        if self.subject: parts.append(f"S:{self.subject}")
        if self.verb: parts.append(f"V:{self.verb}")
        if self.object: parts.append(f"O:{self.object}")
        if self.complement: parts.append(f"C:{self.complement}")
        moods = []
        if self.is_question: moods.append("Q")
        if self.is_imperative: moods.append("IMP")
        if self.is_emotional: moods.append("EMO")
        if self.has_negation: moods.append("NEG")
        return "  ".join(parts) + (f"  MOOD:{'|'.join(moods)}" if moods else "")


def tag_text(text: str) -> Optional[GrammarTags]:
    """Tag text using Stanza dependency parsing. Returns None if Stanza unavailable."""
    import re
    
    tags = GrammarTags()
    tags.word_count = len(text.split())
    
    # ── Entity count (structural regex, no keyword lists) ──
    tags.entity_count = len(re.findall(r'0x[0-9a-fA-F]+', text))
    tags.entity_count += len(re.findall(r'\b[A-Z]{2,}\b', text))
    
    try:
        import stanza
        nlp = _get_stanza()
        if nlp is None:
            return None
        doc = nlp(text)
        return _extract_tags(doc, text, tags)
    except Exception as e:
        logger.debug("Stanza tagging failed: %s", e)
        return None


_stanza_nlp = None

def _get_stanza():
    global _stanza_nlp
    if _stanza_nlp is not None:
        return _stanza_nlp
    try:
        import stanza
        # 2026-08-16: 不调 stanza.download（网络受限无 CPU 挂起, 全库
        # 统一修）。download_method=None = 只读缓存, 缺失快速失败。
        _stanza_nlp = stanza.Pipeline(
            'zh', processors='tokenize,pos,lemma,depparse',
            verbose=False, download_method=None)
        return _stanza_nlp
    except Exception:
        return None


def _extract_tags(doc, text: str, tags: GrammarTags) -> GrammarTags:
    """Extract grammatical tags from Stanza doc."""
    sent = doc.sentences[0] if doc.sentences else None
    if not sent:
        return tags
    
    # Track dependents for each word
    for word in sent.words:
        rel = word.deprel.split(":")[0] if word.deprel else ""
        w = word.text.lower()
        
        # Subject detection
        if rel == "nsubj":
            tags.subject = word.text
        # Object detection
        elif rel == "obj":
            tags.object = word.text
        # Complement
        elif rel in ("xcomp", "ccomp"):
            tags.complement = word.text
        # Verb
        if word.upos in ("VERB", "AUX"):
            tags.verb_count += 1
            if not tags.verb:
                tags.verb = word.text
    
    # ── Mood / speech-act detection (structural, zero keyword lists) ──
    
    # Question: "?" or Chinese question particles (吗/呢/吧 at end, structural not semantic)
    if "?" in text or "？" in text:
        tags.is_question = True
    if text.strip().endswith(("吗", "呢", "吧", "么")):
        tags.is_question = True
    
    # Imperative: starts with bare verb + no subject "I"
    if tags.verb and not tags.subject:
        tags.is_imperative = True
    
    # Emotional: exclamation marks, extreme adverbs
    if "!" in text or "！" in text:
        tags.is_emotional = True
    if any(w in text for w in ("太", "好", "废", "累", "坑", "爱", "棒")):
        tags.is_emotional = True
    
    # Negation
    if any(w in text for w in ("不", "没", "无", "未")):
        tags.has_negation = True
    
    return tags


def tag_for_llm_review(text: str) -> str:
    """Generate the grammar review prompt content."""
    tags = tag_text(text)
    if tags is None:
        return ""
    return tags.to_tag_string()
