"""BehaviorGraph 数据模型"""
import time
from dataclasses import dataclass, field, asdict


@dataclass
class BehaviorStep:
    step_id: str
    action_summary: str
    action_type: str
    entities: dict = field(default_factory=dict)
    result: str = ""
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def edge_key(self) -> str:
        return f"{self.action_type}:{self.action_summary}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BehaviorEdge:
    edge_id: str
    from_step_id: str
    to_step_id: str
    weight: float = 0.5
    llm_causal_prob: float = 0.0
    freq_ratio: float = 0.0
    profile_boost: float = 0.0
    structural_prior: float = 0.0
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    correction_count: int = 0
    importance: float = 0.5
    activation_count: int = 0
    last_activated: float = 0.0
    last_updated: float = 0.0
    is_stable: bool = True
    is_deprecated: bool = False
    correction_mode: bool = False

    @property
    def edge_key(self) -> str:
        return f"{self.from_step_id}->{self.to_step_id}"

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def instability_ratio(self) -> float:
        return self.correction_count / max(self.sample_count, 1)

    def record_observation(self, success: bool, correction: bool = False):
        self.sample_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        if correction:
            self.correction_count += 1
        self.last_updated = time.time()


@dataclass
class ColdStartSeed:
    from_summary: str
    to_summary: str
    from_type: str
    to_type: str
    initial_weight: float
    sample_count: int = 0
    is_deprecated: bool = False
    created_at: float = 0.0

    @property
    def edge_key(self) -> str:
        return f"seed:{self.from_summary}->{self.to_summary}"

    def is_usable(self) -> bool:
        return not self.is_deprecated and self.sample_count < 10


@dataclass
class GraphStatistics:
    node_count: int = 0
    edge_count: int = 0
    seed_count: int = 0
    total_samples: int = 0
    avg_weight: float = 0.0
    avg_importance: float = 0.0
    avg_activation: float = 0.0
    unstable_edge_count: int = 0
    deprecated_seed_count: int = 0
    last_prune_time: float = 0.0
    last_discovery_time: float = 0.0
