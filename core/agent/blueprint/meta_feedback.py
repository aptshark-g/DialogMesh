# -*- coding: utf-8 -*-
"""MetaFeedback — asynchronous learning writeback (§14.4-14.5).

Meta LLM 消费 EventLog → 评分 → 更新 SkillRegistry 权重 → 建议模板进化。
当人不选择时, Profile + Behavior + Meta 代替人做驾驭决策 (§十三).

Trigger thresholds:
  - DEGRADATION: 连续3次低分 → strategy降级 (LLM_DRIVEN→HYBRID→TEMPLATE)
  - PROMOTION: 连续5次高分 → 放松约束 (减少checkpoint频率)
  - SUGGESTION: 新意图出现3次+ → 建议新增Blueprint模板
"""

from __future__ import annotations

import logging
import time
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from core.agent.blueprint.models import ExecutionAudit
from core.agent.blueprint.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


@dataclass
class MetaState:
    """Per-strategy running statistics."""
    strategy: str
    scores: List[float] = field(default_factory=list)
    consecutive_low: int = 0     # 连续低分次数
    consecutive_high: int = 0    # 连续高分次数
    degradation_level: int = 0   # 0=正常, 1=降1级, 2=降2级

    LOW_THRESHOLD = 0.4
    HIGH_THRESHOLD = 0.75
    DEGRADE_TRIGGER = 3
    PROMOTE_TRIGGER = 5

    def record(self, score: float):
        self.scores.append(score)
        if score < self.LOW_THRESHOLD:
            self.consecutive_low += 1
            self.consecutive_high = 0
        elif score > self.HIGH_THRESHOLD:
            self.consecutive_high += 1
            self.consecutive_low = 0
        else:
            self.consecutive_low = max(0, self.consecutive_low - 1)
            self.consecutive_high = max(0, self.consecutive_high - 1)

    @property
    def should_degrade(self) -> bool:
        return self.consecutive_low >= self.DEGRADE_TRIGGER

    @property
    def should_promote(self) -> bool:
        return self.consecutive_high >= self.PROMOTE_TRIGGER

    @property
    def avg_score(self) -> float:
        if not self.scores:
            return 0.5
        return sum(self.scores[-20:]) / min(len(self.scores), 20)


class MetaFeedback:
    """Async learning loop — consumes ExecutionAudit, writes back to SkillRegistry.

    Aligned to §十四 闭环缺口补齐:
      - update_strategy_weights() → §14.4
      - suggest_blueprint() → §14.5
      - trigger_degradation() → §14.4

    Usage:
      fb = MetaFeedback(registry)
      fb.consume(audit)           # 每条执行记录
      fb.check_degradations()     # 异步Tick检查
    """

    def __init__(self, registry: SkillRegistry = None):
        self.registry = registry or SkillRegistry()
        self._strategy_states: Dict[str, MetaState] = {}
        self._intent_sightings: Dict[str, int] = defaultdict(int)  # intent → count
        self._total_audits: int = 0

    def consume(self, audit: ExecutionAudit):
        """Consume one execution audit record."""
        self._total_audits += 1

        # Track per-strategy stats
        if audit.strategy not in self._strategy_states:
            self._strategy_states[audit.strategy] = MetaState(strategy=audit.strategy)
        state = self._strategy_states[audit.strategy]
        state.record(audit.dag_quality_score)

        logger.info("MetaFeedback: consumed audit #%d (strategy=%s, score=%.2f, anomalies=%d)",
                     self._total_audits, audit.strategy, audit.dag_quality_score,
                     len(audit.anomalies))

    def update_strategy_weights(self, intent: str, strategy: str, score: float):
        """Update SkillRegistry weights based on execution quality.

        Called per-request after DAG execution completes.
        """
        self.registry.update_weight(intent, strategy, score)

        # Track intents for blueprint suggestion
        self._intent_sightings[intent] += 1

    def check_degradations(self) -> List[Dict]:
        """Check all strategies for degradation/promotion triggers.

        Returns list of actions taken: [{action, strategy, detail}].
        """
        actions = []
        for strategy, state in self._strategy_states.items():
            if state.should_degrade and state.degradation_level < 2:
                state.degradation_level += 1
                state.consecutive_low = 0
                next_strategy = self._next_degraded_strategy(strategy)
                actions.append({
                    "action": "degrade",
                    "strategy": strategy,
                    "next": next_strategy,
                    "avg_score": state.avg_score,
                    "detail": f"连续{state.DEGRADE_TRIGGER}次低分, 降级 {strategy}→{next_strategy}",
                })
                logger.warning("MetaFeedback: degrading %s→%s (avg=%.2f)", strategy, next_strategy, state.avg_score)

            if state.should_promote and state.degradation_level > 0:
                state.degradation_level -= 1
                state.consecutive_high = 0
                prev_strategy = self._prev_promoted_strategy(strategy)
                actions.append({
                    "action": "promote",
                    "strategy": strategy,
                    "next": prev_strategy,
                    "avg_score": state.avg_score,
                    "detail": f"连续{state.PROMOTE_TRIGGER}次高分, 升级 {strategy}→{prev_strategy}",
                })
                logger.info("MetaFeedback: promoting %s→%s (avg=%.2f)", strategy, prev_strategy, state.avg_score)

        return actions

    def suggest_blueprints(self) -> List[Dict]:
        """Check for intent patterns that suggest new Blueprint templates.

        Returns list of suggestions: [{intent, count, suggest}].
        """
        suggestions = []
        SUGGEST_THRESHOLD = 3
        for intent, count in self._intent_sightings.items():
            if count >= SUGGEST_THRESHOLD and intent not in self.registry._strategy_weights:
                suggestions.append({
                    "intent": intent,
                    "count": count,
                    "suggest": f"新意图 '{intent}' 出现{count}次, 建议新建Blueprint模板",
                })
        return suggestions

    @staticmethod
    def _next_degraded_strategy(strategy: str) -> str:
        """LLM_DRIVEN → HYBRID → TEMPLATE → TEMPLATE"""
        degradation_order = {"LLM_DRIVEN": "HYBRID", "HYBRID": "TEMPLATE"}
        return degradation_order.get(strategy, "TEMPLATE")

    @staticmethod
    def _prev_promoted_strategy(strategy: str) -> str:
        """TEMPLATE → HYBRID → LLM_DRIVEN"""
        promotion_order = {"TEMPLATE": "HYBRID", "HYBRID": "LLM_DRIVEN"}
        return promotion_order.get(strategy, strategy)

    @property
    def summary(self) -> dict:
        """Human-readable summary of all tracked state."""
        return {
            "total_audits": self._total_audits,
            "strategies": {
                s: {
                    "avg_score": st.avg_score,
                    "consecutive_low": st.consecutive_low,
                    "consecutive_high": st.consecutive_high,
                    "degradation": st.degradation_level,
                }
                for s, st in self._strategy_states.items()
            },
            "intent_sightings": dict(self._intent_sightings),
        }
