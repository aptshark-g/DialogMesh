#!/usr/bin/env python3
"""Standalone test runner for path-aware scheduler components.

Run with: py tests/test_path_components_standalone.py
"""
import sys
import os
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    PathState,
    PathStateMachine,
    EventCounter,
    ConfigDrivenTriggerPolicy,
)
from core.agent.v4.cognitive_scheduler.path_models import PathType


# ---- Test utilities ----

_tests_passed = 0
_tests_failed = 0

def assert_eq(actual, expected, msg=""):
    global _tests_passed, _tests_failed
    if actual == expected:
        _tests_passed += 1
        print(f"  [PASS] {msg or 'assert_eq'}")
    else:
        _tests_failed += 1
        print(f"  [FAIL] {msg or 'assert_eq'}: expected {expected!r}, got {actual!r}")

def assert_true(value, msg=""):
    assert_eq(bool(value), True, msg or "assert_true")

def assert_false(value, msg=""):
    assert_eq(bool(value), False, msg or "assert_false")


def run_test_group(name, test_fn):
    print(f"\n{'='*60}")
    print(f"TEST GROUP: {name}")
    print(f"{'='*60}")
    try:
        test_fn()
    except Exception as e:
        global _tests_failed
        _tests_failed += 1
        print(f"  [ERROR] {e}")


# ---- Test: PathStateMachine ----

def test_path_state_machine():
    # Test 1: Initial state
    sm = PathStateMachine()
    sm.register("slow")
    assert_eq(sm.get_state("slow"), PathState.IDLE, "initial state is idle")

    # Test 2: idle -> running
    sm2 = PathStateMachine()
    result = sm2.transition("slow", PathState.RUNNING)
    assert_eq(result, PathState.RUNNING, "idle->running transition")
    assert_true(sm2.is_running("slow"), "is_running after transition")

    # Test 3: running -> idle
    sm2.transition("slow", PathState.IDLE)
    assert_true(sm2.is_idle("slow"), "running->idle transition")

    # Test 4: running -> backlogged
    sm3 = PathStateMachine()
    sm3.transition("slow", PathState.RUNNING)
    sm3.transition("slow", PathState.BACKLOGGED)
    assert_true(sm3.is_backlogged("slow"), "running->backlogged transition")

    # Test 5: backlogged -> idle
    sm3.transition("slow", PathState.IDLE)
    assert_true(sm3.is_idle("slow"), "backlogged->idle transition")

    # Test 6: Invalid transition (idle -> backlogged)
    sm4 = PathStateMachine()
    result = sm4.transition("slow", PathState.BACKLOGGED)
    assert_eq(result, PathState.IDLE, "invalid transition ignored")

    # Test 7: mark_success resets failures
    sm5 = PathStateMachine()
    sm5.transition("slow", PathState.RUNNING)
    sm5.mark_failure("slow")
    assert_true(sm5.is_backlogged("slow"), "mark_failure -> backlogged")
    sm5.mark_success("slow")
    assert_true(sm5.is_idle("slow"), "mark_success -> idle")

    # Test 8: mark_failure increments failures
    sm6 = PathStateMachine()
    sm6.transition("slow", PathState.RUNNING)
    sm6.mark_failure("slow")
    assert_eq(sm6._paths["slow"].consecutive_failures, 1, "failure count incremented")

    # Test 9: NEW - mark_recovery from backlogged
    sm7 = PathStateMachine()
    sm7.transition("slow", PathState.RUNNING)
    sm7.mark_failure("slow")
    assert_true(sm7.is_backlogged("slow"), "before recovery: backlogged")
    assert_eq(sm7._paths["slow"].consecutive_failures, 1, "before recovery: failures=1")
    sm7.mark_recovery("slow")
    assert_true(sm7.is_idle("slow"), "mark_recovery -> idle")
    assert_eq(sm7._paths["slow"].consecutive_failures, 0, "after recovery: failures=0")

    # Test 10: mark_recovery on idle is noop
    sm8 = PathStateMachine()
    sm8.register("slow")
    sm8.mark_recovery("slow")
    assert_true(sm8.is_idle("slow"), "mark_recovery on idle stays idle")

    # Test 11: all_states snapshot
    sm9 = PathStateMachine()
    sm9.transition("async", PathState.RUNNING)
    sm9.transition("slow", PathState.BACKLOGGED)
    states = sm9.all_states()
    assert_eq(states.get("async"), PathState.RUNNING, "all_states: async=running")
    assert_eq(states.get("slow"), PathState.BACKLOGGED, "all_states: slow=backlogged")

    print(f"\n  PathStateMachine: {_tests_passed} passed")


