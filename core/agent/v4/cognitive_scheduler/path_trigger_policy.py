"""PathTriggerPolicy: path-aware trigger conditions with state machine.

This module provides:
    - PathState: enum for path lifecycle states
    - PathTriggerPolicy: evaluates trigger conditions from runtime config and WorldParams
    - EventCounter: sliding-window event counter for Slow Path auto-trigger
    - PathStateMachine: tracks per-path state transitions (idle → running → backlogged → idle)

Usage:
    policy = PathTriggerPolicy(config=runtime_config, world_params=world_params)
    if policy.should_trigger("slow", event_count=50):
        engine.trigger_checkpoint()
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.agent.v4.runtime.config import RuntimeConfig, PathConfig
from core.agent.v4.world.params import WorldParams


class PathState(Enum):
    """Lifecycle states for a cognitive path.

    Transitions:
        idle → running   : path starts executing
        running → idle   : path completes successfully
        running → backlogged : path is blocked (queue full, dependency waiting)
        backlogged → idle: backlog cleared, path ready again
    """

    IDLE = "idle"
    RUNNING = "running"
    BACKLOGGED = "backlogged"


class PathTriggerPolicy(ABC):
    """Abstract base for path trigger policies.

    Implementations evaluate whether a path should be triggered based on
    runtime configuration, world parameters, and current system state.
    """

    @abstractmethod
    def should_trigger(
        self,
        path_name: str,
        *,
        event_count: int = 0,
        pattern_count: int = 0,
        success_count: int = 0,
        failure_count: int = 0,
        **kwargs: Any,
    ) -> bool:
        """Evaluate whether the named path should trigger now.

        Args:
            path_name: One of "async", "slow", "deep", "fast".
            event_count: Number of events accumulated since last trigger.
            pattern_count: Number of patterns detected (Deep Path).
            success_count: Successful executions for success-rate calc.
            failure_count: Failed executions for success-rate calc.
            **kwargs: Additional context for extensibility.

        Returns:
            True if the path should trigger.
        """
        ...

    @abstractmethod
    def get_trigger_config(self, path_name: str) -> Dict[str, Any]:
        """Return merged trigger configuration for a path.

        Merges runtime.yaml trigger_config with WorldParams overrides.
        """
        ...


@dataclass
class _PathRuntime:
    """Internal mutable state tracked per path."""

    state: PathState = PathState.IDLE
    last_triggered_at: float = 0.0
    consecutive_failures: int = 0


class ConfigDrivenTriggerPolicy(PathTriggerPolicy):
    """Trigger policy driven by runtime.yaml + WorldParams.

    Trigger rules:
        - async : always (event-driven, no threshold)
        - slow  : event_count >= threshold OR time-based (handled externally)
        - deep  : pattern_count >= threshold AND success_rate >= threshold

    Parameters are read from:
        1. PathConfig.trigger_config in runtime.yaml
        2. WorldParams (for keys that exist there)
    """

    def __init__(
        self,
        config: RuntimeConfig,
        world_params: Optional[WorldParams] = None,
    ):
        self._config = config
        self._world_params = world_params or WorldParams()
        self._path_runtimes: Dict[str, _PathRuntime] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def should_trigger(
        self,
        path_name: str,
        *,
        event_count: int = 0,
        pattern_count: int = 0,
        success_count: int = 0,
        failure_count: int = 0,
        **kwargs: Any,
    ) -> bool:
        """Evaluate trigger conditions for *path_name*.

        Deep Path logic (from runtime.yaml):
            pattern_count >= 5 AND success_rate >= 0.9

        Slow Path logic:
            event_count >= threshold (default 50 from runtime.yaml)

        Async Path:
            always returns True (event-driven).
        """
        cfg = self.get_trigger_config(path_name)

        if path_name == "async":
            return True

        if path_name == "slow":
            threshold = cfg.get("event_count", 50)
            return event_count >= threshold

        if path_name == "deep":
            min_patterns = cfg.get("pattern_count", 5)
            min_success_rate = cfg.get("success_rate", 0.9)
            total = success_count + failure_count
            if total == 0:
                return False
            success_rate = success_count / total
            return pattern_count >= min_patterns and success_rate >= min_success_rate

        # Unknown path — conservative default
        return False

    def get_trigger_config(self, path_name: str) -> Dict[str, Any]:
        """Merge runtime.yaml trigger_config with WorldParams overrides.

        Priority: runtime.yaml trigger_config > WorldParams > built-in defaults.
        """
        path_cfg = self._config.get_path(path_name)
        base: Dict[str, Any] = dict(path_cfg.modules[0].trigger_config) if path_cfg and path_cfg.modules else {}

        # WorldParams overrides for known keys
        wp = self._world_params
        overrides: Dict[str, Any] = {}
        if hasattr(wp, "min_support"):
            overrides["min_support"] = wp.min_support
        if hasattr(wp, "max_conflict"):
            overrides["max_conflict"] = wp.max_conflict
        if hasattr(wp, "min_stability"):
            overrides["min_stability"] = wp.min_stability

        merged = {**overrides, **base}
        return merged

    # ------------------------------------------------------------------ #
    # PathStateMachine integration
    # ------------------------------------------------------------------ #

    def get_state(self, path_name: str) -> PathState:
        """Return current state of *path_name*."""
        return self._path_runtimes.get(path_name, _PathRuntime()).state

    def transition(self, path_name: str, new_state: PathState) -> PathState:
        """Transition *path_name* to *new_state* and return the new state.

        Valid transitions:
            idle → running
            running → idle | backlogged
            backlogged → idle
        """
        runtime = self._path_runtimes.setdefault(path_name, _PathRuntime())
        current = runtime.state

        valid = {
            PathState.IDLE: {PathState.RUNNING},
            PathState.RUNNING: {PathState.IDLE, PathState.BACKLOGGED},
            PathState.BACKLOGGED: {PathState.IDLE},
        }

        if new_state not in valid.get(current, set()):
            # Invalid transition — no-op, return current
            return current

        runtime.state = new_state
        if new_state == PathState.RUNNING:
            runtime.last_triggered_at = time.time()
        return new_state

    def mark_success(self, path_name: str) -> None:
        """Mark path execution as successful."""
        runtime = self._path_runtimes.setdefault(path_name, _PathRuntime())
        runtime.consecutive_failures = 0
        self.transition(path_name, PathState.IDLE)

    def mark_failure(self, path_name: str) -> None:
        """Mark path execution as failed; may transition to backlogged."""
        runtime = self._path_runtimes.setdefault(path_name, _PathRuntime())
        runtime.consecutive_failures += 1
        self.transition(path_name, PathState.BACKLOGGED)

    def is_idle(self, path_name: str) -> bool:
        """Return True if path is in IDLE state."""
        return self.get_state(path_name) == PathState.IDLE

    def is_running(self, path_name: str) -> bool:
        """Return True if path is currently RUNNING."""
        return self.get_state(path_name) == PathState.RUNNING

    def is_backlogged(self, path_name: str) -> bool:
        """Return True if path is BACKLOGGED."""
        return self.get_state(path_name) == PathState.BACKLOGGED

    def last_triggered(self, path_name: str) -> float:
        """Return timestamp of last trigger, or 0.0 if never triggered."""
        return self._path_runtimes.get(path_name, _PathRuntime()).last_triggered_at

    # ------------------------------------------------------------------ #
    # Back-compat: expose as simple callable
    # ------------------------------------------------------------------ #

    def __call__(
        self,
        path_name: str,
        *,
        event_count: int = 0,
        pattern_count: int = 0,
        success_count: int = 0,
        failure_count: int = 0,
        **kwargs: Any,
    ) -> bool:
        """Convenience alias for ``should_trigger``."""
        return self.should_trigger(
            path_name,
            event_count=event_count,
            pattern_count=pattern_count,
            success_count=success_count,
            failure_count=failure_count,
            **kwargs,
        )


@dataclass
class EventCounter:
    """Sliding-window event counter for Slow Path auto-trigger.

    Automatically triggers Slow Path when ``event_count >= threshold``.
    The counter is reset explicitly via ``reset()`` after a checkpoint.

    Args:
        threshold: Number of events required to trigger (default 50).
    """

    threshold: int = 50
    _count: int = field(default=0, repr=False)
    _history: List[float] = field(default_factory=list, repr=False)

    def increment(self, n: int = 1) -> bool:
        """Increment counter by *n* and return whether threshold is reached.

        Returns:
            True if counter has reached or exceeded threshold.
        """
        self._count += n
        self._history.append(time.time())
        return self._count >= self.threshold

    def reset(self) -> None:
        """Reset counter to zero (call after checkpoint completes)."""
        self._count = 0
        self._history.clear()

    @property
    def count(self) -> int:
        """Current event count."""
        return self._count

    @property
    def is_ready(self) -> bool:
        """True if threshold has been reached."""
        return self._count >= self.threshold

    def set_threshold(self, threshold: int) -> None:
        """Update threshold dynamically (e.g., from WorldParams)."""
        self.threshold = threshold


class PathStateMachine:
    """Per-path state machine manager: idle → running → backlogged → idle.

    Wraps multiple ``_PathRuntime`` instances and provides batch operations.
    Usually owned by ``ConfigDrivenTriggerPolicy`` but can be used standalone.
    """

    def __init__(self):
        self._paths: Dict[str, _PathRuntime] = {}

    def register(self, path_name: str) -> None:
        """Register a new path if not already known."""
        if path_name not in self._paths:
            self._paths[path_name] = _PathRuntime()

    def transition(self, path_name: str, new_state: PathState) -> PathState:
        """Transition *path_name* to *new_state*."""
        self.register(path_name)
        runtime = self._paths[path_name]
        current = runtime.state

        valid = {
            PathState.IDLE: {PathState.RUNNING},
            PathState.RUNNING: {PathState.IDLE, PathState.BACKLOGGED},
            PathState.BACKLOGGED: {PathState.IDLE},
        }

        if new_state not in valid.get(current, set()):
            return current

        runtime.state = new_state
        if new_state == PathState.RUNNING:
            runtime.last_triggered_at = time.time()
        return new_state

    def get_state(self, path_name: str) -> PathState:
        self.register(path_name)
        return self._paths[path_name].state

    def is_idle(self, path_name: str) -> bool:
        return self.get_state(path_name) == PathState.IDLE

    def is_running(self, path_name: str) -> bool:
        return self.get_state(path_name) == PathState.RUNNING

    def is_backlogged(self, path_name: str) -> bool:
        return self.get_state(path_name) == PathState.BACKLOGGED

    def all_states(self) -> Dict[str, PathState]:
        """Return snapshot of all path states."""
        return {name: rt.state for name, rt in self._paths.items()}

    def mark_success(self, path_name: str) -> None:
        """Mark path as successfully completed → idle."""
        self.register(path_name)
        self._paths[path_name].consecutive_failures = 0
        self.transition(path_name, PathState.IDLE)

    def mark_failure(self, path_name: str) -> None:
        """Mark path as failed → backlogged."""
        self.register(path_name)
        self._paths[path_name].consecutive_failures += 1
        self.transition(path_name, PathState.BACKLOGGED)

    def mark_recovery(self, path_name: str) -> None:
        """Mark path as recovered from backlogged → idle.

        Called when a backlogged path's queue has been drained and
        the path is ready to accept new tasks again.
        """
        self.register(path_name)
        self._paths[path_name].consecutive_failures = 0
        self.transition(path_name, PathState.IDLE)
