"""稳定性评分器"""
import statistics
from .models import SlotValue


class StabilityScorer:
    """stability = mean(ci) * (1 - variance(ci))"""
    MIN_STABILITY = 0.6

    def score(self, slots: dict[str, SlotValue]) -> float:
        if not slots:
            return 0.0
        # Only non-empty, non-zero-confidence slots contribute to stability
        active = [s for s in slots.values() if s.value.strip() and s.confidence > 0.1]
        if not active:
            return 0.0
        confidences = [s.confidence for s in active]
        mean_c = statistics.mean(confidences)
        var_c = statistics.variance(confidences) if len(confidences) > 1 else 0
        stability = mean_c * (1.0 - var_c)
        return max(0.0, min(1.0, stability))

    def is_undefined(self, stability: float) -> bool:
        return stability < self.MIN_STABILITY
