"""AnomalyInjector — tests MetaConsumer by injecting known failures.

4 patterns matched to 4 scenarios:
  1. consecutive_rejects → contradicting info loop
  2. no_observe → direct answer without context
  3. low_confidence → ambiguous/unanswerable questions
  4. overheat → rapid topic switching
"""
import sys, os
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
from core.agent.v4.cognitive.monitor_report import MonitorReport
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter


PROVIDER = {
    'api_key': 'lm-studio',
    'base_url': 'http://127.0.0.1:1234/v1',
    'model': 'nvidia/nemotron-3-nano-4b',
}


def test_pattern(engine, ad, scenario_id, turns, expected_pattern):
    """Run a scenario and check if the expected MetaConsumer pattern triggered."""
    report = MonitorReport(f'anomaly_{scenario_id}')
    for i, (speaker, text) in enumerate(turns):
        engine.on_event(ad.adapt(text, scenario_id, i + 1))

    # Check MetaConsumer
    t = engine._trace_v3
    m = t.meta_analyze()
    mc = engine._meta_consumer
    advice = mc.consume(t, len(turns)) if mc else {}
    warnings = advice.get('warnings', [])
    triggered = expected_pattern in str(warnings) if warnings else False

    info = report.collect(engine)
    dist = m["reason_distribution"]
    report.record("result", {
        "pattern": expected_pattern,
        "triggered": triggered,
        "warnings": warnings,
        "transitions": m["total_transitions"],
        "types": sorted(dist.keys()),
        "confidence": m["avg_confidence"],
    })
    report.finish()

    status = "✅" if triggered else "❌"
    print(f"  [{scenario_id}] {expected_pattern}: {status}")
    print(f"    warnings={warnings[:2]} trans={m['total_transitions']} conf={m['avg_confidence']:.2f}")
    return triggered


def run_anomaly_tests():
    print("Anomaly Injection — MetaConsumer Validation")
    print("=" * 50)

    prov = OpenAIProvider('lmstudio', PROVIDER)
    eng = CognitiveRuntimeEngine(llm_provider=prov)
    eng.start()
    ad = DialogAdapter()
    passed = 0

    # ── P1: Consecutive Rejects (contradicting info loop) ──
    p1 = test_pattern(eng, ad, "p1_reject", [
        ("USER", "Is DialogMesh using BFS or DFS for context compilation?"),
        ("USER", "No, the design doc explicitly says water-wave, not BFS. You're wrong."),
        ("USER", "You're still wrong — re-read the design and try again."),
        ("USER", "Still incorrect. One more time — what algorithm does it use?"),
    ], "REJECT")
    if p1: passed += 1

    # ── P3: Low Confidence (ambiguous questions) ──
    p3 = test_pattern(eng, ad, "p3_lowconf", [
        ("USER", "What is the meaning of DialogMesh?"),
        ("USER", "No, I mean the philosophical meaning, not the technical one."),
        ("USER", "You seem unsure. What is the answer?"),
        ("USER", "Is there even a correct answer to this?"),
        ("USER", "I don't think you know. Are you just guessing?"),
        ("USER", "Last try — what is the meaning?"),
    ], "confidence")
    if p3: passed += 1

    # ── P4: Overheat / Topic Switch ──
    p4 = test_pattern(eng, ad, "p4_overheat", [
        ("USER", "Architecture overview."),
        ("USER", "Now about profile system."),
        ("USER", "Switch to extraction blueprint."),
        ("USER", "Actually, back to architecture."),
        ("USER", "No wait — discourse tree design."),
        ("USER", "Change topic — BGE encoder internals."),
    ], "topic_switch")
    if p4: passed += 1

    print(f"\nResult: {passed}/3 patterns triggered")
    print(f"Monitor: data/monitor/anomaly_*.jsonl")


if __name__ == "__main__":
    run_anomaly_tests()
