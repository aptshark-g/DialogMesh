from dataclasses import dataclass, field
from enum import Enum

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