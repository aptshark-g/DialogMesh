from dataclasses import dataclass, field
import math

@dataclass
class RewardSignal:
    edge_key: str
    raw_reward: float
    decay_factor: float = 1.0
    noise_level: float = 0.5
    effective_reward: float = 0.0
    timestamp: float = 0.0
    is_exploration: bool = False
    correction_count: int = 0

    def compute_effective(self):
        if self.is_exploration:
            self.effective_reward = 0.0
            return
        self.effective_reward = self.raw_reward * self.decay_factor * (1 - self.noise_level)

@dataclass
class ABLReflection:
    edge_key: str
    error_type: str
    correct_path: str
    why_wrong: str
    suggested_correction: str
    turn_count: int = 0
    timestamp: float = 0.0