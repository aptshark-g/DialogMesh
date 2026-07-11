from dataclasses import dataclass, field


@dataclass
class CausalEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class CausalSkeleton:
    nodes: list
    edges: list
    observed: set = field(default_factory=set)


@dataclass
class BackdoorTestResult:
    hypothesis: str = ""
    verified: bool = False
    paths_checked: int = 0
    confounders_found: list = field(default_factory=list)
    p_y_given_do_x: float = 0.0

    def to_negative_level(self):
        if self.verified and self.p_y_given_do_x >= 0.95:
            return "HARD_BLOCK"
        return "WARN"
