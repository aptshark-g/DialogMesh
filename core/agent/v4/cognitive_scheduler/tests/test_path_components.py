"""Tests for path-aware scheduler components (v4).

Covers:
    - PathStateMachine: state transitions, mark_success/failure/recovery
    - EventCounter: threshold, reset, dynamic threshold
    - ConfigDrivenTriggerPolicy: trigger logic, config merging, state tracking
    - PathAwareScheduler: integration with state machines and event counter
    - Engine integration: event counter auto-trigger, Deep Path evaluation
"""
import pytest
import time
from unittest.mock import MagicMock, patch

from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    PathState,
    PathStateMachine,
    EventCounter,
    ConfigDrivenTriggerPolicy,
)
from core.agent.v4.cognitive_scheduler.path_models import (
    PathType,
    PathTask,
    PathWorkerPool,
    PathWorker,
)
from core.agent.v4.cognitive_scheduler.path_policy import PriorityPathPolicy
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler


# ============================================================================
# PathStateMachine Tests
# ============================================================================

class TestPathStateMachine:
    """Tests for standalone PathStateMachine."""

    def test_initial_state_is_idle(self):
        sm = PathStateMachine()
        sm.register("slow")
        assert sm.get_state("slow") == PathState.IDLE

    def test_idle_to_running_transition(self):
        sm = PathStateMachine()
        result = sm.transition("slow", PathState.RUNNING)
        assert result == PathState.RUNNING
        assert sm.is_running("slow")

    def test_running_to_idle_transition(self):
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        result = sm.transition("slow", PathState.IDLE)
        assert result == PathState.IDLE
        assert sm.is_idle("slow")

    def test_running_to_backlogged_transition(self):
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        result = sm.transition("slow", PathState.BACKLOGGED)
        assert result == PathState.BACKLOGGED
        assert sm.is_backlogged("slow")

    def test_backlogged_to_idle_transition(self):
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        sm.transition("slow", PathState.BACKLOGGED)
        result = sm.transition("slow", PathState.IDLE)
        assert result == PathState.IDLE
        assert sm.is_idle("slow")

    def test_invalid_transition_ignored(self):
        sm = PathStateMachine()
        # idle -> backlogged is invalid
        result = sm.transition("slow", PathState.BACKLOGGED)
        assert result == PathState.IDLE  # unchanged
        assert sm.is_idle("slow")

    def test_mark_success_resets_failures(self):
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        sm.mark_failure("slow")
        assert sm.is_backlogged("slow")
        sm.mark_success("slow")
        assert sm.is_idle("slow")

    def test_mark_failure_increments_failures(self):
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        sm.mark_failure("slow")
        # Access internal state to verify
        assert sm._paths["slow"].consecutive_failures == 1
        assert sm.is_backlogged("slow")

    def test_mark_recovery_from_backlogged(self):
        """NEW: mark_recovery() transitions backlogged → idle."""
        sm = PathStateMachine()
        sm.transition("slow", PathState.RUNNING)
        sm.mark_failure("slow")
        assert sm.is_backlogged("slow")
        assert sm._paths["slow"].consecutive_failures == 1

        sm.mark_recovery("slow")
        assert sm.is_idle("slow")
        assert sm._paths["slow"].consecutive_failures == 0

    def test_mark_recovery_on_idle_is_noop(self):
        """NEW: mark_recovery() on idle path should stay idle."""
        sm = PathStateMachine()
        sm.register("slow")
        sm.mark_recovery("slow")
        assert sm.is_idle("slow")

    def test_all_states_snapshot(self):
        sm = PathStateMachine()
        sm.transition("async", PathState.RUNNING)
        sm.transition("slow", PathState.BACKLOGGED)
        states = sm.all_states()
        assert states["async"] == PathState.RUNNING
        assert states["slow"] == PathState.BACKLOGGED

    def test_last_triggered_updated(self):
        sm = PathStateMachine()
        before = time.time()
        sm.transition("slow", PathState.RUNNING)
        after = time.time()
        triggered = sm._paths["slow"].last_triggered_at
        assert before <= triggered <= after


# ============================================================================
# EventCounter Tests
# ============================================================================

