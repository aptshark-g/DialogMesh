from dataclasses import dataclass, field


# BC05 §5.1 / A18: predictor weights live in ParameterRegistry (behavior.*).
# The literals below are only cold-start fallbacks when the registry is
# unavailable; runtime tuning goes through the registry.
_PREDICT_WEIGHT_KEYS = {
    "llm": "behavior.predict_weight_llm",
    "success": "behavior.predict_weight_success",
    "load": "behavior.predict_weight_load",
    "profile": "behavior.predict_weight_profile",
}
_PREDICT_WEIGHT_DEFAULTS = {"llm": 0.4, "success": 0.3, "load": 0.2, "profile": 0.1}


def get_predict_weights() -> dict:
    """Read predictor weights from ParameterRegistry (A18)."""
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
    except Exception:
        reg = None
    out = {}
    for name, key in _PREDICT_WEIGHT_KEYS.items():
        val = reg.get(key) if reg is not None else None
        out[name] = float(val) if val is not None else _PREDICT_WEIGHT_DEFAULTS[name]
    return out


@dataclass
class Candidate:
    action_summary: str
    action_type: str = ""
    llm_probability: float = 0.0
    success_rate: float = 0.5
    cognitive_load: float = 0.0
    profile_match: float = 0.0
    expected_value: float = 0.0

    def compute_value(self, weights: dict = None):
        w = weights or get_predict_weights()
        self.expected_value = (
            self.llm_probability * w["llm"]
            + self.success_rate * w["success"]
            + (1 - self.cognitive_load) * w["load"]
            + self.profile_match * w["profile"]
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
        # BC05 §6.1 accuracy kernel (shared with RewardRuleTable).
        from core.agent.rewarder.reward_rules import evaluate_accuracy
        self.reward = evaluate_accuracy(
            self.predicted, self.actual_action, is_correction=self.is_correction,
        )
        return self.reward
