import math

class TimeDecay:
    NO_DECAY = 30; MODERATE_TAU = 300; STRONG_TAU = 3600

    def compute_decay(self, delta_t):
        if delta_t <= self.NO_DECAY: return 1.0
        tau = self.MODERATE_TAU if delta_t <= 300 else self.STRONG_TAU
        return math.exp(-delta_t / tau)