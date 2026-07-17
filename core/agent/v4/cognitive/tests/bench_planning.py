"""PlanningBench — tests ExecutionTrace reasoning chain quality.

LLMs-Planning benchmark: multi-step reasoning tasks.
Measures if ExecutionTrace captures the full OBSERVE→INFER→REFLECT chain
and if transitions are correctly sequenced.

Scenarios:
  - dependency_chain: infer component dependencies
  - conflict_resolve: detect + resolve contradictions
  - multi_perspective: switch between architecture/engineering views
  - causal_reason: trace cause→effect relationships
"""
import sys, os, json
sys.path.insert(0, '.')

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.mock_provider import MockProvider
from core.agent.v4.event_ir import DialogAdapter
from core.agent.v4.state.state_object import TransitionReason


SCENARIOS = {
    "dependency_chain": {
        "turns": [
            ("USER", "What does the PerspectivePlanner depend on?"),
            ("USER", "And what does that depend on?"),
            ("USER", "Trace the full chain from PerspectivePlanner down to ContentProvider."),
            ("USER", "What's the total depth of this dependency chain?"),
            ("USER", "Which node has the most dependents?"),
        ],
        "expect": {"min_transitions": 10, "types": ["observe", "infer", "reflect", "activate"]},
    },
    "conflict_resolve": {
        "turns": [
            ("USER", "Should the ContextCompiler use BFS or DFS?"),
            ("USER", "But the design doc says to use water-wave expansion, not BFS."),
            ("USER", "If water-wave is BFS-based, is there actually a contradiction?"),
            ("USER", "How would you resolve this — BFS, DFS, or water-wave?"),
        ],
        "expect": {"min_transitions": 8, "types": ["observe", "infer", "reflect"]},
    },
    "multi_perspective": {
        "turns": [
            ("USER", "Explain this system from an architecture view."),
            ("USER", "Now from an engineering/implementation view."),
            ("USER", "From an evolution/history view — how did it develop?"),
            ("USER", "Finally from an execution/runtime view."),
        ],
        "expect": {"min_transitions": 8, "types": ["observe", "infer", "reflect"]},
    },
    "causal_reason": {
        "turns": [
            ("USER", "What causes the DiscourseTree to fork?"),
            ("USER", "Does that fork affect profile stability?"),
            ("USER", "If profile becomes unstable, what downstream effects?"),
            ("USER", "What's the root cause chain here?"),
        ],
        "expect": {"min_transitions": 8, "types": ["observe", "infer", "reflect"]},
    },
}


def run_scenario(engine, name, scenario):
    ad = DialogAdapter()
    for i, (speaker, text) in enumerate(scenario["turns"]):
        if speaker == "USER":
            engine.on_event(ad.adapt(text, session_id=name, turn_number=i+1))

    trace = engine._trace_v3
    m = trace.meta_analyze()
    dist = m["reason_distribution"]
    types = sorted(dist.keys())
    total = m["total_transitions"]
    
    expected = scenario.get("expect", {})
    min_t = expected.get("min_transitions", 0)
    required_types = expected.get("types", [])
    missing = [t for t in required_types if t not in types]

    return {
        "scenario": name,
        "total_transitions": total,
        "types": types,
        "type_count": len(types),
        "missing_types": missing,
        "meets_min": total >= min_t,
        "all_types_present": len(missing) == 0,
        "rejects": dist.get("reject", 0),
        "strengthens": dist.get("strengthen", 0),
    }


def run_planning_bench():
    print("PlanningBench — ExecutionTrace Quality")
    print("=" * 40)

    all_results = []
    for name, scenario in SCENARIOS.items():
        prov = MockProvider("mock", {"response_text": "[Mock] Analysis: the component chain shows..."})
        eng = CognitiveRuntimeEngine(llm_provider=prov)
        eng.start()
        result = run_scenario(eng, name, scenario)
        all_results.append(result)

        print(f"\n[{name}]:")
        print(f"  transitions={result['total_transitions']} types={result['types']}")
        if result['missing_types']:
            print(f"  missing: {result['missing_types']} ❌")
        else:
            print(f"  all_types_present ✅")
        print(f"  meets_min={result['meets_min']} rejects={result['rejects']} strengthens={result['strengthens']}")

    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/planning_bench.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # Score
    passed = sum(1 for r in all_results if r["all_types_present"])
    print(f"\nScore: {passed}/{len(SCENARIOS)} scenarios pass type coverage")
    print(f"Saved: data/monitor/planning_bench.json")


if __name__ == "__main__":
    run_planning_bench()
