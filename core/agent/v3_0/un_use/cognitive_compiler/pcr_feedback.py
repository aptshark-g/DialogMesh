# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PcrFeedbackLoop:
    def __init__(self, window_size: int = 20, alpha: float = 0.3, default_threshold: float = 0.3):
        self.window_size = window_size
        self.alpha = alpha
        self.default_threshold = default_threshold
        self._noise_history: deque = deque(maxlen=window_size)
        self._outcome_history: deque = deque(maxlen=window_size)
        self._ema_threshold: float = default_threshold

    def record(self, noise_level: float, was_successful: bool) -> None:
        self._noise_history.append(noise_level)
        self._outcome_history.append(1.0 if was_successful else 0.0)
        if len(self._noise_history) >= 3:
            self._update_threshold()

    def get_threshold(self) -> float:
        return round(self._ema_threshold, 3)

    def _update_threshold(self) -> None:
        recent_noises = list(self._noise_history)[-5:]
        recent_outcomes = list(self._outcome_history)[-5:]
        if not recent_noises:
            return
        avg_noise = sum(recent_noises) / len(recent_noises)
        success_rate = sum(recent_outcomes) / len(recent_outcomes)
        target = avg_noise * (1.0 - success_rate * 0.5)
        self._ema_threshold = self.alpha * target + (1 - self.alpha) * self._ema_threshold
        self._ema_threshold = max(0.1, min(0.9, self._ema_threshold))

    def should_fast_path(self, noise_level: float) -> bool:
        return noise_level < self.get_threshold()

    def reset(self) -> None:
        self._noise_history.clear()
        self._outcome_history.clear()
        self._ema_threshold = self.default_threshold

__all__ = ["PcrFeedbackLoop"]
