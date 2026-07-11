"""EMA 权重更新器"""
from .models import BehaviorEdge


class WeightUpdater:
    ALPHA = 0.25
    BETA = 0.30
    GAMMA = 0.05
    DELTA = 0.05

    def __init__(self, alpha=None, beta=None, gamma=None, delta=None):
        self.alpha = alpha or self.ALPHA
        self.beta = beta or self.BETA
        self.gamma = gamma or self.GAMMA
        self.delta = delta or self.DELTA
        self.ema_remainder = 1.0 - self.alpha - self.beta - self.gamma - self.delta

    def update(self, edge: BehaviorEdge, llm_prob: float = None) -> float:
        if edge.correction_mode:
            return self._fast_correction_weight(edge)
        llm = llm_prob if llm_prob is not None else edge.llm_causal_prob
        new_w = (self.alpha * llm
                 + self.beta * edge.freq_ratio
                 + self.gamma * edge.profile_boost
                 + self.delta * edge.structural_prior
                 + self.ema_remainder * edge.weight)
        return max(0.0, min(1.0, new_w))

    def update_freq_ratio(self, edge: BehaviorEdge) -> float:
        denom = edge.sample_count + edge.correction_count
        edge.freq_ratio = edge.sample_count / denom if denom > 0 else 0.0
        return edge.freq_ratio

    def update_profile_boost(self, edge: BehaviorEdge, match_score: float) -> float:
        edge.profile_boost = min(0.3, match_score)
        return edge.profile_boost

    def update_structural_prior(self, edge: BehaviorEdge, prior: float) -> float:
        edge.structural_prior = min(0.7, prior)
        return edge.structural_prior

    def _fast_correction_weight(self, edge: BehaviorEdge) -> float:
        return max(0.0, 0.3 * edge.weight)

    def reconfigure(self, alpha, beta, gamma, delta):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta
        self.ema_remainder = 1.0 - alpha - beta - gamma - delta
