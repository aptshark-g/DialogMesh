from dataclasses import dataclass, field
from enum import Enum, IntEnum

class MetaRole(IntEnum):
    SOURCE = 1
    SINK = 2
    DISSIPATE = 3
    STORE_P = 4
    STORE_K = 5
    TRANSFORM = 6
    JSUM = 7
    JSPLIT = 8


@dataclass
class CausalConstraints:
    """Structural constraints extracted from a behavior step.

    These six fields drive skeleton matching: domain hint, feedback loop,
    dissipation/storage/transformation involvement, and causal direction.
    """
    domain_hint: str = "general"
    has_feedback: bool = False
    involves_dissipation: bool = False
    involves_storage: bool = False
    causal_direction: str = "cause->effect"
    involves_transformation: bool = False


@dataclass
class SkeletonMatch:
    """Match between a behavior chain and a causal skeleton.

    ``roles`` are the meta-role chain matched, ``coverage`` is the fraction of
    required roles covered, ``score`` is the overall match quality, and
    ``is_multi`` marks multi-skeleton ties. ``to_prior()`` converts the match
    into a capped structural prior (A22: prior ≤ 0.7, never 1.0).
    """
    roles: list = field(default_factory=list)
    coverage: float = 0.0
    score: float = 0.0
    is_multi: bool = False

    def to_prior(self) -> float:
        if self.score > 0.8:
            return 0.7
        if self.score > 0.5:
            return 0.3
        return 0.0


class TrackType(str, Enum):
    TRACK_0 = "algo"
    TRACK_1 = "llm"
    TRACK_P = "pred"
    CAUSAL = "causal"
    STRATEGIC = "strategic"

@dataclass
class TrackResult:
    track: TrackType
    output: dict
    confidence: float
    latency_ms: float = 0.0
    priority_level: int = 0
    repression_count: int = 0
    is_timeout: bool = False

    def is_confident(self):
        return self.confidence > 0.5 and not self.is_timeout

@dataclass
class StageOutput:
    stage: int
    tracks: list
    merged: dict
    is_final: bool = False
    latency_ms: float = 0.0

@dataclass
class FusionResult:
    final_output: dict
    confidence: float
    dominant_track: TrackType
    conflicts: list
    stages: list
    ask_clarification: bool = False
    latency_ms: float = 0.0
    profile_lite: bool = False
