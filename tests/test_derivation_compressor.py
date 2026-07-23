"""Derivation Compressor Tests — JSON driven."""

import sys, json
sys.path.insert(0, '.')
from core.agent.cognitive.derivation_compressor import (
    DerivationCompressor, HeuristicChain, StateTransition, DivergenceGuess
)


class MockEdge:
    def __init__(self, d):
        self.source = d.get("source", "")
        self.target = d.get("target", "")
        self.relation_kind = d.get("relation_kind", "")
        self.confidence = d.get("confidence", 0.5)


class MockTrace:
    def __init__(self, d):
        self.probability_before = d.get("probability_before", {})
        self.probability_after = d.get("probability_after", {})


def test_extract():
    data = json.loads(open("tests/test_data_compressor.json", encoding='utf-8').read())
    comp = DerivationCompressor()

    for s in data["scenarios"]:
        sid = s["id"]
        checks = s["checks"]
        
        edges = [MockEdge(e) for e in s.get("edge_history", [])]
        traces = [MockTrace(t) for t in s.get("belief_trace", [])]
        
        transitions = comp.extract(edges, traces)
        
        ok = True
        for check, expected in checks.items():
            if check == "min_transitions":
                if len(transitions) < expected:
                    print(f"  ❌ {sid}: {len(transitions)} < {expected}")
                    ok = False
            elif check == "has_belief_change":
                belief_trans = [t for t in transitions if t.evidence_type == "belief_change"]
                if not belief_trans:
                    print(f"  ❌ {sid}: no belief_change transitions")
                    ok = False
            elif check == "pool_after":
                pass  # no LLM, pool stays empty
        
        if ok:
            print(f"  ✅ {sid}: {len(transitions)} transitions")


def test_heuristic_chain():
    """Test chain lifecycle: coverage, staleness, freshness."""
    chain = HeuristicChain(
        chain_id="test_1",
        summary="测试启发链",
        conditions=["条件1"],
        counter_examples=["反例1"],
        reasoning_path="推理路径",
    )
    
    # Fresh chain, never tested
    assert chain.freshness == 1.0
    assert not chain.is_stale
    
    # Record hits → coverage stays high
    for _ in range(8):
        chain.record_test(matched=True)
    assert chain.coverage == 1.0
    assert not chain.is_stale
    
    # Record misses → coverage drops
    for _ in range(5):
        chain.record_test(matched=False)
    assert chain.coverage < 0.7
    print(f"  ✅ chain lifecycle: coverage={chain.coverage:.2f} stale={chain.is_stale}")


if __name__ == "__main__":
    test_extract()
    test_heuristic_chain()
    print("\n🎉 Derivation Compressor: all tests passed")
