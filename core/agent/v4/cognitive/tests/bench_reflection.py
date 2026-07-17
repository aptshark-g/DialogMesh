"""ReflectionBench — tests epistemic agency: detect, reflect, correct, learn.

4 scenarios: math_error, hallucination, oversimplify, wrong_tool.
"""
import sys, os, json
sys.path.insert(0, '.')
from core.agent.v4.cognitive.monitor_report import MonitorReport
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.mock_provider import MockProvider
from core.agent.v4.event_ir import DialogAdapter

SCENARIOS = {
    "math_error": [
        ("USER", "How many objects in SemanticObject store?"),
        ("USER", "That seems too low — should be ~10,000."),
        ("USER", "Recount and verify."),
        ("USER", "Correct count?"),
    ],
    "hallucination": [
        ("USER", "Does DialogMesh have QuantumReasoningEngine?"),
        ("USER", "I don't see it in codebase. Why mention it?"),
        ("USER", "What modules actually exist?"),
    ],
    "oversimplify": [
        ("USER", "How does runtime pipeline work?"),
        ("USER", "Too simplified — use actual module names."),
        ("USER", "Specific compiler modules?"),
    ],
    "wrong_tool": [
        ("USER", "Extract relations using regex."),
        ("USER", "No — use JiebaRelationParser, not regex."),
        ("USER", "Now use BGE encoder for cross-language."),
    ],
}


def run_reflection_bench():
    report = MonitorReport("bench_reflection")
    print("ReflectionBench — Epistemic Agency")
    print("=" * 40)

    for name, turns in SCENARIOS.items():
        prov = MockProvider("mock", {"response_text": "[Mock] DialogMesh modules include..."})
        eng = CognitiveRuntimeEngine(llm_provider=prov)
        eng.start()
        ad = DialogAdapter()
        meta_warnings = 0
        for i, (sp, text) in enumerate(turns):
            eng.on_event(ad.adapt(text, session_id=name, turn_number=i+1))
            if i >= 1 and eng._meta_consumer and eng._trace_v3:
                advice = eng._meta_consumer.consume(eng._trace_v3, i+1)
                meta_warnings += len(advice.get("warnings", []))

        report.record("scenario_done", {"turns": len(turns), "warnings": meta_warnings}, name)
        print(f"  [{name}]: turns={len(turns)} warnings={meta_warnings}")

    report.finish()
    print(f"  Saved: data/monitor/{report.session_id}.jsonl")


if __name__ == "__main__":
    run_reflection_bench()