# ---- Test: EventCounter ----

def test_event_counter():
    global _tests_passed, _tests_failed
    before_passed = _tests_passed

    # Test 1: Initial state
    ec = EventCounter(threshold=5)
    assert_eq(ec.count, 0, "initial count is 0")
    assert_false(ec.is_ready, "initial is_ready is False")

    # Test 2: Increment below threshold
    result = ec.increment(3)
    assert_false(result, "increment below threshold")
    assert_eq(ec.count, 3, "count after +3")

    # Test 3: Increment reaches threshold
    ec2 = EventCounter(threshold=5)
    result = ec2.increment(5)
    assert_true(result, "increment reaches threshold")
    assert_true(ec2.is_ready, "is_ready at threshold")

    # Test 4: Increment exceeds threshold
    ec3 = EventCounter(threshold=5)
    ec3.increment(3)
    result = ec3.increment(3)
    assert_true(result, "increment exceeds threshold")
    assert_eq(ec3.count, 6, "count is 6")

    # Test 5: Reset
    ec4 = EventCounter(threshold=5)
    ec4.increment(10)
    assert_true(ec4.is_ready, "before reset: ready")
    ec4.reset()
    assert_eq(ec4.count, 0, "after reset: count=0")
    assert_false(ec4.is_ready, "after reset: not ready")
    assert_eq(len(ec4._history), 0, "after reset: history cleared")

    # Test 6: Dynamic threshold
    ec5 = EventCounter(threshold=10)
    ec5.increment(8)
    assert_false(ec5.is_ready, "dynamic: 8 < 10")
    ec5.set_threshold(5)
    assert_true(ec5.is_ready, "dynamic: 8 >= 5 after threshold change")

    # Test 7: History tracks timestamps
    ec6 = EventCounter(threshold=50)
    before = time.time()
    ec6.increment()
    after = time.time()
    assert_eq(len(ec6._history), 1, "history has 1 entry")
    assert_true(before <= ec6._history[0] <= after, "timestamp in range")

    print(f"\n  EventCounter: {_tests_passed - before_passed} passed")


# ---- Test: ConfigDrivenTriggerPolicy ----

def test_trigger_policy():
    global _tests_passed, _tests_failed
    before_passed = _tests_passed

    mock_config = MagicMock()
    mock_config.get_path.return_value = None
    policy = ConfigDrivenTriggerPolicy(config=mock_config)

    # Test 1: Async always triggers
    assert_true(policy.should_trigger("async"), "async always triggers")
    assert_true(policy.should_trigger("async", event_count=0), "async with 0 events")

    # Test 2: Slow at threshold
    assert_false(policy.should_trigger("slow", event_count=49), "slow: 49 < 50")
    assert_true(policy.should_trigger("slow", event_count=50), "slow: 50 >= 50")
    assert_true(policy.should_trigger("slow", event_count=100), "slow: 100 >= 50")

    # Test 3: Deep - not enough patterns
    assert_false(
        policy.should_trigger("deep", pattern_count=3, success_count=10, failure_count=0),
        "deep: not enough patterns"
    )

    # Test 4: Deep - enough patterns but low success rate
    assert_false(
        policy.should_trigger("deep", pattern_count=5, success_count=5, failure_count=5),
        "deep: low success rate"
    )

    # Test 5: Deep - both conditions met
    assert_true(
        policy.should_trigger("deep", pattern_count=5, success_count=10, failure_count=0),
        "deep: all conditions met"
    )

    # Test 6: Deep - no executions
    assert_false(
        policy.should_trigger("deep", pattern_count=5, success_count=0, failure_count=0),
        "deep: no executions"
    )

    # Test 7: Unknown path
    assert_false(policy.should_trigger("unknown", event_count=999), "unknown path")

    # Test 8: State machine integration
    policy.transition("slow", PathState.RUNNING)
    assert_true(policy.is_running("slow"), "policy: is_running")
    policy.mark_success("slow")
    assert_true(policy.is_idle("slow"), "policy: mark_success -> idle")

    # Test 9: mark_failure
    policy2 = ConfigDrivenTriggerPolicy(config=mock_config)
    policy2.transition("slow", PathState.RUNNING)
    policy2.mark_failure("slow")
    assert_true(policy2.is_backlogged("slow"), "policy: mark_failure -> backlogged")
    assert_eq(policy2._path_runtimes["slow"].consecutive_failures, 1, "policy: failure count")

    # Test 10: Callable alias
    assert_true(policy("async"), "callable: async")
    assert_false(policy("slow", event_count=10), "callable: slow")

    print(f"\n  ConfigDrivenTriggerPolicy: {_tests_passed - before_passed} passed")


