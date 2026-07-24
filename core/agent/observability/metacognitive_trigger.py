"""Metacognitive Trigger Engine — condition-based cognitive pipeline activation.

Monitors system signals and triggers pipeline components when thresholds crossed.
Zero hardcoded rules — all triggers from config.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
import time, json, logging

logger = logging.getLogger(__name__)


@dataclass
class Trigger:
    """One trigger rule: condition → action."""
    name: str
    metric: str              # key in signal dict
    comparator: str          # ">" | "<" | ">=" | "<="
    threshold: float
    action: str              # pipeline component to activate
    cooldown_s: float = 300.0
    severity: str = "info"
    message_template: str = "{name}: {metric}={value} {comparator} {threshold}"
    
    # Callback: triggered(state, trigger, value) → None
    callback: Optional[Callable] = None


@dataclass
class TriggerEvent:
    """Record of a triggered event."""
    trigger: str
    action: str
    severity: str
    message: str
    value: float
    threshold: float
    timestamp: float


class MetacognitiveTriggerEngine:
    """Signal monitor → trigger pipeline components.

    Usage:
        engine = MetacognitiveTriggerEngine(config_path="config/triggers.json")
        engine.subscribe("belief_entropy_high", compressor_ingest)
        
        signals = {"llm_error_rate": 0.15, "belief_entropy": 0.6, "cold_blocks": 25}
        events = engine.check(signals)
        # → [TriggerEvent(action="compressor_ingest", ...), 
        #     TriggerEvent(action="llm_degraded", ...)]
    """

    DEFAULT_TRIGGERS = [
        Trigger("error_rate_high", "llm_error_rate", ">", 0.10,
                "llm_degraded", severity="critical",
                message_template="LLM error rate {value:.1%} exceeds {threshold:.1%}"),
        Trigger("llm_failures", "consecutive_llm_failures", ">=", 3,
                "llm_degraded", severity="warning",
                message_template="LLM consecutive failures: {value}"),
        Trigger("latency_high", "avg_llm_latency_ms", ">", 10000,
                "llm_degraded", severity="warning",
                message_template="LLM latency {value:.0f}ms > {threshold:.0f}ms"),
        Trigger("belief_entropy_high", "belief_entropy", ">", 0.5,
                "compressor_ingest", severity="info",
                message_template="Belief entropy {value:.2f} — trigger compression"),
        Trigger("intent_drift", "intent_drift_jsd", ">", 0.3,
                "l4_explain_drift", severity="info",
                message_template="Intent drift {value:.2f} — trigger L4 explanation"),
        Trigger("cold_blocks_high", "cold_blocks", ">", 20,
                "compress_cold_blocks", severity="info",
                message_template="{value} cold blocks — trigger summary upgrade"),
        Trigger("correction_rate_high", "correction_rate", ">", 0.4,
                "behavior_llm_review", severity="info",
                message_template="Correction rate {value:.1%} — trigger behavior review"),
    ]

    def __init__(self, triggers: List[Trigger] = None, config_path: str = None):
        self.triggers = triggers or self._load_triggers(config_path)
        self._callbacks: Dict[str, List[Callable]] = {}
        self._last_trigger_time: Dict[str, float] = {}
        self._events: List[TriggerEvent] = []
        self._max_events = 100

    def _load_triggers(self, path: str = None) -> List[Trigger]:
        """Load triggers from config or use defaults."""
        if path:
            try:
                data = json.loads(open(path, encoding='utf-8').read())
                return [
                    Trigger(**t) for t in data.get("triggers", [])
                ] or self.DEFAULT_TRIGGERS
            except Exception:
                pass
        return self.DEFAULT_TRIGGERS

    def subscribe(self, action: str, callback: Callable):
        """Subscribe a callback to an action name."""
        self._callbacks.setdefault(action, []).append(callback)

    def check(self, signals: Dict[str, float]) -> List[TriggerEvent]:
        """Evaluate all triggers against current signals."""
        now = time.time()
        events = []

        for trigger in self.triggers:
            # Cooldown
            last = self._last_trigger_time.get(trigger.name, 0)
            if now - last < trigger.cooldown_s:
                continue

            value = signals.get(trigger.metric, 0)
            if not self._compare(value, trigger.comparator, trigger.threshold):
                continue

            event = TriggerEvent(
                trigger=trigger.name,
                action=trigger.action,
                severity=trigger.severity,
                message=trigger.message_template.format(
                    name=trigger.name, metric=trigger.metric,
                    value=value, comparator=trigger.comparator,
                    threshold=trigger.threshold,
                ),
                value=value,
                threshold=trigger.threshold,
                timestamp=now,
            )

            self._events.append(event)
            self._last_trigger_time[trigger.name] = now
            events.append(event)

            # Callbacks
            if trigger.callback:
                trigger.callback(trigger, value, event)
            for cb in self._callbacks.get(trigger.action, []):
                try:
                    cb(trigger, value, event)
                except Exception as e:
                    logger.debug("Callback failed for %s: %s", trigger.name, e)

            if len(self._events) > self._max_events:
                self._events.pop(0)

        return events

    @staticmethod
    def _compare(value: float, comparator: str, threshold: float) -> bool:
        return {
            ">": value > threshold,
            "<": value < threshold,
            ">=": value >= threshold,
            "<=": value <= threshold,
        }.get(comparator, False)

    def status(self) -> dict:
        return {
            "triggers": len(self.triggers),
            "events_total": len(self._events),
            "recent": [
                {"trigger": e.trigger, "action": e.action, "message": e.message}
                for e in self._events[-5:]
            ],
        }
