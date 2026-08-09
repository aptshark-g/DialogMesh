"""BehaviorScheduler — BC05 §3 four-layer priority decision tree.

The scheduler decides HOW to predict (stats / LLM / ask), the BehaviorPredictor
remains the executor (its four-mode fallback runs whatever the scheduler picks).
All thresholds live in ParameterRegistry (A18) — nothing is hard-coded here.

    L1 cost floor:   token budget exhausted       → pure stats (0 tokens)
    L2 risk hijack:  delete/pay/permission action → unconditional LLM
    L3 cold start:   total_turns <= threshold     → LLM + epsilon exploration
    L4 CI width:     converged (<t)               → Bayesian fast path
                     chaotic  (t..T)              → LLM golden zone
                     diverged (>T)                → ask the user
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.agent.compiler.parameter_registry import get_registry


class ScheduleMode(str, Enum):
    STATS = "stats"          # Bayesian fast path, 0 tokens
    LLM = "llm"              # unconditional (risk) or golden-zone LLM
    EXPLORE = "explore"      # cold-start LLM + epsilon-greedy
    ASK = "ask"              # diverged → ask the user, no prediction


@dataclass
class SchedulerDecision:
    mode: ScheduleMode
    reason: str
    epsilon: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "reason": self.reason,
            "epsilon": self.epsilon,
        }


# Risk-hijack action keywords (L2). Kept small and explicit; extendable.
RISK_ACTIONS = {
    "delete", "删除", "rm ", "drop",
    "pay", "支付", "转账",
    "grant", "permission", "权限", "授权", "sudo", "chmod",
}


class BehaviorScheduler:
    def __init__(self):
        self._reg = get_registry()

    def epsilon_for_turns(self, turns: int, anchors: int = 0) -> float:
        """BC05 §4 dynamic epsilon decay."""
        stable = float(self._reg.get("behavior.scheduler_epsilon_stable", 0.05))
        if anchors > 50:
            return 0.02
        if turns <= 5:
            return float(self._reg.get("behavior.scheduler_epsilon_cold", 0.6))
        if turns <= 20:
            return round(0.6 * math.exp(-0.1 * (turns - 5)), 4)
        return stable

    def decide(
        self,
        *,
        token_budget_remaining: float = 2000.0,
        risk_action: bool = False,
        total_turns: int = 100,
        ci_width: float = 0.0,
        anchors: int = 0,
    ) -> SchedulerDecision:
        """Return the scheduling decision for this prediction round."""
        # L1 — cost floor
        if token_budget_remaining <= 0:
            return SchedulerDecision(
                ScheduleMode.STATS, "L1 cost floor: token budget exhausted",
            )
        # L2 — risk hijack
        if risk_action:
            return SchedulerDecision(
                ScheduleMode.LLM, "L2 risk hijack: unconditional LLM",
            )
        # L3 — cold start exploration
        cold_turns = int(self._reg.get("behavior.scheduler_cold_turns", 3))
        if total_turns <= cold_turns:
            eps = self.epsilon_for_turns(total_turns, anchors)
            return SchedulerDecision(
                ScheduleMode.EXPLORE,
                f"L3 cold start (turns={total_turns}): LLM + epsilon={eps}",
                epsilon=eps,
            )
        # L4 — confidence-interval width
        converged = float(self._reg.get("behavior.scheduler_ci_converged", 0.15))
        diverged = float(self._reg.get("behavior.scheduler_ci_diverged", 0.4))
        if ci_width < converged:
            return SchedulerDecision(
                ScheduleMode.STATS,
                f"L4 converged (ci={ci_width:.3f}): Bayesian fast path",
            )
        if ci_width > diverged:
            return SchedulerDecision(
                ScheduleMode.ASK,
                f"L4 diverged (ci={ci_width:.3f}): ask the user",
            )
        eps = self.epsilon_for_turns(total_turns, anchors)
        return SchedulerDecision(
            ScheduleMode.LLM,
            f"L4 chaotic (ci={ci_width:.3f}): LLM golden zone",
            epsilon=eps,
        )


def is_risk_action(context: str) -> bool:
    """L2 check: does the recent behavior context involve a risk action?"""
    if not context:
        return False
    low = context.lower()
    return any(k in low for k in RISK_ACTIONS)


def ci_width_proxy(graph, n: int = 10) -> float:
    """Wald-interval CI width of the statistical prediction (L4 input).

    Narrow CI (converged) → stats path; wide CI (diverged) → ask user.
    No edges yet → width 1.0 (diverged, ask — matches the design's cold-start
    posture: when there is no statistical prior, do not guess blindly).
    """
    edges = list(getattr(graph, "edges", {}).values())
    if not edges:
        return 1.0
    recent = edges[-n:]
    samples = sum(max(getattr(e, "sample_count", 0), 0) for e in recent)
    if samples <= 0:
        return 1.0
    p = sum(getattr(e, "success_rate", 0.5) for e in recent) / len(recent)
    p = max(0.0, min(1.0, p))
    se = math.sqrt(p * (1 - p) / samples)
    return min(1.0, 1.96 * se * 2)
