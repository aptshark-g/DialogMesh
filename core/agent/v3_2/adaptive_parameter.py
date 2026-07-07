"""Adaptive Parameter System - literature anchor + bounded interval + online training"""
import time, math
from dataclasses import dataclass, field
from typing import Callable, Optional

@dataclass
class ParamConfig:
    name: str
    anchor: float       # literature anchor (initial value)
    min_val: float      # lower bound
    max_val: float      # upper bound
    lr: float = 0.02    # learning rate per update
    signal_fn: Optional[Callable] = None  # custom signal function

class AdaptiveParameter:
    def __init__(self, config: ParamConfig):
        self.config = config
        self.value = config.anchor
        self._history: list = []

    def update(self, signal: float):
        self.value += signal * self.config.lr
        self.value = max(self.config.min_val, min(self.config.max_val, self.value))
        self._history.append({"t": time.time(), "v": self.value, "s": signal})

    @property
    def current(self) -> float:
        return self.value

    def reset(self):
        self.value = self.config.anchor

    def stats(self) -> dict:
        return {"name": self.config.name, "value": round(self.value, 4),
                "range": [self.config.min_val, self.config.max_val],
                "anchor": self.config.anchor, "lr": self.config.lr,
                "updates": len(self._history)}

PREDEFINED = {
    # Compiler thresholds (anchor from Stanza UAS ~88%)
    "compiler_confidence": ParamConfig("compiler_confidence", 0.75, 0.65, 0.85, lr=0.02),
    "stability_min": ParamConfig("stability_min", 0.60, 0.50, 0.70, lr=0.01),
    "llm_retries": ParamConfig("llm_retries", 1, 0, 3, lr=0.1),
    # Graph weights (anchor from ACT-R cognitive architecture)
    "graph_alpha": ParamConfig("graph_alpha", 0.25, 0.10, 0.40, lr=0.01),
    "graph_beta": ParamConfig("graph_beta", 0.30, 0.15, 0.50, lr=0.01),
    "graph_gamma": ParamConfig("graph_gamma", 0.05, 0.02, 0.15, lr=0.005),
    "graph_delta": ParamConfig("graph_delta", 0.05, 0.03, 0.25, lr=0.005),
    # Predictor weights (anchor from ESMM/MMOE equal-initial approach)
    "pred_llm": ParamConfig("pred_llm", 0.35, 0.25, 0.55, lr=0.01),
    "pred_history": ParamConfig("pred_history", 0.30, 0.15, 0.45, lr=0.01),
    "pred_cognitive": ParamConfig("pred_cognitive", 0.20, 0.05, 0.30, lr=0.005),
    "pred_profile": ParamConfig("pred_profile", 0.15, 0.05, 0.25, lr=0.005),
    # Rewarder values (anchor from behavior psychology 1:2-3 ratio)
    "reward_hit": ParamConfig("reward_hit", 0.10, 0.05, 0.20, lr=0.005),
    "reward_fail": ParamConfig("reward_fail", -0.15, -0.25, -0.08, lr=0.005),
    "reward_correction": ParamConfig("reward_correction", -0.20, -0.35, -0.12, lr=0.005),
    # FoA (anchor from ACT-R literature: decay 0.5, bounds 0.2-0.5)
    "foa_decay": ParamConfig("foa_decay", 0.30, 0.20, 0.50, lr=0.01),
    "foa_threshold": ParamConfig("foa_threshold", 0.30, 0.15, 0.50, lr=0.01),
    # Semantic similarity (anchor from BGE-small MTEB ~0.55-0.65)
    "sim_threshold": ParamConfig("sim_threshold", 0.75, 0.55, 0.85, lr=0.01),
}

class ParameterCalibrator:
    def __init__(self):
        self._params: dict[str, AdaptiveParameter] = {}

    def register(self, config: ParamConfig):
        self._params[config.name] = AdaptiveParameter(config)

    def register_preset(self):
        for name, cfg in PREDEFINED.items():
            self._params[name] = AdaptiveParameter(cfg)

    def get(self, name: str) -> Optional[AdaptiveParameter]:
        return self._params.get(name)

    def value(self, name: str) -> float:
        p = self._params.get(name)
        return p.current if p else PREDEFINED.get(name, ParamConfig(name, 0.5, 0, 1)).anchor

    def update(self, name: str, signal: float):
        p = self._params.get(name)
        if p:
            p.update(signal)

    def multi_update(self, signals: dict[str, float]):
        for name, signal in signals.items():
            self.update(name, signal)

    def report(self) -> dict:
        return {k: v.stats() for k, v in self._params.items()}

    def suggest(self, prediction_hit: bool, correction: bool):
        if prediction_hit:
            self.update("pred_llm", 0.01)
            self.update("pred_history", -0.005)
        if correction:
            self.update("pred_llm", -0.02)
            self.update("pred_history", 0.01)
            self.update("reward_correction", -0.002)
        if prediction_hit and not correction:
            self.update("reward_hit", 0.001)
            self.update("reward_fail", -0.001)
        if correction and not prediction_hit:
            self.update("reward_fail", 0.002)

CALIBRATOR = ParameterCalibrator()
CALIBRATOR.register_preset()