class TestEventCounter:
    """Tests for EventCounter sliding-window counter."""

    def test_initial_count_is_zero(self):
        ec = EventCounter(threshold=5)
        assert ec.count == 0
        assert not ec.is_ready

    def test_increment_below_threshold(self):
        ec = EventCounter(threshold=5)
        result = ec.increment(3)
        assert not result
        assert ec.count == 3
        assert not ec.is_ready

    def test_increment_reaches_threshold(self):
        ec = EventCounter(threshold=5)
        result = ec.increment(5)
        assert result
        assert ec.count == 5
        assert ec.is_ready

    def test_increment_exceeds_threshold(self):
        ec = EventCounter(threshold=5)
        ec.increment(3)
        result = ec.increment(3)
        assert result
        assert ec.count == 6

    def test_reset_clears_counter(self):
        ec = EventCounter(threshold=5)
        ec.increment(10)
        assert ec.is_ready
        ec.reset()
        assert ec.count == 0
        assert not ec.is_ready
        assert len(ec._history) == 0

    def test_dynamic_threshold(self):
        ec = EventCounter(threshold=10)
        ec.increment(8)
        assert not ec.is_ready
        ec.set_threshold(5)
        assert ec.is_ready  # 8 >= 5

    def test_history_tracks_timestamps(self):
        ec = EventCounter(threshold=50)
        before = time.time()
        ec.increment()
        after = time.time()
        assert len(ec._history) == 1
        assert before <= ec._history[0] <= after


# ============================================================================
# ConfigDrivenTriggerPolicy Tests
# ============================================================================

