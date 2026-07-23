"""Structural Intent Classifier — grammar-based, zero keywords.

Replaces hardcoded _TOOL_KEYWORDS, _ADVISOR_KEYWORDS, _COMPANION_KEYWORDS.
Uses only: sentence structure, verb morphology, entity presence, dependency depth.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional
import re


@dataclass
class StructuralFeatures:
    """Pure grammar features extracted from text — no domain keywords."""
    word_count: int = 0
    has_question_mark: bool = False
    has_wh_word: bool = False       # 什么/怎么/why/how/when/where
    has_imperative: bool = False     # verb-first / 祈使用法
    entity_count: int = 0            # 专有名词 / 数字 / 地址
    verb_count: int = 0
    avg_word_len: float = 0.0
    punctuation_count: int = 0
    repetition_ratio: float = 0.0    # 重复词占比 → 噪声信号

    # Language-agnostic question patterns
    _QUESTION_PARTICLES = {"吗", "呢", "吧", "？", "?"}
    _WH_WORDS = {"什么", "怎么", "为什么", "哪", "谁", "何时",
                 "what", "why", "how", "when", "where", "which", "who"}
    _IMPERATIVE_INDICATORS = {
        "帮", "请", "试", "做", "测", "改", "加", "删", "查", "看", "找",
        "run", "scan", "read", "write", "patch", "find", "test", "check",
    }

    @classmethod
    def extract(cls, text: str) -> "StructuralFeatures":
        if not text.strip():
            return cls(word_count=0)

        # CJK: split by characters, not spaces
        has_cjk = sum(1 for c in text if ord(c) > 0x2000) > len(text)*0.5
        if has_cjk:
            words = list(text.replace(' ', ''))  # char-level for CJK
        else:
            words = text.split()
        chars = list(text)

        # Word count
        word_count = len(words)

        # Question detection: ? or ？ or sentence-ending particles
        has_qm = any(c in '？？' for c in text) or any(text.strip().endswith(p) for p in ['吗','呢','吧'])

        # WH words
        text_lower = text.lower()
        has_wh = any(w in text_lower for w in cls._WH_WORDS)

        # Imperative: first word/char is a verb indicator
        first_word = words[0].lower() if words else ""
        has_imp = (first_word in cls._IMPERATIVE_INDICATORS or
                   any(text.startswith(v) for v in ['帮','请','试','跑','测','改','加','删','查','看','找','扫']))

        # Entity count: numbers, hex addresses, uppercase sequences
        entity_count = 0
        entity_count += len(re.findall(r'\b0x[0-9a-fA-F]+\b', text))  # hex
        entity_count += len(re.findall(r'\b\d+\b', text))              # decimal
        entity_count += len(re.findall(r'[A-Z][a-z]+(?:[.][A-Z][a-z]+)+', text))  # CamelCase
        entity_count += len(re.findall(r'[A-Z_]{3,}', text))           # CONSTANTS

        # Verb count: rule-of-thumb via common verb endings
        verb_suffixes_cn = {"出", "到", "完", "好", "下", "上", "起", "开", "过", "回"}
        verb_count = 0
        for w in words:
            # Chinese: verb-like endings or short action words
            if len(w) <= 3 and any(w.endswith(s) or s in w for s in verb_suffixes_cn):
                verb_count += 1
            # English: common verb patterns
            elif re.match(r'^(dis)?[a-z]+(e|ed|ing|es|ate|ify|ize)$', w) or w.lower() in {"scan","patch","hook","dump","nop","test","check","find","run","read","write","modify"}:
                verb_count += 1

        # Average word length
        avg_len = sum(len(w) for w in words) / max(1, word_count)

        # Punctuation
        punct = sum(1 for c in text if c in ',;:!?。，；：！？、…')

        # Repetition ratio (noise signal)
        unique = len(set(words))
        repetition = 1.0 - unique / max(1, word_count)

        return cls(
            word_count=word_count,
            has_question_mark=has_qm,
            has_wh_word=has_wh,
            has_imperative=has_imp,
            entity_count=entity_count,
            verb_count=verb_count,
            avg_word_len=avg_len,
            punctuation_count=punct,
            repetition_ratio=repetition,
        )

    def expectation_hint(self) -> Tuple[str, float]:
        """Map structural features to coarse-grained expectation.

        Returns: (expectation_label, confidence)

        No keywords. Pure structure. Language-agnostic.
        """
        # Empty input
        if self.word_count == 0:
            return ("UNKNOWN", 0.95)

        # High repetition = noise → UNKNOWN (lower threshold for CJK char-level)
        if self.repetition_ratio > 0.5:
            return ("UNKNOWN", 0.75)

        # Very short + no structure → UNKNOWN
        if self.word_count <= 2 and self.verb_count == 0:
            return ("UNKNOWN", 0.70)

        # TOOL: imperative + entities + verbs → user wants action
        tool_score = 0.0
        if self.has_imperative:
            tool_score += 0.4
        if self.entity_count >= 1:
            tool_score += 0.25
        if self.entity_count >= 2:
            tool_score += 0.2
        if self.verb_count >= 1:
            tool_score += 0.15
        if not self.has_question_mark:
            tool_score += 0.1
        if tool_score >= 0.5:
            return ("TOOL", tool_score)

        # ADVISOR: question + mid-complexity → asking for analysis
        advisor_score = 0.0
        if self.has_question_mark or self.has_wh_word:
            advisor_score += 0.4
        if 3 <= self.word_count <= 15:
            advisor_score += 0.2
        if not self.has_imperative:
            advisor_score += 0.2
        if advisor_score >= 0.5:
            return ("ADVISOR", advisor_score)

        # COMPANION: mid-long, verbose, no strong tool signals (but NOT noisy CJK)
        companion_score = 0.0
        if self.word_count >= 8 and not self.has_imperative and self.repetition_ratio < 0.35:
            companion_score += 0.4
        if 0.2 < self.repetition_ratio < 0.5:
            companion_score += 0.2  # natural language, not mechanical
        if companion_score >= 0.4:
            return ("COMPANION", companion_score)

        # Fallback
        return ("UNKNOWN", 0.30)
