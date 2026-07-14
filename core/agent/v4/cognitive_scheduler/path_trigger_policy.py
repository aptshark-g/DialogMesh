"""PathTriggerPolicy: Config-driven path triggering with state machine.

Replaces hard-coded trigger logic in engine.py with configurable,
parameter-registry-aware trigger decisions.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class PathState(str, Enum):
    """Path lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    BACKLOGGED = "backlogged"


class PathName(str, Enum):
    """Cognitive runtime paths."""
    ASYNC = "async"
    SLOW = "slow"
    DEEP = "deep"


@dataclass
class PathStateRecord:
    """Mutable state record for a single path."""
    state: PathState = PathState.IDLE
    last_triggered_at: float = 0.0
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    def mark_trigger(self):
        self.state = PathState.RUNNING
        self.last_triggered_at = time.time()
        self.trigger_count += 1

    def mark_success(self):
        self.state = PathState.IDLE
        self.success_count += 1
        self.consecutive_failures = 0

    def mark_failure(self):
        self.failure_count += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.state = PathState.BACKLOGGED

    def mark_recovery(self):
        self.state = PathState.IDLE
        self.consecutive_failures = 0


class PathStateMachine:
    """Manages state for all cognitive paths."""

    VALID_TRANSITIONS = {
        PathState.IDLE: {PathState.RUNNING},
        PathState.RUNNING: {PathState.IDLE, PathState.BACKLOGGED},
        PathState.BACKLOGGED: {PathState.IDLE},
    }

    def __init__(self):
        self._paths: Dict[str, PathStateRecord] = {
            PathName.ASYNC: PathStateRecord(),
            PathName.SLOW: PathStateRecord(),
            PathName.DEEP: PathStateRecord(),
        }

    def get(self, path_name: str) -> PathStateRecord:
        return self._paths.get(path_name, PathStateRecord())

    def transition(self, path_name: str, new_state: PathState) -> bool:
        """Attempt state transition. Returns True if valid."""
        record = self._paths.get(path_name)
        if record is None:
            return False
        if new_state not in self.VALID_TRANSITIONS.get(record.state, set()):
            return False
        record.state = new_state
        return True

    def mark_trigger(self, path_name: str):
        self._paths[path_name].mark_trigger()

    def mark_success(self, path_name: str):
        self._paths[path_name].mark_success()

    def mark_failure(self, path_name: str):
        self._paths[path_name].mark_failure()

    def is_running(self, path_name: str) -> bool:
        return self._paths.get(path_name, PathStateRecord()).state == PathState.RUNNING

    def is_backlogged(self, path_name: str) -> bool:
        return self._paths.get(path_name, PathStateRecord()).state == PathState.BACKLOGGED

    def stats(self) -> Dict[str, Dict]:
        return {
            name: {
                "state": record.state.value,
                "trigger_count": record.trigger_count,
                "success_count": record.success_count,
                "failure_count": record.failure_count,
                "consecutive_failures": record.consecutive_failures,
            }
            for name, record in self._paths.items()
        }


class EventCounter:
    """Sliding-window event counter for automatic checkpoint triggering."""

    def __init__(self, threshold: int = 50, window_seconds: float = 3600):
        self.threshold = threshold
        self.window_seconds = window_seconds
        self._events: List[float] = []

    def increment(self) -> bool:
        """Add an event. Returns True if threshold reached."""
        now = time.time()
        self._events.append(now)
        self._prune(now)
        return len(self._events) >= self.threshold

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        self._events = [t for t in self._events if t > cutoff]

    def count(self) -> int:
        self._prune(time.time())
        return len(self._events)

    def reset(self):
        self._events = []

    def should_trigger(self) -> bool:
        return self.count() >= self.threshold


class PathTriggerPolicy(ABC):
    """Abstract policy for deciding when to trigger a cognitive path."""

    @abstractmethod
    def should_trigger(self, path_name: str, context: Dict[str, Any]) -> bool:
        """Return True if path should be triggered now."""

    @abstractmethod
    def get_trigger_config(self, path_name: str) -> Dict[str, Any]:
        """Return trigger configuration for a path."""


class ConfigDrivenTriggerPolicy(PathTriggerPolicy):
    """Trigger policy driven by runtime.yaml + WorldParams.

    Args:
        runtime_config: RuntimeConfig from runtime.yaml
        world_params: WorldParams for threshold overrides
    """

    def __init__(self, runtime_config, world_params=None):
        self._config = runtime_config
        self._world_params = world_params
        self._state_machine = PathStateMachine()
        self._event_counter = EventCounter(
            threshold=self._get_slow_threshold(),
            window_seconds=3600,
        )

    def _get_slow_threshold(self) -> int:
        """Get Slow Path event threshold from config."""
        slow_path = self._config.get_path("slow")
        if slow_path and slow_path.modules:
            for mc in slow_path.modules:
                if mc.trigger == "checkpoint":
                    return mc.trigger_config.get("event_count", 50)
        return 50

    def _get_deep_threshold(self) -> Dict[str, Any]:
        """Get Deep Path threshold from config."""
        deep_path = self._config.get_path("deep")
        if deep_path and deep_path.modules:
            for mc in deep_path.modules:
                if mc.trigger == "threshold":
                    return {
                        "pattern_count": mc.trigger_config.get("pattern_count", 5),
                        "success_rate": mc.trigger_config.get("success_rate", 0.9),
                    }
        return {"pattern_count": 5, "success_rate": 0.9}

    def _get_optimizer_interval(self) -> int:
        """Get optimizer step interval from WorldParams."""
        if self._world_params:
            return getattr(self._world_params, "optimizer_interval", 3)
        return 3

    def should_trigger(self, path_name: str, context: Dict[str, Any]) -> bool:
        """Determine if a path should trigger based on current state."""
        # Prevent re-entry if already running
        if self._state_machine.is_running(path_name):
            return False

        if path_name == "async":
            # Async always triggers on event
            return True

        elif path_name == "slow":
            # Slow: event count threshold OR time-based
            event_count = context.get("event_count", 0)
            time_since_last = context.get("time_since_last_checkpoint", 0)
            time_threshold = context.get("time_threshold_minutes", 30) * 60
            return (event_count >= self._event_counter.threshold or
                    time_since_last >= time_threshold)

        elif path_name == "deep":
            # Deep: pattern count + success rate from Slow Path results
            results = context.get("slow_results", [])
            if not results:
                return False
            pattern_count = len([r for r in results if getattr(r, 'ok', False)])
            success_rate = pattern_count / len(results) if results else 0.0
            threshold = self._get_deep_threshold()
            return (pattern_count >= threshold["pattern_count"] and
                    success_rate >= threshold["success_rate"])

        return False

    def get_trigger_config(self, path_name: str) -> Dict[str, Any]:
        if path_name == "slow":
            return {"event_count": self._event_counter.threshold}
        elif path_name == "deep":
            return self._get_deep_threshold()
        return {}

    @property
    def state_machine(self) -> PathStateMachine:
        return self._state_machine

    @property
    def event_counter(self) -> EventCounter:
        return self._event_counter

    def on_event(self) -> bool:
        """Call on each event. Returns True if Slow Path should trigger."""
        return self._event_counter.increment()

    def should_optimize(self, checkpoint_count: int) -> bool:
        """Determine if optimizer should run."""
        interval = self._get_optimizer_interval()
        return checkpoint_count > 0 and checkpoint_count % interval == 0