# ---- Test: Parameter Loading ----

def test_parameter_loading():
    global _tests_passed, _tests_failed
    before_passed = _tests_passed

    # Test 1: Slow threshold from config
    mock_config = MagicMock()
    path_cfg = MagicMock()
    path_cfg.modules = [MagicMock()]
    path_cfg.modules[0].trigger = "checkpoint"
    path_cfg.modules[0].trigger_config = {"event_count": 25}
    mock_config.get_path.return_value = path_cfg

    policy = ConfigDrivenTriggerPolicy(config=mock_config)
    assert_false(policy.should_trigger("slow", event_count=24), "config: 24 < 25")
    assert_true(policy.should_trigger("slow", event_count=25), "config: 25 >= 25")

    # Test 2: WorldParams override
    from core.agent.v4.world.params import WorldParams
    wp = WorldParams()
    wp.min_support = 5

    mock_config2 = MagicMock()
    mock_config2.get_path.return_value = None
    policy2 = ConfigDrivenTriggerPolicy(config=mock_config2, world_params=wp)
    cfg = policy2.get_trigger_config("slow")
    assert_eq(cfg.get("min_support"), 5, "world_params override")

    print(f"\n  ParameterLoading: {_tests_passed - before_passed} passed")


# ---- Test: Engine Integration ----

def test_engine_integration():
    global _tests_passed, _tests_failed
    before_passed = _tests_passed

    # Test 1: Event counter auto-trigger
    counter = EventCounter(threshold=5)
    triggered = False
    for i in range(5):
        if counter.increment():
            triggered = True
            counter.reset()
    assert_true(triggered, "event counter auto-trigger at threshold")

    # Test 2: Deep Path trigger evaluation
    mock_config = MagicMock()
    mock_config.get_path.return_value = None
    policy = ConfigDrivenTriggerPolicy(config=mock_config)

    # Success rate = 1.0, patterns = 10
    assert_true(
        policy.should_trigger("deep", pattern_count=10, success_count=10, failure_count=0),
        "deep trigger: high success rate"
    )
    # Success rate = 0.5, patterns = 5
    assert_false(
        policy.should_trigger("deep", pattern_count=5, success_count=5, failure_count=5),
        "deep trigger: low success rate"
    )

    # Test 3: Engine flow simulation
    sm = PathStateMachine()
    sm.transition("async", PathState.RUNNING)
    assert_true(sm.is_running("async"), "engine: async running")
    sm.mark_success("async")
    assert_true(sm.is_idle("async"), "engine: async idle after success")

    # Test 4: Backlogged path recovery
    sm2 = PathStateMachine()
    sm2.transition("slow", PathState.RUNNING)
    sm2.mark_failure("slow")
    assert_true(sm2.is_backlogged("slow"), "engine: slow backlogged")
    sm2.mark_recovery("slow")
    assert_true(sm2.is_idle("slow"), "engine: slow recovered")

    print(f"\n  EngineIntegration: {_tests_passed - before_passed} passed")


# ---- Main ----

if __name__ == "__main__":
    print("=" * 60)
    print("PATH-AWARE SCHEDULER COMPONENT TESTS")
    print("=" * 60)

    run_test_group("PathStateMachine", test_path_state_machine)
    run_test_group("EventCounter", test_event_counter)
    run_test_group("ConfigDrivenTriggerPolicy", test_trigger_policy)
    run_test_group("ParameterLoading", test_parameter_loading)
    run_test_group("EngineIntegration", test_engine_integration)

    print("\n" + "=" * 60)
    print(f"RESULTS: {_tests_passed} passed, {_tests_failed} failed")
    print("=" * 60)

    if _tests_failed > 0:
        sys.exit(1)
    sys.exit(0)
