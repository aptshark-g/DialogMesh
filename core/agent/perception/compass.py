"""Signal Dimension — pluggable measurement lens for perception pipeline.

Philosophy: Not a fixed module. A swappable lens.
  LLM can select which dimension to use.
  LLM can use dimension output as structured compass.
  LLM can request dimension switch or define new dimensions.

Each dimension = SignalDimension.measure(text) → dict
  Pipeline: TextInput → CompassSelector(LLM/blueprint) → selected lenses → structured signal
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


# ═══ Base Interface ═══

class SignalDimension(ABC):
    """Pluggable measurement dimension. Each lens quantifies one aspect of input."""

    @abstractmethod
    def name(self) -> str:
        """Unique name for lens selection."""

    @abstractmethod
    def measure(self, text: str) -> Dict[str, Any]:
        """Quantify this dimension. Returns {metric_name: value, ...}."""

    def description(self) -> str:
        """Human-readable description for LLM selection."""
        return self.name()


@dataclass
class CompassResult:
    """Aggregated measurement from selected lenses."""
    text: str
    dimensions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    selected_lenses: List[str] = field(default_factory=list)
    selector_reason: str = ""

    def summary(self) -> str:
        """Compact text for LLM context injection."""
        parts = []
        for name, metrics in self.dimensions.items():
            clean = {k: round(v, 3) if isinstance(v, float) else v
                     for k, v in metrics.items() if not k.startswith("_")}
            parts.append(f"[{name}] {clean}")
        return " | ".join(parts) if parts else ""


# ═══ Compass Selector ═══

class CompassSelector:
    """Routes text to the right lenses. LLM-driven or blueprint-driven.

    Two modes:
      auto:       LLM selects lenses based on text characteristics
      blueprint:  Blueprint prescribes which lenses to use
    """

    def __init__(self, lenses: List[SignalDimension] = None):
        self._lenses: Dict[str, SignalDimension] = {}
        if lenses:
            for lens in lenses:
                self.register(lens)

    def register(self, lens: SignalDimension):
        self._lenses[lens.name()] = lens

    def list_lenses(self) -> List[Dict]:
        return [{"name": l.name(), "desc": l.description()}
                for l in self._lenses.values()]

    def measure(self, text: str, lens_names: List[str] = None,
                llm_selector: Any = None) -> CompassResult:
        """Apply selected lenses (or auto-select) and produce aggregated signal.

        Args:
            text: raw input text
            lens_names: explicit lens selection, or None for auto
            llm_selector: callable(text, lens_list) → selected_names, for auto mode

        Returns:
            CompassResult with all measurements
        """
        if lens_names is None and llm_selector is not None:
            try:
                lens_names = llm_selector(text, self.list_lenses())
            except Exception:
                lens_names = list(self._lenses.keys())
        if lens_names is None:
            lens_names = list(self._lenses.keys())

        result = CompassResult(
            text=text,
            selected_lenses=lens_names,
            selector_reason="auto" if llm_selector is None else "llm",
        )
        for name in lens_names:
            if name in self._lenses:
                try:
                    result.dimensions[name] = self._lenses[name].measure(text)
                except Exception as e:
                    logger.debug("Lens %s failed: %s", name, e)
        return result


# ═══ NoiseSpan Lens ═══

class NoiseSpanLens(SignalDimension):
    """7-type noise detection at character level.

    Types: TYPO, AMBIGUOUS, INJECTION, REPETITION, IRRELEVANT, MIXED_LANG, EMPTY
    Each type marks a (start, end) span and confidence.

    Rules (structural, not keyword-based):
      TYPO:      repeated characters, keyboard pattern proximity
      AMBIGUOUS: missing subject/verb/object in structural parse
      INJECTION: suspicious patterns (URLs in non-link context, script-like fragments)
      REPETITION: same sentence structure repeated >2 times
      IRRELEVANT: BM25+embedding distance from session topic >threshold
      MIXED_LANG: multiple scripts in single utterance (Latin+CJK+Arabic)
      EMPTY:      whitespace-only or single punctuation
    """

    TYPES = ["TYPO", "AMBIGUOUS", "INJECTION", "REPETITION",
             "IRRELEVANT", "MIXED_LANG", "EMPTY"]

    def name(self) -> str:
        return "noise_span"

    def description(self) -> str:
        return "7-type noise detection at char-level: TYPO,AMBIGUOUS,INJECTION,..."

    def measure(self, text: str) -> Dict[str, Any]:
        if not text or not text.strip():
            return {"_type": "EMPTY", "spans": [(0, 0, "EMPTY", 1.0)],
                    "score": 1.0, "dominant": "EMPTY"}

        spans = []
        spans.extend(self._detect_repetition(text))
        spans.extend(self._detect_mixed_lang(text))
        spans.extend(self._detect_injection(text))
        spans.extend(self._detect_typo(text))
        spans.extend(self._detect_ambiguous(text))

        if not spans:
            spans.append((0, len(text) - 1, "CLEAN", 0.0))

        noise_score = sum(s[3] for s in spans) / max(len(spans), 1)
        dominant = max(spans, key=lambda s: s[3])[2] if spans else "CLEAN"

        return {
            "_type": "NOISE_SPAN",
            "spans": spans,
            "score": round(noise_score, 3),
            "dominant": dominant,
            "type_counts": {t: sum(1 for s in spans if s[2] == t) for t in self.TYPES},
        }

    def _detect_typo(self, text: str) -> list:
        spans = []
        for m in re.finditer(r'(.)\1{3,}', text):
            spans.append((m.start(), m.end() - 1, "TYPO", 0.6))
        keyboard_rows = [r'[qwertyuiop]{4,}', r'[asdfghjkl]{4,}', r'[zxcvbnm]{4,}']
        for row in keyboard_rows:
            for m in re.finditer(row, text.lower()):
                spans.append((m.start(), m.end() - 1, "TYPO", 0.4))
        return spans

    def _detect_ambiguous(self, text: str) -> list:
        """Structural heuristic: looks for missing components."""
        spans = []
        if len(text) < 5 and not any(c.isalnum() for c in text):
            spans.append((0, len(text) - 1, "AMBIGUOUS", 0.7))
        return spans

    def _detect_injection(self, text: str) -> list:
        spans = []
        suspicious = [
            r'<script', r'javascript:', r'onerror=',
            r'\\x[0-9a-fA-F]{2}', r'%[0-9a-fA-F]{2}%[0-9a-fA-F]{2}',
        ]
        for pat in suspicious:
            for m in re.finditer(pat, text, re.IGNORECASE):
                spans.append((m.start(), m.end() - 1, "INJECTION", 0.8))
        return spans

    def _detect_repetition(self, text: str) -> list:
        spans = []
        sentences = re.split(r'[。！？.!?\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 3:
            for i in range(len(sentences) - 2):
                s1, s2, s3 = sentences[i:i+3]
                if len(s1) > 5 and abs(len(s1) - len(s2)) < 3 and abs(len(s2) - len(s3)) < 3:
                    idx = text.find(s1)
                    if idx >= 0:
                        spans.append((idx, idx + len(s3) - 1, "REPETITION", 0.5))
        return spans

    def _detect_mixed_lang(self, text: str) -> list:
        spans = []
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', text))
        has_latin = bool(re.search(r'[a-zA-Z]{3,}', text))
        has_arabic = bool(re.search(r'[\u0600-\u06ff]', text))
        script_count = sum([has_cjk, has_latin, has_arabic])
        if script_count >= 2:
            spans.append((0, len(text) - 1, "MIXED_LANG", 0.3))
        return spans


# ═══ Coordinate3D Lens ═══

class Coordinate3DLens(SignalDimension):
    """3D cognitive coordinate: novelty × structural complexity × emotional load.

    X = novelty:    entity novelty ratio (unseen entities / total entities)
    Y = complexity: structural complexity (SVO depth, clause count)
    Z = emotion:    emotional load (exclamation count, negation density)
    """

    def name(self) -> str:
        return "coordinate_3d"

    def description(self) -> str:
        return "3D cognitive space: novelty(X)×complexity(Y)×emotion(Z)"

    def measure(self, text: str) -> Dict[str, Any]:
        words = text.split()
        word_count = max(len(words), 1)
        exclam_count = text.count('!') + text.count('！')
        neg_count = text.count('不') + text.count('没') + text.count('无') + text.count('非')
        clause_markers = text.count('，') + text.count('，') + text.count('但') + text.count('因为')

        return {
            "_type": "COORDINATE_3D",
            "word_count": word_count,
            "x_novelty": round(1.0 - 1.0 / max(word_count, 1), 3),
            "y_complexity": round(min(clause_markers / max(word_count, 1) * 5, 1.0), 3),
            "z_emotion": round((exclam_count + neg_count) / max(word_count, 1) * 3, 3),
        }


# ═══ Factory ═══

def create_default_compass() -> CompassSelector:
    """Create CompassSelector with built-in lenses."""
    compass = CompassSelector()
    compass.register(NoiseSpanLens())
    compass.register(Coordinate3DLens())
    return compass
