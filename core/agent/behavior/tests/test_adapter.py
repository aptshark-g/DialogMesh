"""Tests for v4 BehaviorGraph adapter and CausalSubstrate integration."""
from __future__ import annotations
import time
import tempfile
import os

from core.agent.events.event_ir import EventIR
from core.agent.behavior.adapter import (
    BehaviorGraphAdapter, BehaviorContextItem, BehaviorChainResult,
)
from core.agent.behavior.causal_adapter import (
    CausalSubstrateAdapter, CausalInsight,
)
from core.agent.behavior.runtime_hook import (
    BehaviorGraphRuntimeHook, register_with_engine,
)


def test_record_event():
    adapter = BehaviorGraphAdapter()
    event = EventIR(
        id="evt_001",
        kind="dialog.message",
        payload={"text": "Hello world", "source": "user"},
    )
    sid = adapter.record_event(event)
    assert sid.startswith("bs_")
    assert adapter.node_count == 1
    print("✓ test_record_event passed")


def test_record_multiple_events():
    adapter = BehaviorGraphAdapter()
    for i in range(3):
        event = EventIR(
            id=f"evt_{i:03d}",
            kind="dialog.message",
            payload={"text": f"Message {i}"},
        )
        adapter.record_event(event)

    assert adapter.node_count == 3
    assert adapter.edge_count == 2  # linked chain
    print("✓ test_record_multiple_events passed")


def test_context_source_retrieve():
    adapter = BehaviorGraphAdapter()
    adapter.record_step("deploy to production", "api")
    adapter.record_step("monitor logs", "tool")
    adapter.record_step("rollback deployment", "api")

    items = adapter.retrieve("deploy", top_k=2)
    assert len(items) > 0
    assert items[0].source == "behavior"
    print("✓ test_context_source_retrieve passed")


def test_chain_for_causal():
    adapter = BehaviorGraphAdapter()
    for i in range(5):
        adapter.record_step(f"step_{i}", "dialog")

    chain = adapter.get_recent_chain(n_steps=3)
    assert isinstance(chain, BehaviorChainResult)
    assert len(chain.steps) <= 3
    print("✓ test_chain_for_causal passed")


def test_persistence():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        adapter = BehaviorGraphAdapter(graph_path=path, auto_save=True)
        adapter.record_step("test persistence", "config")
        adapter.save()

        adapter2 = BehaviorGraphAdapter(graph_path=path)
        adapter2.load(path)
        assert adapter2.node_count >= 1
        print("✓ test_persistence passed")
    finally:
        os.unlink(path)


def test_causal_adapter():
    behavior = BehaviorGraphAdapter()
    for i in range(12):  # > MIN_CHAIN=10
        behavior.record_step(f"action_{i}", "dialog")

    causal = CausalSubstrateAdapter(behavior, min_chain_length=5)
    chain = behavior.get_recent_chain(n_steps=12)

    assert causal.should_trigger(chain)
    insights = causal.process_chain(chain)
    # May be empty if v3_2 substrate can't match skeletons, but should not crash
    assert isinstance(insights, list)
    print(f"✓ test_causal_adapter passed ({len(insights)} insights)")


def test_causal_retrieve():
    behavior = BehaviorGraphAdapter()
    behavior.record_step("deploy service", "api")
    behavior.record_step("check health", "tool")

    causal = CausalSubstrateAdapter(behavior)
    items = causal.retrieve("deploy", top_k=2)
    assert isinstance(items, list)
    print("✓ test_causal_retrieve passed")


def test_runtime_hook():
    from core.agent.runtime.engine import CognitiveRuntimeEngine

    engine = CognitiveRuntimeEngine()
    hook = register_with_engine(engine, enable_causal=False)

    event = EventIR(id="evt_001", kind="dialog.message", payload={"text": "test"})
    hook.on_event(event)
    assert hook.behavior_adapter.node_count == 1

    stats = hook.stats()
    assert "behavior" in stats
    assert "causal" in stats
    print("✓ test_runtime_hook passed")


if __name__ == "__main__":
    test_record_event()
    test_record_multiple_events()
    test_context_source_retrieve()
    test_chain_for_causal()
    test_persistence()
    test_causal_adapter()
    test_causal_retrieve()
    test_runtime_hook()
    print("\nAll tests passed.")
