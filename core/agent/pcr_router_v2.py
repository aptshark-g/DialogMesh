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

        config_path = Path(__file__).parent.parent.parent / "config" / "mood_profiles.yaml"
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
        
        # Try 1: LM Studio nomic embedding (local, no numpy conflict)
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
            logger.debug("LM Studio nomic loaded: %d descriptors", len(descriptors))
        except Exception as e1:
            logger.debug("LM Studio nomic unavailable: %s", e1)
        
        # Try 2: sentence_transformers
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
    def route(cls, text: str, history: list = None) -> PCRResult:
        """Zero-keyword routing: structural features → coordinate → zone."""

        # Y-axis: operational granularity from structural features
        sf = StructuralFeatures.extract(text)
        
        # LLM entity gap-fill: regex misses Chinese technical terms
        if sf.entity_count == 0 and len(text) > 10:
            llm_ents = cls._llm_entities(text)
            if llm_ents:
                sf.entity_count = max(sf.entity_count, llm_ents)
        
        y = cls._compute_granularity(sf)

        # Z-axis: feedback expectation from mood vectors
        z = cls._compute_mood(text)

        # X-axis: cognitive distance from vocabulary novelty
        x = cls._compute_distance(text)

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

        # 1. LM Studio nomic mood vectors (primary)
        cls._load_mood_vectors()
        if cls._mood_vectors is not None:
            try:
                import urllib.request, json, numpy as np
                req = urllib.request.Request(
                    "http://127.0.0.1:1234/v1/embeddings",
                    data=json.dumps({"model": "text-embedding-nomic-embed-text-v1.5", "input": text}).encode(),
                    headers={"Content-Type": "application/json"}
                )
                resp = urllib.request.urlopen(req, timeout=5)
                v = np.array(json.loads(resp.read())["data"][0]["embedding"])
                v = v / (np.linalg.norm(v) + 1e-8)
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
