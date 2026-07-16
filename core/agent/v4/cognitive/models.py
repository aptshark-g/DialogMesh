"""Cognitive Profile v2 — data models.

Design refs:
  docs/v3.0/design_cognitive_profile_v2.md §2 (Dual-Track Architecture)
  docs/v3.0/ENGINEERING_COGNITIVE_PROFILE_V2.md §2 (Data Models)
  docs/DESIGN_SPECIFICATION.md §5.4 (Capacitor model for memory)
  docs/blog/chapter1_design_thinking.md §七 (Forgetting = capacitor discharge)

Memory model: capacitor-based activation counting (not time decay).
  "不计衰减，只计使用。" — activation_count naturally favors frequent access.
"""
from __future__ import annotations
import time
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

Timestamp = float
TagValue = Any

# ═══════════════════ UserTag (Track B) ═══════════════════

@dataclass
class UserTag:
    name: str
    value: TagValue
    confidence: float = 0.0
    source: str = "unknown"
    last_updated: float = field(default_factory=time.time)
    verification_count: int = 0
    is_sensitive: bool = False

    def update_confidence(self, new_conf: float, new_source: str) -> None:
        if new_source in ("L1", "user_declared"):
            self.confidence = min(0.95, 0.8 + new_conf * 0.2)
        elif new_source == "L4":
            self.confidence = min(0.95, 0.8 + new_conf * 0.15)
        elif new_source == "L2":
            self.verification_count += 1
            if self.verification_count >= 3:
                self.confidence = min(0.9, self.confidence + 0.15)
        elif new_source == "L3":
            self.confidence = min(0.7, self.confidence + 0.1)
        self.last_updated = time.time()
        self.source = new_source

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserTag":
        return cls(**{k: d.get(k) for k in [
            "name","value","confidence","source","last_updated",
            "verification_count","is_sensitive"]})


# ═══════════════════ Memory (Capacitor Model) ═══════════════════

@dataclass
class MemoryPoint:
    """High-impact event. Weight = importance * log(1+activation_count)."""
    point_id: str
    timestamp: float
    content: str
    activation_count: int = 1
    importance: float = 0.5
    emotion_polarity: float = 0.0
    topic_tags: List[str] = field(default_factory=list)

    def access(self) -> None:
        self.activation_count += 1

    @property
    def weight(self) -> float:
        return min(1.0, self.importance * math.log(1 + self.activation_count) * 0.3)

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryPoint":
        return cls(**{k: d.get(k) for k in [
            "point_id","timestamp","content","activation_count",
            "importance","emotion_polarity","topic_tags"]})


@dataclass
class MemoryChunk:
    """Aggregated turns. Stage = f(activation_count), not t."""
    chunk_id: str
    created_at: float
    activation_count: int = 0
    importance: float = 0.5
    content: str = ""
    topic_tags: List[str] = field(default_factory=list)

    WARM_THRESHOLD = 3
    COLD_THRESHOLD = 1

    def access(self) -> None:
        self.activation_count += 1

    @property
    def weight(self) -> float:
        import math
        eff = self.activation_count * (2.0 if self.importance > 0.8 else 1.0)
        return min(1.0, math.log(1 + eff) * 0.25)

    @property
    def stage(self) -> str:
        if self.activation_count >= self.WARM_THRESHOLD:
            return "hot"
        if self.activation_count >= self.COLD_THRESHOLD:
            return "warm"
        return "cold"

    def should_cleanup(self) -> bool:
        return self.stage == "cold" and self.importance < 0.3

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryChunk":
        return cls(**{k: d.get(k) for k in [
            "chunk_id","created_at","activation_count",
            "importance","content","topic_tags"]})


# ═══════════════════ CognitiveDynamics (Track A) ═══════════════════

@dataclass
class CognitiveDynamics:
    cognitive_inertia: float = 0.5
    behavior_inertia: float = 0.5
    trust_score: float = 0.5
    emotional_entropy: float = 0.5
    attention_anchor: float = 0.5
    expectation_deviation: float = 0.0
    memory_point_count: int = 0
    self_value_score: float = 0.5
    cognitive_resource: float = 0.5
    observation_count: int = 0
    stability: float = 1.0
    frozen_dimensions: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CognitiveDynamics":
        return cls(**{k: d.get(k, 0.5) for k in [
            "cognitive_inertia","behavior_inertia","trust_score",
            "emotional_entropy","attention_anchor","expectation_deviation",
            "memory_point_count","self_value_score","cognitive_resource",
            "observation_count","stability","frozen_dimensions","last_updated"]})

    @property
    def converged(self) -> bool:
        return self.observation_count > 50 and self.stability < 0.05


# ═══════════════════ CognitiveProfileV2 ═══════════════════

@dataclass
class CognitiveProfileV2:
    user_id: str = "default"
    session_id: str = ""
    track_a: CognitiveDynamics = field(default_factory=CognitiveDynamics)
    track_b: Dict[str, UserTag] = field(default_factory=dict)
    memory_chunks: List[MemoryChunk] = field(default_factory=list)
    memory_points: List[MemoryPoint] = field(default_factory=list)
    total_turns: int = 0
    total_sessions: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id, "session_id": self.session_id,
            "track_a": self.track_a.to_dict(),
            "track_b": {k: v.to_dict() for k, v in self.track_b.items()},
            "memory_chunks": [c.to_dict() for c in self.memory_chunks],
            "memory_points": [p.to_dict() for p in self.memory_points],
            "total_turns": self.total_turns, "total_sessions": self.total_sessions,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CognitiveProfileV2":
        return cls(
            user_id=d.get("user_id","default"), session_id=d.get("session_id",""),
            track_a=CognitiveDynamics.from_dict(d.get("track_a",{})),
            track_b={k: UserTag.from_dict(v) for k,v in d.get("track_b",{}).items()},
            memory_chunks=[MemoryChunk.from_dict(c) for c in d.get("memory_chunks",[])],
            memory_points=[MemoryPoint.from_dict(p) for p in d.get("memory_points",[])],
            total_turns=d.get("total_turns",0), total_sessions=d.get("total_sessions",1),
            created_at=d.get("created_at",time.time()), updated_at=d.get("updated_at",time.time()),
        )
