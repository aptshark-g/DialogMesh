import math


def _decay_params():
    """Read time-decay parameters from ParameterRegistry (A18)."""
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
    except Exception:
        reg = None
    if reg is None:
        return {"no_decay": 30, "moderate_tau": 300, "strong_tau": 3600}
    return {
        "no_decay": int(reg.get("behavior.time_decay_no_decay", 30)),
        "moderate_tau": int(reg.get("behavior.time_decay_moderate_tau", 300)),
        "strong_tau": int(reg.get("behavior.time_decay_strong_tau", 3600)),
    }


class TimeDecay:
    NO_DECAY = 30
    MODERATE_TAU = 300
    STRONG_TAU = 3600

    def __init__(self, no_decay=None, moderate_tau=None, strong_tau=None):
        p = _decay_params()
        self.NO_DECAY = no_decay if no_decay is not None else p["no_decay"]
        self.MODERATE_TAU = moderate_tau if moderate_tau is not None else p["moderate_tau"]
        self.STRONG_TAU = strong_tau if strong_tau is not None else p["strong_tau"]

    def compute_decay(self, delta_t):
        if delta_t <= self.NO_DECAY: return 1.0
        tau = self.MODERATE_TAU if delta_t <= self.MODERATE_TAU else self.STRONG_TAU
        return math.exp(-delta_t / tau)
