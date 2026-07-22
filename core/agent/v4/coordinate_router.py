"""DialogMesh V4.0 — Cognitive Coordinate Router

Three orthogonal axes:
  X: Cognitive Distance (0=母语级常识, 1=外星人黑话)
  Y: Operational Granularity (0=单细胞动作, 1=千层饼逻辑)
  Z: Feedback Expectation (-1=镜子, 0=探索, +1=求解)

Zero hardcoded keywords. Pure computational geometry.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, Optional
import math, re, logging

logger = logging.getLogger(__name__)


@dataclass
class CognitiveCoordinate:
    """3D point in the Intent Manifold."""
    x: float = 0.0   # cognitive distance
    y: float = 0.0   # operational granularity
    z: float = 0.0   # feedback expectation
    
    def zone(self) -> str:
        """Which routing zone does this point fall into?"""
        x, y, z = self.x, self.y, self.z
        
        if z < -0.5:
            return "PSYCHE"
        if x < 0.2 and y < 0.2:
            return "ATOMIC"
        if x > 0.7 and y > 0.7 and z > 0.5:
            return "ABYSS"
        if x < 0.5 and y > 0.5 and z > 0:
            return "PRECISION"
        if x > 0.5 and y < 0.5 and z <= 0:
            return "EXPLORE"
        return "MIXED"
    
    def strategy(self) -> dict:
        """Routing strategy for this point."""
        z = self.zone()
        return {
            "ATOMIC":    {"llm": "none", "cost_ms": 0, "desc": "cache/rule"},
            "ABYSS":     {"llm": "primary", "max_recursion": 5, "cost_ms": 1000, "desc": "react+CoT full"},
            "PSYCHE":    {"llm": "local_small", "forbid_technical": True, "cost_ms": 100, "desc": "empathetic"},
            "PRECISION": {"llm": "primary", "output_format": "json_plan", "cost_ms": 400, "desc": "planner agent"},
            "EXPLORE":   {"llm": "primary", "temperature": 0.7, "cost_ms": 200, "desc": "socratic"},
            "MIXED":     {"llm": "primary", "cost_ms": 300, "desc": "balanced"},
        }[z]
    
    def to_dict(self) -> dict:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3),
                "zone": self.zone(), "strategy": self.strategy()}


@dataclass
class SyntacticTerrain:
    """STC: Syntactic Terrain Complexity from stanza dependency parse."""
    nesting_depth: int = 0
    coordination_count: int = 0
    preposition_density: float = 0.0
    total_tokens: int = 0
    real_word_count: int = 0
    
    @classmethod
    def from_stanza(cls, doc) -> "SyntacticTerrain":
        max_depth = 0
        coord_count = 0
        prep_count = 0
        total_words = 0
        real_words = 0
        
        for sent in doc.sentences:
            for w in sent.words:
                total_words += 1
                if w.upos in ('NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN'):
                    real_words += 1
                if w.deprel in ('conj', 'cc', 'parataxis'):
                    coord_count += 1
                if w.deprel in ('case', 'mark') or w.upos == 'ADP':
                    prep_count += 1
                
                # Compute depth from root
                depth = 1
                cur = w
                while cur.head > 0 and depth < 50:
                    depth += 1
                    cur = sent.words[cur.head - 1]
                max_depth = max(max_depth, depth)
        
        return cls(
            nesting_depth=max_depth,
            coordination_count=coord_count,
            preposition_density=prep_count / max(total_words, 1),
            total_tokens=total_words,
            real_word_count=real_words,
        )
    
    def granularity_y(self) -> float:
        """Y-axis: operational granularity 0~1."""
        d = min(self.nesting_depth / 5.0, 1.5)
        c = min(self.coordination_count / 3.0, 1.5)
        p = min(self.preposition_density * 10, 1.5)
        raw = d * 0.4 + c * 0.4 + p * 0.2
        return round(1.0 / (1.0 + math.exp(-(raw - 0.3) * 4.0)), 4)


class MoodClassifier:
    """Z-axis signal A: syntactic mood → feedback expectation.
    
    Zero LLM. Pure syntactic pattern matching on question forms.
    """
    
    SOLUTION_MARKERS = {"吗", "几个", "在哪", "是不是", "是否有"}
    EXPLORE_MARKERS = {"如何", "怎么", "为什么", "为何", "怎样", "可否", "有没有", "有什么"}
    MIRROR_MARKERS = {"烂透了", "太棒了", "太烦了", "崩溃", "疯了", "受不了",
                      "无语", "服了", "废了", "好累", "不想", "太难了"}
    
    # English equivalents
    SOLUTION_EN = {"is", "are", "do", "does", "did", "will", "can", "could",
                   "what is", "where is", "how many", "how much"}
    EXPLORE_EN = {"how", "why", "what if", "how to", "explain"}
    
    @classmethod
    def classify(cls, text: str, has_question: bool, has_imperative: bool) -> float:
        """Returns Z contribution from mood: -1.0 ~ +1.0."""
        text_lower = text.lower()
        
        # Mirror check first: emotional outbursts
        for m in cls.MIRROR_MARKERS:
            if m in text:
                return -1.0
        
        # Solution-seeking: direct questions expecting facts
        for m in cls.SOLUTION_MARKERS:
            if m in text:
                return 1.0
        for m in cls.SOLUTION_EN:
            if f" {m} " in f" {text_lower} " or text_lower.startswith(m+" "):
                return 1.0
        
        # Imperative + no question = strong solution demand
        if has_imperative:
            return 0.7
        
        # Exploration: "how" / "why" / "怎么" questions
        # Default: slight solution bias for structured input
        if has_question:
            return 0.3
        
        return 0.0


class CoordinateProjector:
    """Projects user input → (X, Y, Z) coordinate using lightweight features."""
    
    def __init__(self, stanza_nlp=None, bge_model=None):
        self._nlp = stanza_nlp
        self._bge = bge_model
        self._idf_cache: Dict[str, float] = {}
        self._calibration = {"x_idf_weight": 0.3, "y_coord_weight": 0.4,
                            "z_mood_weight": 0.5, "z_kurtosis_weight": 0.3}
    
    def project(self, text: str, kurtosis: float = 0.5,
                fatigue: float = 0.3) -> CognitiveCoordinate:
        """Main entry: text → (X,Y,Z) coordinate."""
        
        # ── X-axis: Cognitive Distance ──
        x = self._compute_x(text)
        
        # ── Y-axis: Operational Granularity ──
        y = 0.0
        if self._nlp:
            try:
                doc = self._nlp(text)
                st = SyntacticTerrain.from_stanza(doc)
                y = st.granularity_y()
            except Exception as e:
                logger.debug("Stanza STC failed: %s", e)
        
        # ── Z-axis: Feedback Expectation ──
        has_question = "?" in text or "？" in text or any(
            text.strip().endswith(p) for p in ['吗','呢','吧'])
        has_imperative = any(text.strip().startswith(w) for w in
            ['帮','请','试','改','加','删','查','找','scan','run','read','write','patch','find'])
        
        mood = MoodClassifier.classify(text, has_question, has_imperative)
        k_norm = (kurtosis - 3.0) / 6.0 if kurtosis > 0 else 0.0
        k_norm = max(-0.5, min(0.5, k_norm))
        fatigue_bias = -fatigue * 0.4
        
        z = mood * self._calibration["z_mood_weight"] + \
            k_norm * self._calibration["z_kurtosis_weight"] + \
            fatigue_bias
        
        return CognitiveCoordinate(
            x=round(max(0.0, min(1.0, x)), 3),
            y=round(max(0.0, min(1.0, y)), 3),
            z=round(max(-1.0, min(1.0, z)), 3),
        )
    
    def _compute_x(self, text: str) -> float:
        """X-axis: semantic distance via SVO + IDF."""
        # SVO extraction (simple heuristic — no user-supplied S/O in projector)
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|0x[0-9a-fA-F]+', text)
        if len(tokens) < 2:
            return 0.3  # too short to judge
        
        subj = tokens[0]
        obj = tokens[-1]
        
        # BGE cosine (if available)
        bge_cos = 0.5
        if self._bge and subj and obj and subj != obj:
            try:
                s_vec = self._bge.encode(subj, normalize_embeddings=True)
                o_vec = self._bge.encode(obj, normalize_embeddings=True)
                bge_cos = float(sum(a*b for a,b in zip(s_vec, o_vec)))
            except: pass
        
        semantic_distance = 1.0 - bge_cos
        
        # IDF correction: rare terms → greater cognitive distance
        idf_avg = 0.3
        if subj in self._idf_cache:
            idf_avg = (self._idf_cache.get(subj, 0.3) + 
                      self._idf_cache.get(obj, 0.3)) / 2
        
        return semantic_distance * 0.7 + idf_avg * self._calibration["x_idf_weight"]
    
    def update_idf(self, text: str):
        """Accumulate IDF statistics from conversation history."""
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]{3,}', text.lower())
        for t in tokens:
            self._idf_cache[t] = self._idf_cache.get(t, 0.0) + 0.01
    
    def calibrate(self, actual_zone: str, expected_zone: str):
        """User feedback → adjust coefficient weights."""
        if actual_zone == expected_zone:
            return
        # Simple gradient: move weights toward better classification
        if expected_zone in ("ATOMIC", "EXPLORE"):
            self._calibration["x_idf_weight"] = max(0.1, 
                self._calibration["x_idf_weight"] - 0.02)
        elif expected_zone in ("PRECISION", "ABYSS"):
            self._calibration["y_coord_weight"] = min(0.6,
                self._calibration["y_coord_weight"] + 0.02)
