"""ReflectionAdapter — tests DialogMesh epistemic agency with ReflectionBench scenarios.

ReflectionBench (ICML 2025) measures "epistemic agency": can the model
detect its own errors, reflect, correct, and learn from mistakes.

DialogMesh equivalents:
  - detect errors      → MetaConsumer detects unhealthy trace patterns
  - reflect            → ReasoningPolicy changes perspective/mode/depth
  - correct            → next turn's response quality improves
  - learn              → MistakeMemory stores avoidance rules
  - cross-session       → MindRelation persists learned patterns
"""
import sys, os, time, json
sys.path.insert(0, '.')

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.mock_provider import MockProvider
from core.agent.v4.event_ir import DialogAdapter


SCENARIOS = {
    "math_error": {
        "turns": [
            ("USER", "How many objects are in the SemanticObject store?"),
            ("USER", "Are you sure? That number seems too low — there should be ~10,000."),
            ("USER", "Can you recount and verify?"),
            ("USER", "What was the correct count?"),
        ],
        "expected": {"detect": True, "correct": True},
    },
    "hallucination": {
        "turns": [
            ("USER", "Does DialogMesh have a QuantumReasoningEngine module?"),
            ("USER", "I don't see it anywhere in the codebase. Why did you mention it?"),
            ("USER", "What modules actually exist in the codebase?"),
        ],
        "expected": {"detect": True, "correct": True, "retract": True},
    },
    "oversimplify": {
        "turns": [
            ("USER", "How does the runtime pipeline work?"),
            ("USER", "That's too simplified — explain with actual module names."),
            ("USER", "Still not enough detail. What are the specific compiler modules?"),
        ],
        "expected": {"detect": True, "deepen": True},
    },
    "wrong_tool": {
        "turns": [
            ("USER", "Extract relations from this design doc using regex."),
            ("USER", "No — use the JiebaRelationParser, not regex."),
            ("USER", "Now use the BGE semantic encoder for cross-language matching."),
        ],
        "expected": {"detect": True, "redirect": True},
    },
}


def run_scenario(engine, scenario_name, scenario):
    ad = DialogAdapter()
    results = {"scenario": scenario_name, "turns": [], "meta_warnings": 0, "corrections": 0}

    for i, (speaker, text) in enumerate(scenario["turns"]):
        if speaker == "USER":
            response = engine.on_event(ad.adapt(text, session_id=scenario_name, turn_number=i+1))
            results["turns"].append({"turn": i+1, "text": text[:80], "resp_len": len(response) if response else 0})

        if i >= 1 and engine._meta_consumer and engine._trace_v3:
            advice = engine._meta_consumer.consume(engine._trace_v3, i+1)
            warnings = advice.get("warnings", [])
            results["meta_warnings"] += len(warnings)
            if warnings:
                results["corrections"] += 1

    if engine._mind:
        results["mind_relations"] = engine._mind.stats()["active_relations"]
    if engine._mind_mistakes:
        results["mistake_rules"] = engine._mind_mistakes.stats()["rules"]

    return results


def run_reflection_bench():
    print("ReflectionBench — Epistemic Agency Test")
    print("=" * 40)

    all_results = []
    for name, scenario in SCENARIOS.items():
        prov = MockProvider("mock", {"response_text": "[Mock] DialogMesh v4 has modules including SemanticObject, RelationSubstrate, Observer, Workspace..."})
        eng = CognitiveRuntimeEngine(llm_provider=prov)
        eng.start()
        print(f"\n[{name}] {len(scenario['turns'])} turns:")
        result = run_scenario(eng, name, scenario)
        all_results.append(result)

        expected = scenario.get("expected", {})
        detected = result["meta_warnings"] > 0
        print(f"  meta_warnings={result['meta_warnings']} corrections={result['corrections']}")
        if expected.get("detect"):
            print(f"  detect={'✅' if detected else '❌'}")
        if expected.get("correct"):
            print(f"  correct={'✅' if result['corrections'] >= 1 else '❌'}")
        if result.get("mind_relations", 0) > 0:
            print(f"  mind_relations: {result['mind_relations']} active")
        if result.get("mistake_rules", 0) > 0:
            print(f"  mistakes: {result['mistake_rules']} rules")

    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/reflection_bench.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    total = sum(r["meta_warnings"] for r in all_results)
    print(f"\nTotal: {total} warnings across {len(SCENARIOS)} scenarios")
    print(f"Saved: data/monitor/reflection_bench.json")


if __name__ == "__main__":
    run_reflection_bench()
