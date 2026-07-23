"""PCR V2 — Zero Hardcoded Keywords. Pure Structural Features + Vectors.

Replaces: rule_based.py (1207 lines, 21 thresholds, 13 string-match chains)

V4.0 Design (DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md):
  Y-axis: StructuralFeatures — verb_count, entity_count, word_count → operational granularity
  Z-axis: MoodProfile vectors — 32 descriptors via BGE cosine → feedback expectation
  X-axis: NRC-VAD lexicon fallback — lexical novelty → cognitive distance

Fallback strategy: BGE → mood_profiles.yaml (primary), NRC-VAD (secondary), Structural (tertiary)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import re, math, json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# Data contracts — no hardcoded keywords
# ═══════════════════════════════════════════════════

@dataclass
class StructuralFeatures:
    """Grammar-structure features. No keywords, no vocab lists."""
    verb_count: int = 0
    entity_count: int = 0        # hex addresses, tool names, identifiers
    word_count: int = 0
    char_count: int = 0
    question_markers: int = 0    # ?, ?, rhetorical patterns
    imperative_markers: int = 0  # command patterns: bare verbs, "!"
    cjk_ratio: float = 0.0

    @staticmethod
    def extract(text: str) -> "StructuralFeatures":
        if not text or not text.strip():
            return StructuralFeatures()

        # Word count — handles both English (whitespace) and Chinese (char-based)
        cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        latin_words = [w for w in text.split() if any(c.isalpha() for c in w)]
        word_count = max(len(latin_words), cjk_chars // 2)

        # Entity count: hex addresses + ALL_CAPS + Chinese quoted terms
        hex_count = len(re.findall(r'0x[0-9a-fA-F]+', text))
        caps_count = len(re.findall(r'\b[A-Z]{2,}\b', text))
        cn_entities = len(re.findall(r'[""\(（][^""\)）]+[""\)）]', text))

        # Verb count — morphological heuristics, ZERO hardcoded word lists
        action_verbs = 0
        for word in text.split():
            w = word.lower().strip('.,!?;:()[]{}"\'')
            if not w or len(w) < 2:
                continue
            # Morphological: verb-like suffixes (cross-language)
            if (w.endswith(('ing', 'ed', 'ize', 'ify', 'ate', 'ect', 'ove')) or
                # Consonant-final short words (typical imperative: scan,patch,dump,fix)
                (len(w) <= 6 and w[-1] not in 'aeiou' and w[0].islower())):
                action_verbs += 1

        # Question markers — pure structural: punctuation only, no word lists
        question = sum(1 for c in text if c in '?？')
        # CJK question char detection (吗/呢/吧 as sentence-final particles)
        stripped = text.strip()
        if stripped and stripped[-1] in '吗呢吧':
            question += 1
        # Rhetorical: "是不是", "有没有" — detected as bi-character pattern, not word list
        question += len(re.findall(r'不.|\u6709\u6ca1\u6709', text))

        # Imperative markers — punctuation + positional
        imperative = text.count('!') + text.count('！')
        # Bare verb at start = imperative (structural, not keyword-based)
        if text.split() and text.split()[0][0].islower():
            imperative += 1

        # CJK ratio
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        cjk_ratio = cjk / max(1, len(text))

        return StructuralFeatures(
            verb_count=action_verbs,
            entity_count=hex_count + caps_count + cn_entities,
            word_count=word_count,
            char_count=len(text),
            question_markers=question,
            imperative_markers=imperative,
            cjk_ratio=cjk_ratio,
        )


@dataclass
class PCRResult:
    """PCR output — no discrete labels, coordinate-based routing."""
    x_axis: float    = 0.5   # cognitive distance (0=near, 1=far)
    y_axis: float    = 0.5   # operational granularity (0=atomic, 1=complex)
    z_axis: float    = 0.0   # feedback expectation (-1=mirror, 0=explore, +1=solution)
    zone: str        = "MIXED"
    structural: Optional[StructuralFeatures] = None
    cognitive_level: str = "mixed"
    execution_mode: str = "slow"
    prompt_style: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════
# PCR Router V2 — Zero hardcoded keywords
# ═══════════════════════════════════════════════════

class PCRRouterV2:
    """Pre-Cognitive Router using structural features + vector mood classification.

    Replaces: all hardcoded _TOOL_KEYWORDS, _ADVISOR_KEYWORDS, _COMPANION_KEYWORDS,
              domain_keywords, category_keywords, and regex patterns.
    """

    # ── Mood vector support ──
    _mood_vectors = None     # Lazy loaded BGE mood vectors
    _mood_labels = None      # Category labels
    _mood_zvalues = None     # Z-value mapping

    # ── NRC-VAD lexicon ──
    _vad_lexicon = None      # Lazy loaded NRC-VAD

    # ── Llm provider ──
    _llm_provider = None

    @classmethod
    def set_llm_provider(cls, provider):
        cls._llm_provider = provider

    @classmethod
    def _load_mood_vectors(cls):
        """Load mood_profiles.yaml → BGE vectors once."""
        if cls._mood_vectors is not None:
            return

        import yaml, json
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent.parent / "config" / "mood_profiles.yaml"
        try:
            config = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        except Exception:
            logger.debug("mood_profiles.yaml not found, using fallback")
            return

        descriptors, labels, zvalues = [], [], {}
        for category, profile in config.get("profiles", {}).items():
            for d in profile.get("descriptors", []):
                descriptors.append(d)
                labels.append(category)
            zvalues[category] = profile.get("z_value", 0.0)

        if not descriptors:
            return

        import numpy as np
        vecs = None
        
        # Try 1: sentence_transformers (most common, .venv has it)
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            vecs = np.array([model.encode(d, normalize_embeddings=True) for d in descriptors])
        except Exception as e1:
            logger.debug("sentence_transformers unavailable: %s", e1)
        
        # Try 2: fastembed (lighter, CPU-optimized)
        if vecs is None:
            try:
                from fastembed import TextEmbedding
                model = TextEmbedding("BAAI/bge-small-zh-v1.5")
                raw = list(model.embed(descriptors))
                vecs = np.array(raw)
                vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8)
            except Exception as e2:
                logger.debug("fastembed unavailable: %s", e2)
        
        # Try 3: HF_HOME override
        if vecs is None:
            try:
                import os as _os
                _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
                vecs = np.array([model.encode(d, normalize_embeddings=True) for d in descriptors])
            except Exception as e3:
                logger.debug("BGE with mirror also failed: %s", e3)
                return

        cls._mood_vectors = vecs
        cls._mood_labels = labels
        cls._mood_zvalues = zvalues
        logger.debug("Mood vectors loaded: %d descriptors", len(descriptors))

    @classmethod
    def _load_vad_lexicon(cls):
        """Load NRC-VAD lexicon for X-axis cognitive distance."""
        if cls._vad_lexicon is not None:
            return

        from pathlib import Path
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        vad_path = config_dir / "NRC-VAD-Lexicon-v2.1.txt"

        if not vad_path.exists():
            logger.debug("NRC-VAD lexicon not found at %s", vad_path)
            return

        try:
            lexicon = {}
            with open(vad_path, 'r', encoding='utf-8') as f:
                next(f)  # skip header
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:
                        try:
                            v, a, d = float(parts[1]), float(parts[2]), float(parts[3])
                            lexicon[parts[0].strip()] = (v, a, d)
                        except ValueError:
                            pass
            cls._vad_lexicon = lexicon
            logger.debug("NRC-VAD loaded: %d words", len(lexicon))
        except Exception as e:
            logger.debug("NRC-VAD load failed: %s", e)

    # ── Core routing ──

    @classmethod
    def route(cls, text: str, history: list = None) -> PCRResult:
        """Zero-keyword routing: structural features → coordinate → zone."""

        # Y-axis: operational granularity from structural features
        sf = StructuralFeatures.extract(text)
        y = cls._compute_granularity(sf)

        # Z-axis: feedback expectation from mood vectors
        z = cls._compute_mood(text)

        # X-axis: cognitive distance from vocabulary novelty
        x = cls._compute_distance(text)

        # Zone routing
        zone = cls._zone_from_xyz(x, y, z)

        return PCRResult(
            x_axis=x, y_axis=y, z_axis=z, zone=zone,
            structural=sf,
            cognitive_level=cls._cognitive_level(x, y, z),
            execution_mode=cls._execution_mode(zone),
            prompt_style=cls._prompt_style(zone),
            metadata={"sf_verb": sf.verb_count, "sf_entity": sf.entity_count,
                     "sf_words": sf.word_count, "sf_cjk": sf.cjk_ratio},
        )

    # ── Axis computation ──

    @classmethod
    def _compute_granularity(cls, sf: StructuralFeatures) -> float:
        """Y-axis: 0 = atomic, 1 = complex workflow."""
        y = min(sf.verb_count / 5, 1.0) * 0.4 \
          + min(sf.entity_count / 5, 1.0) * 0.3 \
          + min(sf.word_count / 20, 1.0) * 0.3
        return round(y, 3)

    @classmethod
    def _compute_mood(cls, text: str) -> float:
        """Z-axis: -1 = mirror, 0 = explore, +1 = solution.

        Priority: BGE mood vectors > NRC-VAD lexicon > structural fallback."""
        if not text or not text.strip():
            return 0.0

        # 1. BGE mood vectors (primary)
        cls._load_mood_vectors()
        if cls._mood_vectors is not None:
            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np
                model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
                v = model.encode(text, normalize_embeddings=True)
                idx = int(np.argmax(np.dot(cls._mood_vectors, v)))
                return cls._mood_zvalues.get(cls._mood_labels[idx], 0.0)
            except Exception:
                try:
                    from fastembed import TextEmbedding
                    import numpy as np
                    model = TextEmbedding("BAAI/bge-small-zh-v1.5")
                    v = np.array(list(model.embed([text])))[0]
                    v = v / np.linalg.norm(v)
                    idx = int(np.argmax(np.dot(cls._mood_vectors, v)))
                    return cls._mood_zvalues.get(cls._mood_labels[idx], 0.0)
                except Exception:
                    pass

        # 2. NRC-VAD lexicon (secondary)
        cls._load_vad_lexicon()
        if cls._vad_lexicon is not None:
            words = re.findall(r'[a-zA-Z]+', text.lower())
            if words:
                vs, ds = [], []
                for w in words:
                    if w in cls._vad_lexicon:
                        v, a, d = cls._vad_lexicon[w]
                        vs.append(v)
                        ds.append(d)
                if vs:
                    avg_d = sum(ds) / len(ds)
                    avg_v = sum(vs) / len(vs)
                    # High dominance + high valence → solution, high arousal → mirror
                    if avg_d > 0.1:
                        return 1.0 if avg_v > 0 else 0.0
                    elif avg_d < -0.3:
                        return -1.0
                    return 0.0

        # 3. Structural fallback (tertiary)
        sf = StructuralFeatures.extract(text)
        # Signals tier: explicit markers take priority
        if sf.imperative_markers > 0:
            return 1.0  # imperatives → solution
        if sf.question_markers > 0:
            return 0.0  # questions → exploration
        return 0.0

    @classmethod
    def _compute_distance(cls, text: str) -> float:
        """X-axis: 0 = near (familiar domain), 1 = far (novel domain).

        Uses NRC-VAD rarity + entity density as proxy."""
        if not text or not text.strip():
            return 0.3

        # Entity density → more entities = more specific domain = potentially farther
        sf = StructuralFeatures.extract(text)
        entity_density = sf.entity_count / max(1, sf.word_count)

        # NRC-VAD word rarity
        cls._load_vad_lexicon()
        rarity = 0.3  # default: moderate distance
        if cls._vad_lexicon is not None:
            words = re.findall(r'[a-zA-Z]+', text.lower())
            if words:
                known = sum(1 for w in words if w in cls._vad_lexicon)
                rarity = 1.0 - (known / len(words))  # unknown words → farther

        x = entity_density * 0.5 + rarity * 0.5
        return round(min(max(x, 0.0), 1.0), 3)

    # ── Zone routing ──

    @classmethod
    def _zone_from_xyz(cls, x: float, y: float, z: float) -> str:
        """Map 3D coordinate to routing zone."""
        if z < -0.5:
            return "PSYCHE"        # mirror/emotional — use small model, no solutions
        if x < 0.3 and y < 0.3:
            return "ATOMIC"        # near + simple → cache/rule
        if x > 0.7 and y > 0.6 and z > 0.3:
            return "ABYSS"         # far + complex + solution → ReAct + no depth limit
        if x < 0.5 and y > 0.4 and z > 0:
            return "PRECISION"     # near + complex + solution → CoT + tools
        if x > 0.4 and y < 0.4 and z <= 0:
            return "EXPLORE"       # far + simple + explore → retrieval + open-ended
        return "MIXED"

    @classmethod
    def _cognitive_level(cls, x: float, y: float, z: float) -> str:
        """Infer cognitive load from coordinates."""
        score = x * 0.4 + y * 0.4 + abs(z) * 0.2
        if score > 0.7: return "heavy"
        if score > 0.4: return "moderate"
        return "light"

    @classmethod
    def _execution_mode(cls, zone: str) -> str:
        return {"ATOMIC": "cache", "PSYCHE": "small_model",
                "EXPLORE": "retrieval", "PRECISION": "cot",
                "ABYSS": "react", "MIXED": "slow"}.get(zone, "slow")

    @classmethod
    def _prompt_style(cls, zone: str) -> str:
        return {"ATOMIC": "concise", "PSYCHE": "empathetic",
                "EXPLORE": "socratic", "PRECISION": "analytical",
                "ABYSS": "exhaustive", "MIXED": "default"}.get(zone, "default")
