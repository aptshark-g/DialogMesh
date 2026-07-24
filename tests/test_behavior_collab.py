"""Behavior LLM Collaborative Tests — JSON-driven."""

import sys, json
sys.path.insert(0, '.')
from core.agent.behavior.llm_collaborative import BehaviorLLMCollaborator


class MockEdge:
    def __init__(self, from_step="诊断", to_step="修复", success_rate=0.8,
                 correction_count=2, sample_count=10, is_stable=True, activation_count=5):
        self.from_step_id = from_step
        self.to_step_id = to_step
        self.success_rate = success_rate
        self.correction_count = correction_count
        self.sample_count = sample_count
        self.is_stable = is_stable
        self.activation_count = activation_count


def test_explain_drift():
    collab = BehaviorLLMCollaborator()  # no LLM
    
    # Stable edge → no issue
    stable = MockEdge(is_stable=True, success_rate=0.85)
    r = collab.explain_drift(stable)
    assert r["explanation"] == "no LLM"
    print("  ✅ stable edge: no LLM fallback")

    # Unstable edge with LLM (mock)
    class MockLLM:
        def generate(self, p, **kw):
            return '{"explanation": "user switched toolchain", "severity": 0.7, "suggestion": "update prediction weight"}'

    collab_llm = BehaviorLLMCollaborator(llm=MockLLM())
    unstable = MockEdge(is_stable=False, success_rate=0.3, correction_count=5)
    r = collab_llm.explain_drift(unstable)
    assert r["severity"] > 0.5
    print(f"  ✅ unstable edge: severity={r['severity']} explain={r['explanation'][:50]}")


def test_discover_patterns():
    graph = {
        "unstable_edges": ["诊断→修复 (success=0.3)", "修复→探索 (success=0.4)"],
        "correction_chains": ["诊断→修复→correction→诊断"],
        "top_edges": ["诊断→修复 (success=0.85)", "修复→部署 (success=0.9)"],
    }
    collab = BehaviorLLMCollaborator()
    patterns = collab.discover_patterns(graph)
    assert patterns == []  # no LLM
    print("  ✅ discover: no LLM fallback")

    class MockLLM:
        def generate(self, p, **kw):
            return '[{"pattern": "diagnose→fix oscillation", "confidence": 0.8, "action": "pillar"}]'
    collab_llm = BehaviorLLMCollaborator(llm=MockLLM())
    patterns = collab_llm.discover_patterns(graph)
    assert len(patterns) == 1
    print(f"  ✅ discover: pattern={patterns[0]['pattern'][:50]}")


def test_suggest_thresholds():
    stats = {"false_positives": 5, "false_negatives": 2, 
             "current_success_threshold": 0.7, "current_instability_threshold": 0.3}
    collab = BehaviorLLMCollaborator()
    r = collab.suggest_thresholds(stats)
    assert r == stats  # no LLM
    print("  ✅ suggest: no LLM fallback")

    class MockLLM:
        def generate(self, p, **kw):
            return '{"success_threshold": 0.65, "instability_threshold": 0.25, "reason": "too many FP"}'
    collab_llm = BehaviorLLMCollaborator(llm=MockLLM())
    r = collab_llm.suggest_thresholds(stats)
    assert r["success_threshold"] < 0.7
    print(f"  ✅ suggest: new_threshold={r['success_threshold']}")


def test_analyze_corrections():
    corrections = [
        {"from": "诊断", "to": "修复", "corrected_to": "探索", "turn": 5},
        {"from": "诊断", "to": "修复", "corrected_to": "探索", "turn": 6},
    ]
    class MockLLM:
        def generate(self, p, **kw):
            return '{"root_cause": "agent misidentifies exploratory query as repair", "suggested_fix": "tune intent classifier", "confidence": 0.85}'
    collab = BehaviorLLMCollaborator(llm=MockLLM())
    r = collab.analyze_correction_chain(corrections)
    assert r["confidence"] > 0.5
    print(f"  ✅ corrections: root={r['root_cause'][:50]}")


if __name__ == "__main__":
    test_explain_drift()
    test_discover_patterns()
    test_suggest_thresholds()
    test_analyze_corrections()
    print("\n🎉 Behavior LLM Collaborative: all tests passed")
