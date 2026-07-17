"""PlanningBench — tests ExecutionTrace reasoning chain quality.

Scenarios: dependency_chain, conflict_resolve, multi_perspective, causal_reason.
"""
import sys, os, json
sys.path.insert(0, '.')
from core.agent.v4.cognitive.monitor_report import MonitorReport
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.mock_provider import MockProvider
from core.agent.v4.event_ir import DialogAdapter

SCENARIOS = {
    "dependency_chain": {"turns": [
        ("USER", "What does PerspectivePlanner depend on?"),
        ("USER", "And what does that depend on?"),
        ("USER", "Trace full chain down to ContentProvider."),
        ("USER", "Total depth of this chain?"),
        ("USER", "Which node has most dependents?"),
    ]},
    "conflict_resolve": {"turns": [
        ("USER", "Should ContextCompiler use BFS or DFS?"),
        ("USER", "Design doc says water-wave, not BFS."),
        ("USER", "Is water-wave actually BFS-based?"),
        ("USER", "How to resolve this?"),
    ]},
    "multi_perspective": {"turns": [
        ("USER", "Architecture view of the system."),
        ("USER", "Engineering implementation view."),
        ("USER", "Evolution history view."),
        ("USER", "Execution runtime view."),
    ]},
    "causal_reason": {"turns": [
        ("USER", "What causes DiscourseTree to fork?"),
        ("USER", "Does fork affect profile stability?"),
        ("USER", "Downstream effects of unstable profile?"),
        ("USER", "Root cause chain?"),
    ]},
}


def run_planning_bench():
    report = MonitorReport("bench_planning")
    print("PlanningBench — ExecutionTrace Quality")
    print("=" * 40)

    for name, sc in SCENARIOS.items():
        prov = MockProvider("mock", {"response_text": "[Mock] Analysis..."})
        eng = CognitiveRuntimeEngine(llm_provider=prov)
        eng.start()
        ad = DialogAdapter()
        for i, (sp, text) in enumerate(sc["turns"]):
            if sp == "USER":
                eng.on_event(ad.adapt(text, session_id=name, turn_number=i+1))

        t = eng._trace_v3; m = t.meta_analyze()
        info = {"total": m["total_transitions"], "types": sorted(m["reason_distribution"].keys())}
        report.record("scenario_done", info, name)
        print(f"  [{name}]: {info['total']}trans {info['types']}")

    report.finish()
    print(f"  Saved: data/monitor/{report.session_id}.jsonl")


if __name__ == "__main__":
    run_planning_bench()
