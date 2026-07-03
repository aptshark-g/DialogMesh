# -*- coding: utf-8 -*-
"""
Run orchestrator end-to-end tests directly without pytest plugin system.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.agent.v3_0.orchestrator.orchestrator import (
    AlgorithmEngine,
    FusionEngine,
    Orchestrator,
)
from core.agent.v3_0.orchestrator.models import (
    OrchestratorConfig,
    LLMInstanceResult,
    FusionSource,
)
from core.agent.v3_0.orchestrator.tests.test_orchestrator import (
    TestOrchestrator,
    TestEndToEnd,
    TestSystemBootstrap,
    TestFusionEngine,
    TestAlgorithmEngine,
    TestModels,
)

passed = 0
failed = 0
errors = []


def run_sync(coro, name):
    global passed, failed
    try:
        asyncio.run(coro)
        print(f"  [PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1
        errors.append((name, e))


print("=" * 60)
print("DialogMesh v3.0 Orchestrator End-to-End Tests")
print("=" * 60)

# ── TestModels ─────────────────────────────────────────
print("\n--- TestModels ---")
tm = TestModels()
try:
    tm.test_turn_context_lifecycle()
    print("  [PASS] test_turn_context_lifecycle")
    passed += 1
except Exception as e:
    print(f"  [FAIL] test_turn_context_lifecycle: {e}")
    failed += 1

try:
    tm.test_orchestrator_result_to_agent_message()
    print("  [PASS] test_orchestrator_result_to_agent_message")
    passed += 1
except Exception as e:
    print(f"  [FAIL] test_orchestrator_result_to_agent_message: {e}")
    failed += 1

try:
    tm.test_system_health()
    print("  [PASS] test_system_health")
    passed += 1
except Exception as e:
    print(f"  [FAIL] test_system_health: {e}")
    failed += 1

# ── TestFusionEngine ───────────────────────────────────
print("\n--- TestFusionEngine ---")
config = OrchestratorConfig(
    enable_pcr_llm=False,
    enable_intent_llm=False,
    enable_planning_llm=False,
    enable_meta_cognitive_llm=False,
    enable_answer_llm=False,
    enable_reflective_llm=False,
    fallback_to_algorithm=True,
    fallback_to_single_task=True,
    clarification_threshold=0.3,
)
for name, test_fn in [
    ("test_algorithm_high_confidence", TestFusionEngine().test_algorithm_high_confidence),
    ("test_llm_high_confidence", TestFusionEngine().test_llm_high_confidence),
    ("test_both_low_confidence_fallback", TestFusionEngine().test_both_low_confidence_fallback),
    ("test_conflict_detection", TestFusionEngine().test_conflict_detection),
    ("test_weighted_fusion", TestFusionEngine().test_weighted_fusion),
]:
    try:
        test_fn(config)
        print(f"  [PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1
        errors.append((name, e))

# ── TestAlgorithmEngine ─────────────────────────────────
print("\n--- TestAlgorithmEngine ---")
_alg_engine = AlgorithmEngine()
for method_name in [
    "test_pcr_analysis",
    "test_intent_parsing_scan",
    "test_intent_parsing_read",
    "test_intent_parsing_unknown",
]:
    try:
        getattr(TestAlgorithmEngine(), method_name)(_alg_engine)
        print(f"  [PASS] {method_name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {method_name}: {e}")
        failed += 1

# ── TestOrchestrator (integration) ──────────────────────
print("\n--- TestOrchestrator ---")
config = OrchestratorConfig(
    enable_pcr_llm=False,
    enable_intent_llm=False,
    enable_planning_llm=False,
    enable_meta_cognitive_llm=False,
    enable_answer_llm=False,
    enable_reflective_llm=False,
    fallback_to_algorithm=True,
    fallback_to_single_task=True,
    clarification_threshold=0.3,
)
for name, coro in [
    ("test_process_turn_simple", TestOrchestrator().test_process_turn_simple(config)),
    ("test_process_turn_clarification", TestOrchestrator().test_process_turn_clarification(config)),
    ("test_process_turn_task_graph", TestOrchestrator().test_process_turn_task_graph(config)),
    ("test_orchestrator_health", TestOrchestrator().test_orchestrator_health(config)),
    ("test_orchestrator_stats", TestOrchestrator().test_orchestrator_stats(config)),
    ("test_orchestrator_close", TestOrchestrator().test_orchestrator_close(config)),
]:
    run_sync(coro, name)

# ── TestSystemBootstrap ─────────────────────────────────
print("\n--- TestSystemBootstrap ---")
for name, coro in [
    ("test_full_startup", TestSystemBootstrap().test_full_startup()),
    ("test_phase_results", TestSystemBootstrap().test_phase_results()),
    ("test_shutdown_idempotent", TestSystemBootstrap().test_shutdown_idempotent()),
    ("test_orchestrator_after_startup", TestSystemBootstrap().test_orchestrator_after_startup()),
]:
    run_sync(coro, name)

# ── TestEndToEnd (the core!) ────────────────────────────
print("\n--- TestEndToEnd ---")
for name, coro in [
    ("test_memory_scan_workflow", TestEndToEnd().test_memory_scan_workflow()),
    ("test_multi_session_isolation", TestEndToEnd().test_multi_session_isolation()),
]:
    run_sync(coro, name)

# ── Summary ─────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"Results: PASSED={passed}, FAILED={failed}")
print("=" * 60)

if errors:
    print("\nErrors:")
    for name, e in errors:
        print(f"  {name}: {e}")

if failed > 0:
    sys.exit(1)