class TestConfigDrivenTriggerPolicy:
    """Tests for ConfigDrivenTriggerPolicy with mocked config."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.get_path.return_value = None
        return config

    @pytest.fixture
    def policy(self, mock_config):
        return ConfigDrivenTriggerPolicy(config=mock_config)

    def test_async_always_triggers(self, policy):
        assert policy.should_trigger("async") is True
        assert policy.should_trigger("async", event_count=0) is True

    def test_slow_triggers_at_threshold(self, policy):
        # Default threshold is 50
        assert not policy.should_trigger("slow", event_count=49)
        assert policy.should_trigger("slow", event_count=50)
        assert policy.should_trigger("slow", event_count=100)

    def test_slow_custom_threshold(self, mock_config):
        path_cfg = MagicMock()
        path_cfg.modules = [MagicMock()]
        path_cfg.modules[0].trigger_config = {"event_count": 10}
        mock_config.get_path.return_value = path_cfg

        policy = ConfigDrivenTriggerPolicy(config=mock_config)
        assert not policy.should_trigger("slow", event_count=9)
        assert policy.should_trigger("slow", event_count=10)

    def test_deep_requires_patterns_and_success_rate(self, policy):
        # Not enough patterns
        assert not policy.should_trigger("deep", pattern_count=3, success_count=10, failure_count=0)
        # Enough patterns but low success rate
        assert not policy.should_trigger("deep", pattern_count=5, success_count=5, failure_count=5)
        # Both conditions met
        assert policy.should_trigger("deep", pattern_count=5, success_count=10, failure_count=0)

    def test_deep_no_executions_returns_false(self, policy):
        assert not policy.should_trigger("deep", pattern_count=5, success_count=0, failure_count=0)

    def test_unknown_path_returns_false(self, policy):
        assert not policy.should_trigger("unknown", event_count=999)

    def test_state_machine_integration(self, policy):
        policy.transition("slow", PathState.RUNNING)
        assert policy.is_running("slow")
        policy.mark_success("slow")
        assert policy.is_idle("slow")

    def test_mark_failure_transitions_to_backlogged(self, policy):
        policy.transition("slow", PathState.RUNNING)
        policy.mark_failure("slow")
        assert policy.is_backlogged("slow")
        assert policy._path_runtimes["slow"].consecutive_failures == 1

    def test_callable_alias(self, policy):
        assert policy("async") is True
        assert not policy("slow", event_count=10)


# ============================================================================
# PathAwareScheduler Tests
# ============================================================================

class TestPathAwareScheduler:
    """Tests for PathAwareScheduler with mocked dependencies."""

    def test_initial_state_all_idle(self):
        scheduler = PathAwareScheduler()
        for path in PathType:
            assert scheduler.get_path_state(path) == PathState.IDLE

    def test_submit_task_to_queue(self):
        scheduler = PathAwareScheduler()
        task = PathTask(task_id="test_1", path=PathType.ASYNC, priority=5)
        scheduler.submit_to_path(task)
        assert len(scheduler.get_queue(PathType.ASYNC)) == 1

    def test_increment_event_counter(self):
        scheduler = PathAwareScheduler()
        # Default threshold is 50
        for i in range(49):
            assert not scheduler.increment_event_counter(1)
        assert scheduler.increment_event_counter(1)  # 50th event

    def test_custom_event_threshold(self):
        scheduler = PathAwareScheduler()
        scheduler._slow_event_threshold = 5
        for i in range(4):
            assert not scheduler.increment_event_counter(1)
        assert scheduler.increment_event_counter(1)  # 5th event

    def test_reset_event_counter(self):
        scheduler = PathAwareScheduler()
        scheduler.increment_event_counter(50)
        scheduler.reset_event_counter()
        assert scheduler._event_counter == 0

    def test_evaluate_deep_trigger_no_data(self):
        scheduler = PathAwareScheduler()
        assert not scheduler.evaluate_deep_trigger()

    def test_evaluate_deep_trigger_with_data(self):
        scheduler = PathAwareScheduler()
        # Simulate async successes
        scheduler._path_metrics[PathType.ASYNC]["success_count"] = 10
        scheduler._path_metrics[PathType.ASYNC]["failure_count"] = 0
        scheduler._deep_pattern_threshold = 5
        scheduler._deep_success_rate_threshold = 0.9
        assert scheduler.evaluate_deep_trigger()

    def test_stats_structure(self):
        scheduler = PathAwareScheduler()
        stats = scheduler.stats()
        assert "queue_size" in stats
        assert "workers" in stats
        assert "path_snapshots" in stats
        assert "event_counter" in stats
        assert "deep_trigger_ready" in stats
        for path in PathType:
            assert path.value in stats["path_snapshots"]


# ============================================================================
# Integration: Engine trigger logic
# ============================================================================

class TestEngineTriggerLogic:
    """Tests for engine.py integration with trigger policy and event counter."""

    def test_event_counter_auto_trigger(self):
        """Simulate engine.on_event() reaching threshold triggers Slow Path."""
        from core.agent.v4.cognitive_scheduler.path_trigger_policy import EventCounter

        counter = EventCounter(threshold=5)
        triggered = False

        for i in range(5):
            if counter.increment():
                triggered = True
                counter.reset()

        assert triggered

    def test_deep_path_trigger_evaluation(self):
        """Deep Path triggers when pattern_count >= threshold AND success_rate >= threshold."""
        from core.agent.v4.cognitive_scheduler.path_trigger_policy import ConfigDrivenTriggerPolicy

        mock_config = MagicMock()
        mock_config.get_path.return_value = None
        policy = ConfigDrivenTriggerPolicy(config=mock_config)

        # Success rate = 10/10 = 1.0, patterns = 10
        assert policy.should_trigger(
            "deep",
            pattern_count=10,
            success_count=10,
            failure_count=0,
        )

        # Success rate = 5/10 = 0.5, patterns = 5
        assert not policy.should_trigger(
            "deep",
            pattern_count=5,
            success_count=5,
            failure_count=5,
        )

    def test_path_state_transitions_in_engine_flow(self):
        """Simulate engine flow: event → async running → success → idle."""
        sm = PathStateMachine()

        # on_event starts async
        sm.transition("async", PathState.RUNNING)
        assert sm.is_running("async")

        # After processing, no backlog
        sm.mark_success("async")
        assert sm.is_idle("async")

    def test_backlogged_path_recovery(self):
        """NEW: Test backlogged path recovery via mark_recovery."""
        sm = PathStateMachine()

        # Simulate overload
        sm.transition("slow", PathState.RUNNING)
        sm.mark_failure("slow")
        assert sm.is_backlogged("slow")

        # After queue drain
        sm.mark_recovery("slow")
        assert sm.is_idle("slow")


# ============================================================================
# Parameter Loading Tests
# ============================================================================

class TestParameterLoading:
    """Verify parameters are read from config/WorldParams, not hard-coded."""

    def test_slow_threshold_from_config(self):
        mock_config = MagicMock()
        path_cfg = MagicMock()
        path_cfg.modules = [MagicMock()]
        path_cfg.modules[0].trigger = "checkpoint"
        path_cfg.modules[0].trigger_config = {"event_count": 25}
        mock_config.get_path.return_value = path_cfg

        policy = ConfigDrivenTriggerPolicy(config=mock_config)
        assert not policy.should_trigger("slow", event_count=24)
        assert policy.should_trigger("slow", event_count=25)

    def test_world_params_override(self):
        from core.agent.v4.world.params import WorldParams

        wp = WorldParams()
        wp.min_support = 5

        mock_config = MagicMock()
        mock_config.get_path.return_value = None

        policy = ConfigDrivenTriggerPolicy(config=mock_config, world_params=wp)
        cfg = policy.get_trigger_config("slow")
        assert cfg.get("min_support") == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
