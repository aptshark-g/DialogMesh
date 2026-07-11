from dataclasses import dataclass, field
from enum import Enum

class MetaRole(str, Enum):
    SOURCE = "source"; SINK = "sink"
    STORE_P = "store:potential"; STORE_K = "store:kinetic"
    DISSIPATE = "dissipate"; TRANSFORM = "transform"
    JSUM = "junction_sum"; JSPLIT = "junction_split"

@dataclass
class CausalConstraints:
    domain_hint: str = "general"
    has_feedback: bool = False
    involves_dissipation: bool = False
    involves_storage: bool = False
    causal_direction: str = "cause->effect"
    involves_transformation: bool = False

@dataclass
class SkeletonMatch:
    roles: list = field(default_factory=list)
    coverage: float = 0.0
    score: float = 0.0
    is_multi: bool = False
    def to_prior(self):
        if self.score > 0.8: return 0.7
        if self.score > 0.5: return 0.3
        return 0.0