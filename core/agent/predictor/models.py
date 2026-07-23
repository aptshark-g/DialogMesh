from dataclasses import dataclass, field

@dataclass
class Candidate:
    action_summary: str
    action_type: str = ""
    llm_probability: float = 0.0
    success_rate: float = 0.5
    cognitive_load: float = 0.0
    profile_match: float = 0.0
    expected_value: float = 0.0

    def compute_value(self):
        self.expected_value = (
            self.llm_probability * 0.4
            + self.success_rate * 0.3
            + (1 - self.cognitive_load) * 0.2
            + self.profile_match * 0.1
        )
        return self.expected_value

@dataclass
class ValueBreakdown:
    llm_prob: float = 0.0
    success_rate: float = 0.0
    cognitive_load: float = 0.0
    profile_match: float = 0.0
    expected_value: float = 0.0

@dataclass
class PredictionResult:
    candidates: list
    breakdowns: dict
    query_mode: str
    predicted_top1: str = ""
    ask_clarification: bool = False
    latency_ms: float = 0.0

    @property
    def top3(self):
        return sorted(self.candidates, key=lambda c: -c.expected_value)[:3]

@dataclass
class TrainingSignal:
    predicted: list
    actual_action: str
    reward: float = 0.0
    is_correction: bool = False

    def compute_reward(self):
        top3 = sorted(self.predicted, key=lambda c: -c.expected_value)[:3]
        top1 = top3[0] if top3 else None
        in_top3 = any(c.action_summary == self.actual_action for c in top3)
        is_top1 = top1 and top1.action_summary == self.actual_action
        if is_top1: self.reward = 0.10
        elif in_top3: self.reward = 0.05
        else: self.reward = -0.15
        return self.reward