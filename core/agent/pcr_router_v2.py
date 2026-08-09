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

from core.agent.pcr_dimensions import run_axis

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
    labels: Dict[str, str] = field(default_factory=dict)  # compass labels (§2.3)
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
    def warm_up(cls, config: dict = None):
        """Lifecycle warm-up (IPCRRouter contract). Local-only init, no external calls.

        Pre-loads lazy assets (mood vectors / NRC-VAD lexicon) so the first
        route() call does not pay the cold-start cost. Config is accepted for
        interface compatibility and currently unused — structural routing is
        stateless.
        """
        try:
            cls._load_mood_vectors()
        except Exception:
            pass
        try:
            cls._load_vad_lexicon()
        except Exception:
            pass

    @classmethod
    def shutdown(cls):
        """Lifecycle shutdown (IPCRRouter contract). Idempotent no-op."""
        cls._mood_vectors = None
        cls._mood_labels = None
        cls._mood_zvalues = None
        cls._vad_lexicon = None

    @classmethod
    def _load_mood_vectors(cls):
        """Load mood_profiles.yaml → BGE vectors once."""
        if cls._mood_vectors is not None:
            return

        # Offline-first: model weights are cached locally (HF_HUB_OFFLINE).
        # Prevents sentence_transformers from probing huggingface.co and
        # failing the whole mood path when the network is restricted.
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        import yaml, json
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "config" / "mood_profiles.yaml"
        try:
            config = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        except Exception:
            logger.debug("mood_profiles.yaml not found, using fallback")
            return

        descriptors, labels, zvalue_list, zvalues = [], [], [], {}
        for category, profile in config.get("profiles", {}).items():
            for d in profile.get("descriptors", []):
                descriptors.append(d)
                labels.append(category)
                zvalue_list.append(profile.get("z_value", 0.0))
            for d in profile.get("descriptors_zh", []):
                descriptors.append(d)
                labels.append(category)
                zvalue_list.append(profile.get("z_value", 0.0))
            zvalues[category] = profile.get("z_value", 0.0)

        if not descriptors:
            return

        import numpy as np
        vecs = None

        # Try 0: 复用 SemanticEncoder（GAP-O3 模型统一）— 若本地 bge-small-zh
        # 已就绪, 优先用它（与上下文/子图共用单模型内存, 消除双模型并存）。
        # 无本地模型时静默回退现有链（不新增失败路径）。
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            enc = SemanticEncoder()
            # 本地模型存在才尝试（否则抛 FileNotFoundError → 回退）
            if enc is not None:
                vecs = np.array([
                    enc.encode(d) for d in descriptors
                ])
                vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8)
                cls._local_embed_model = enc
                cls._mood_source = "semantic_encoder"
                logger.debug("SemanticEncoder loaded: %d descriptors", len(descriptors))
        except Exception as e0:
            logger.debug("SemanticEncoder unavailable, fallback chain: %s", e0)
            vecs = None

        # Try 1: LM Studio nomic embedding (local, no numpy conflict)
        if vecs is None:
            try:
                import urllib.request, json
                embeddings = []
                for d in descriptors:
                    req = urllib.request.Request(
                        "http://127.0.0.1:1234/v1/embeddings",
                        data=json.dumps({"model": "text-embedding-nomic-embed-text-v1.5", "input": d}).encode(),
                        headers={"Content-Type": "application/json"}
                    )
                    resp = urllib.request.urlopen(req, timeout=5)
                    emb = json.loads(resp.read())["data"][0]["embedding"]
                    embeddings.append(emb)
                vecs = np.array(embeddings)
                vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8)
                cls._mood_source = "nomic"
                logger.debug("LM Studio nomic loaded: %d descriptors", len(descriptors))
            except Exception as e1:
                logger.debug("LM Studio nomic unavailable: %s", e1)

        # Try 2: sentence_transformers
        if vecs is None:
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
                vecs = np.array([model.encode(d, normalize_embeddings=True) for d in descriptors])
                cls._local_embed_model = model
                cls._mood_source = "bge"
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
                cls._local_embed_model = model
                cls._mood_source = "bge"
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
                cls._local_embed_model = model
                cls._mood_source = "bge"
            except Exception as e3:
                logger.debug("BGE with mirror also failed: %s", e3)
                return

        cls._mood_vectors = vecs
        cls._mood_labels = labels
        cls._mood_zvalues = zvalues
        cls._mood_zvalue_list = zvalue_list
        logger.debug("Mood vectors loaded: %d descriptors", len(descriptors))

    @classmethod
    def _load_vad_lexicon(cls):
        """Load NRC-VAD lexicon for X-axis cognitive distance."""
        if cls._vad_lexicon is not None:
            return

        from pathlib import Path
        config_dir = Path(__file__).parent.parent.parent / "config"
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
    def route(cls, text: str, history: list = None,
              subgraph_prior: str = None) -> PCRResult:
        """Zero-keyword routing: structural features → coordinate → zone.

        subgraph_prior: expected-context text from the subgraph/association
        chain (DESIGN_PCR §5). When provided, X-axis distance is measured
        against this real reference (1 - cos(query, prior)); without it, X
        degrades explicitly to structural novelty (no fake baseline).
        """

        # Dimension units (DESIGN_PCR §3.1): each axis is a registry of
        # deterministic/vector/llm units; first non-None wins.
        sf = StructuralFeatures.extract(text)
        ctx = {"structural": sf, "prior": subgraph_prior}

        y = run_axis("y", text, ctx)
        z = run_axis("z", text, ctx)
        x = run_axis("x", text, ctx)

        # Defensive defaults — every axis has a terminal deterministic unit,
        # but never let a unit failure break the router.
        y = y if y is not None else 0.5
        z = z if z is not None else 0.0
        x = x if x is not None else 0.3

        # Zone routing
        zone = cls._zone_from_xyz(x, y, z)
        
        # LLM Collaborative Review (local model auto-detect, remote model optional)
        reviewed = cls._llm_review(text, x, y, z, sf)
        if reviewed:
            x2, y2, z2 = reviewed["x"], reviewed["y"], reviewed["z"]
            if any(abs(a-b) > 0.3 for a,b in [(x,x2),(y,y2),(z,z2)]):
                zone = cls._zone_from_xyz(x2, y2, z2)
                x, y, z = x2, y2, z2
                logger.debug("PCR reviewed: new zone=%s", zone)

        return PCRResult(
            x_axis=x, y_axis=y, z_axis=z, zone=zone,
            labels=cls._compass_labels(x, y, z, zone),
            structural=sf,
            cognitive_level=cls._cognitive_level(x, y, z),
            execution_mode=cls._execution_mode(zone),
            prompt_style=cls._prompt_style(zone),
            metadata={"sf_verb": sf.verb_count, "sf_entity": sf.entity_count,
                     "sf_words": sf.word_count, "sf_cjk": sf.cjk_ratio},
        )

    @classmethod
    def _compass_labels(cls, x: float, y: float, z: float, zone: str) -> Dict[str, str]:
        """Compass labels for LLM navigation (DESIGN_PCR §2.3).

        Deterministic approximation until the LLM compass (JSON-schema
        constrained, §3.3.4) lands: temperature from z, distance from x,
        value from zone semantics. Two views stay independent — labels serve
        the LLM, coordinates serve the algorithm; conflicts are recorded, not
        arbitrated.
        """
        temperature = "neutral"
        if z < -0.15:
            temperature = "cold"
        elif z > 0.15:
            temperature = "warm"

        distance = "mid"
        if x < 0.2:
            distance = "near"
        elif x > 0.5:
            distance = "far"

        value = {"PRECISION": "high", "ABYSS": "high",
                 "ATOMIC": "medium", "EXPLORE": "medium",
                 "PSYCHE": "low", "MIXED": "low"}.get(zone, "medium")

        return {"temperature": temperature, "distance": distance, "value": value}

    # ── Axis computation — unit forwarding methods (DESIGN_PCR §3.1) ──
    # Each method backs one registered DimensionUnit; return None to let the
    # next unit in the axis take over. Behaviour identical to the pre-split
    # single _compute_* methods.

    @classmethod
    def _granularity_structural(cls, text: str, sf: StructuralFeatures) -> Optional[float]:
        """Y: formula value, or None when LLM gap-fill should take over."""
        if sf is None:
            return None
        if sf.entity_count == 0 and len(text or "") > 10:
            return None  # let the LLM entity unit fill the gap first
        y = min(sf.verb_count / 5, 1.0) * 0.4 \
          + min(sf.entity_count / 5, 1.0) * 0.3 \
          + min(sf.word_count / 20, 1.0) * 0.3
        return round(y, 3)

    @classmethod
    def _granularity_llm(cls, text: str, sf: StructuralFeatures) -> Optional[float]:
        """Y: LLM entity gap-fill recompute (only when structural yields none)."""
        if not text or not text.strip() or sf is None:
            return None
        if sf.entity_count > 0 or len(text) <= 10:
            return None  # no gap to fill — structural unit already handled it
        llm_ents = cls._llm_entities(text)
        if llm_ents:
            sf.entity_count = max(sf.entity_count, llm_ents)
        # Direct formula — must NOT re-enter _granularity_structural, which
        # would yield again (entity_count may still be 0 → None → y=0.5
        # fallback, collapsing zh/en into a fake "consistent" MIXED).
        y = min(sf.verb_count / 5, 1.0) * 0.4 \
          + min(sf.entity_count / 5, 1.0) * 0.3 \
          + min(sf.word_count / 20, 1.0) * 0.3
        return round(y, 3)

    @classmethod
    def _mood_vector(cls, text: str) -> Optional[float]:
        """Z: mood class-aggregated soft vote (WEAK signal offline, see §8.2)."""
        if not text or not text.strip():
            return None
        cls._load_mood_vectors()
        if cls._mood_vectors is None:
            return None
        v = cls._query_embed(text)
        if v is None:
            return None
        import numpy as np
        v = np.asarray(v, dtype=np.float64)
        if v.ndim == 1:
            v = v[np.newaxis, :]
        scores = np.dot(cls._mood_vectors, v.T).flatten()
        class_scores = {}
        for i, lab in enumerate(cls._mood_labels):
            class_scores[lab] = max(class_scores.get(lab, -1e9), scores[i])
        cats = list(class_scores.keys())
        cs = np.array([class_scores[c] for c in cats], dtype=np.float64)
        # softmax temperature from config (baseline 0.15); adaptive tier later
        from core.agent.pcr_dimensions import axis_config
        temp = float(axis_config("z").get("softmax_temp", 0.15))
        exp_s = np.exp((cs - cs.max()) / temp)
        w = exp_s / exp_s.sum()
        zv = np.array([cls._mood_zvalues[c] for c in cats], dtype=np.float64)
        z = float(np.dot(w, zv))
        return round(max(-1.0, min(1.0, z)), 3)

    @classmethod
    def _mood_nrc(cls, text: str) -> Optional[float]:
        """Z: NRC-VAD lexicon (English dominance/valence)."""
        if not text or not text.strip():
            return None
        cls._load_vad_lexicon()
        if cls._vad_lexicon is None:
            return None
        words = re.findall(r'[a-zA-Z]+', text.lower())
        if not words:
            return None
        vs, ds = [], []
        for w in words:
            if w in cls._vad_lexicon:
                v, a, d = cls._vad_lexicon[w]
                vs.append(v)
                ds.append(d)
        if not vs:
            return None
        avg_d = sum(ds) / len(ds)
        avg_v = sum(vs) / len(vs)
        if avg_d > 0.1:
            return 1.0 if avg_v > 0 else 0.0
        elif avg_d < -0.3:
            return -1.0
        return 0.0

    @classmethod
    def _mood_structural(cls, text: str) -> Optional[float]:
        """Z: imperative/question structural fallback (terminal unit)."""
        if not text or not text.strip():
            return 0.0
        sf = StructuralFeatures.extract(text)
        if sf.imperative_markers > 0:
            return 1.0
        if sf.question_markers > 0:
            return 0.0
        return 0.0

    @classmethod
    def _distance_prior(cls, text: str, prior: str) -> Optional[float]:
        """X: 1 - cos(query, prior) with shared-vocab correction.

        DATA (2026-08-01): short-text BGE 1-cos has poor resolution as a
        novelty meter ("量子退火 + related prior" → X=0.51). Only reliable
        when prior is a REAL subgraph/history vector (§5 pull_prior).
        """
        if not text or not text.strip() or not prior or not prior.strip():
            return None
        qv = cls._local_embed(text)
        pv = cls._local_embed(prior)
        if qv is None or pv is None:
            return None
        import numpy as np
        qv = np.asarray(qv, dtype=np.float64)
        pv = np.asarray(pv, dtype=np.float64)
        cos = float(np.dot(qv, pv) / (max(1e-8, np.linalg.norm(qv) * np.linalg.norm(pv))))
        semantic_distance = 1.0 - cos
        q_words = set(re.findall(r'[a-zA-Z\u4e00-\u9fff]+', text.lower()))
        p_words = set(re.findall(r'[a-zA-Z\u4e00-\u9fff]+', prior.lower()))
        overlap = len(q_words & p_words) / max(1, len(q_words))
        return min(1.0, semantic_distance * 0.7 + (1.0 - overlap) * 0.3)

    @classmethod
    def _distance_svo_nomic(cls, text: str, sf: StructuralFeatures) -> Optional[float]:
        """X: Stanza SVO subject/object cosine via nomic (LM Studio)."""
        if not text or not text.strip() or sf is None:
            return None
        try:
            import stanza, urllib.request, json
            nlp = cls._get_stanza()
            if not nlp:
                return None
            doc = nlp(text)
            if not doc.sentences:
                return None
            words = doc.sentences[0].words
            s_words = [w.text for w in words if w.deprel and 'nsubj' in w.deprel]
            o_words = [w.text for w in words if w.deprel and w.deprel.split(':')[0] == 'obj']
            if not s_words or not o_words:
                return None
            s_emb = cls._nomic_embed(s_words[0])
            o_emb = cls._nomic_embed(o_words[0])
            if not s_emb or not o_emb:
                return None
            cos = sum(a*b for a,b in zip(s_emb, o_emb)) / (
                max(1e-8, sum(x*x for x in s_emb)**0.5 * sum(x*x for x in o_emb)**0.5))
            semantic_distance = 1.0 - cos
            idf_avg = len(set(s_words + o_words)) / max(1, sf.word_count)
            return min(1.0, semantic_distance * 0.7 + idf_avg * 0.3)
        except Exception:
            return None

    @classmethod
    def _distance_nrc_rarity(cls, text: str, sf: StructuralFeatures) -> Optional[float]:
        """X: English NRC-VAD word rarity."""
        if not text or not text.strip() or sf is None:
            return None
        english_words = re.findall(r'[a-zA-Z]+', text)
        if not english_words or len(english_words) <= len(text.split()) * 0.5:
            return None
        entity_density = sf.entity_count / max(1, sf.word_count)
        cls._load_vad_lexicon()
        if not cls._vad_lexicon:
            return None
        known = sum(1 for w in english_words if w.lower() in cls._vad_lexicon)
        rarity = 1.0 - (known / max(1, len(english_words)))
        return min(1.0, entity_density * 0.3 + rarity * 0.7)

    @classmethod
    def _distance_entity(cls, text: str, sf: StructuralFeatures) -> Optional[float]:
        """X: explicit structural degradation (terminal unit)."""
        if sf is None:
            return 0.3
        entity_density = sf.entity_count / max(1, sf.word_count)
        return min(1.0, entity_density * 0.5 + 0.3)

    @classmethod
    def _nomic_embed(cls, word: str) -> Optional[list]:
        """Get nomic embedding for a word via LM Studio."""
        try:
            import urllib.request, json
            req = urllib.request.Request("http://127.0.0.1:1234/v1/embeddings",
                data=json.dumps({"model":"text-embedding-nomic-embed-text-v1.5","input":[word]}).encode(),
                headers={"Content-Type":"application/json"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            return data["data"][0]["embedding"]
        except Exception:
            return None

    @classmethod
    def _local_embed(cls, text: str) -> Optional[list]:
        """Local BGE embedding — offline replacement for LM Studio HTTP.

        Uses the same model that built _mood_vectors (sentence_transformers or
        fastembed). Returns a normalized vector list, or None on any failure.
        """
        model = getattr(cls, '_local_embed_model', None)
        if model is None:
            return None
        try:
            import numpy as np
            if hasattr(model, 'embed'):
                # fastembed: model.embed(list[str]) -> iterable of ndarray
                raw = list(model.embed([text]))
                if not raw:
                    return None
                v = np.asarray(raw[0], dtype=np.float64)
            else:
                # sentence_transformers: model.encode(str, normalize_embeddings=True)
                v = np.asarray(model.encode(text, normalize_embeddings=True), dtype=np.float64)
            if v.size == 0:
                return None
            return v.tolist()
        except Exception as e:
            logger.debug("local embed failed: %s", e)
            return None

    @classmethod
    def _query_embed(cls, text: str) -> Optional[list]:
        """Encode a query with the SAME embedder that built _mood_vectors.

        Mood vectors can come from LM Studio nomic (768d) or local BGE (512d);
        dot product requires matching dimensions. _mood_source records which
        one was used at load time so the query side never mismatches.
        """
        if getattr(cls, '_mood_source', None) == "nomic":
            return cls._nomic_embed(text)
        return cls._local_embed(text)

    @classmethod
    def _get_stanza(cls):
        if not hasattr(cls, '_stanza_nlp'):
            try:
                import stanza
                stanza.download('zh', verbose=False)
                cls._stanza_nlp = stanza.Pipeline('zh', processors='tokenize,pos,lemma,depparse', verbose=False)
            except Exception:
                cls._stanza_nlp = None
        return cls._stanza_nlp

    # ── Zone routing ──

    @classmethod
    def _zone_from_xyz(cls, x: float, y: float, z: float) -> str:
        """Map 3D coordinate to routing zone.

        Thresholds = DESIGN_PCR §8.1 baseline (aligned with coordinate_router).
        v2 "relaxed" set (0.3/0.3; abyss z>0.3) retired — single source of truth.
        """
        if z < -0.5:
            return "PSYCHE"        # mirror/emotional — use small model, no solutions
        if x < 0.2 and y < 0.2:
            return "ATOMIC"        # near + simple → cache/rule
        if x > 0.7 and y > 0.7 and z > 0.5:
            return "ABYSS"         # far + complex + solution → ReAct + no depth limit
        if x < 0.5 and y > 0.5 and z > 0:
            return "PRECISION"     # near + complex + solution → CoT + tools
        if x > 0.5 and y < 0.5 and z <= 0:
            return "EXPLORE"       # far + simple + explore → retrieval + open-ended
        return "MIXED"

    # ── LLM Collaborative Review (nemotron / small model) ──

    _llm_review_enabled: bool = None  # None=auto-detect, True/False=override
    _llm_review_provider = None

    # ── LLM Entity Extraction (structural first, LLM fills gaps) ──

    @classmethod
    def _llm_entities(cls, text: str) -> int:
        """Use LLM to identify specialized entities that regex misses.
        Only called when StructuralFeatures finds 0 entities in text > 10 chars."""
        if not cls._should_review():
            return 0
        try:
            import urllib.request, json, re
            provider = cls._llm_review_provider
            prompt = f"List ONLY domain-specific terms/tools/algorithms in this text. Comma-separated, max 5: {text[:200]}"
            if provider:
                resp = provider.generate(prompt, max_tokens=50, temperature=0.1)
            else:
                req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps({"model":"nvidia/nemotron-3-nano-4b","messages":[{"role":"user","content":prompt}],"max_tokens":50,"temperature":0.1}).encode(),
                    headers={"Content-Type":"application/json"})
                r = urllib.request.urlopen(req, timeout=10)
                resp = json.loads(r.read())["choices"][0]["message"].get("content","") or \
                       json.loads(r.read())["choices"][0]["message"].get("reasoning_content","")
            terms = [t.strip() for t in re.split(r'[,，\n]', str(resp)) if len(t.strip()) > 1]
            return len(terms)
        except Exception:
            return 0

    @classmethod
    def _auto_detect_llm(cls) -> bool:
        """Auto-detect local model and return size category: 'small','medium','large',None."""
        try:
            import urllib.request, json, re
            req = urllib.request.Request("http://127.0.0.1:1234/v1/models")
            data = json.loads(urllib.request.urlopen(req, timeout=2).read())
            # Try to find model name from LM Studio response
            models = data.get("data", []) if isinstance(data, dict) else data
            name = ""
            for m in models:
                name = m.get("id", "") if isinstance(m, dict) else str(m)
                if name: break
            
            # Known model sizes
            SMALL = ["1b","3b","qwen-1","tiny","small"]
            MEDIUM = ["7b","8b","13b","qwen-7","llama-3","mistral","gemma-2"]
            LARGE = ["70b","72b","405b","deepseek","claude","gpt"]
            
            nl = name.lower()
            for p in LARGE:
                if p in nl: return "large"
            for p in MEDIUM:
                if p in nl: return "medium"
            for p in SMALL:
                if p in nl: return "small"
            return "small"  # unknown = assume small
        except Exception:
            return None

    _llm_review_enabled: bool = None
    _llm_review_provider = None
    _model_size: str = None

    @classmethod
    def enable_llm_review(cls, provider=None):
        """Enable LLM review. Pass provider for remote model (DeepSeek)."""
        cls._llm_review_provider = provider
        cls._llm_review_enabled = True

    @classmethod
    def _should_review(cls) -> bool:
        if cls._llm_review_enabled is not None:
            return cls._llm_review_enabled
        size = cls._auto_detect_llm()
        cls._model_size = size
        cls._llm_review_enabled = size is not None
        return cls._llm_review_enabled

    @classmethod
    def _llm_review(cls, text: str, x: float, y: float, z: float, sf) -> Optional[dict]:
        """LLM reviews PCR. Strategy depends on model size:
           small (<7B): 3 minimal signals  |  medium (7-13B): full grammar tags  |  large: PCR only"""
        if not cls._should_review():
            return None
        
        size = cls._model_size or "small"
        
        if size == "medium":
            # Full grammar tags for medium models (structural anchors help)
            try:
                from core.agent.pcr.grammar_tagger import tag_text
                tags = tag_text(text)
                extra = f"\nGRAMMAR: {tags.to_tag_string()}" if tags else ""
            except Exception:
                extra = ""
        elif size == "small":
            # 3 minimal signals for small models (avoid prompt bloat)
            extra = ""
            if "?" in text or "？" in text: extra += " [question]"
            if "!" in text or "！" in text: extra += " [emotion]"
        else:
            extra = ""  # large model: just PCR numbers
        
        prompt = f"""Review routing. PCR: X={x:.2f}(familiar→expert) Y={y:.2f}(simple→complex) Z={z:+.2f}(venting→solution)
TEXT: "{text[:150]}"{extra}
Output ONLY: X <num> Y <num> Z <num>"""

        try:
            import urllib.request, json, re
            provider = cls._llm_review_provider
            if provider:
                resp = provider.generate(prompt, max_tokens=100, temperature=0.1)
            else:
                req = urllib.request.Request(
                    "http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps({"model":"nvidia/nemotron-3-nano-4b","messages":[{"role":"user","content":prompt}],"max_tokens":100,"temperature":0.1}).encode(),
                    headers={"Content-Type":"application/json"})
                r = urllib.request.urlopen(req, timeout=10)
                data = json.loads(r.read())
                resp = data["choices"][0]["message"].get("content","") or \
                       data["choices"][0]["message"].get("reasoning_content","")
            
            nums = [float(t) for t in re.findall(r'[-]?\d+\.?\d*', str(resp))]
            if len(nums) >= 3:
                return {"x": max(0, min(1, nums[0])), "y": max(0, min(1, nums[1])), "z": max(-1, min(1, nums[2]))}
        except Exception:
            pass
        return None

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
