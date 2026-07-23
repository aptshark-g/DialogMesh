"""AnomalyInjector — tests MetaConsumer by injecting known failures.

3 patterns: REJECT, WEAKEN (low confidence), topic switch.
"""
import sys, os
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
from core.agent.v4.cognitive.monitor_report import MonitorReport
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.events.event_ir import DialogAdapter

PROVIDER = {
    'api_key': 'lm-studio', 'base_url': 'http://127.0.0.1:1234/v1',
    'model': 'nvidia/nemotron-3-nano-4b',
}

def test_pattern(engine, ad, sid, turns, expected_type):
    report = MonitorReport(f'anomaly_{sid}')
    for i, (sp, text) in enumerate(turns):
        engine.on_event(ad.adapt(text, sid, i+1))
    t = engine._trace_v3; m = t.meta_analyze()
    dist = m["reason_distribution"]
    triggered = dist.get(expected_type, 0) > 0
    mc = engine._meta_consumer
    advice = mc.consume(t, len(turns)) if mc else {}
    warnings = advice.get('warnings', [])
    info = report.collect(engine)
    report.record("result", {"type": expected_type, "triggered": triggered, "warnings": warnings})
    report.finish()
    status = "✅" if triggered else "❌"
    print(f"  [{sid}] {expected_type}: {status} trans={m['total_transitions']} conf={m['avg_confidence']:.2f} warn={len(warnings)}")
    return triggered

def run():
    print("Anomaly Injection — MetaConsumer Validation")
    print("=" * 50)
    prov = OpenAIProvider('lmstudio', PROVIDER)
    eng = CognitiveRuntimeEngine(llm_provider=prov); eng.start()
    ad = DialogAdapter()
    passed = 0

    p1 = test_pattern(eng, ad, "p1_reject", [
        ("USER", "Is DialogMesh using BFS or DFS?"),
        ("USER", "No, design says water-wave. You're wrong."),
        ("USER", "Still wrong — re-read and try again."),
        ("USER", "Still incorrect. One more time."),
    ], "reject")
    if p1: passed += 1

    p3 = test_pattern(eng, ad, "p3_lowconf", [
        ("USER", "What is the meaning of DialogMesh?"),
        ("USER", "No, philosophical meaning, not technical."),
        ("USER", "You seem unsure. What is the answer?"),
        ("USER", "Is there even a correct answer?"),
        ("USER", "Are you just guessing?"),
        ("USER", "Last try — what is the meaning?"),
    ], "weaken")
    if p3: passed += 1

    p4 = test_pattern(eng, ad, "p4_switch", [
        ("USER", "Architecture overview."),
        ("USER", "Now about profile system."),
        ("USER", "Switch to extraction blueprint."),
        ("USER", "Back to architecture."),
        ("USER", "No — discourse tree design."),
        ("USER", "BGE encoder internals."),
    ], "weaken")
    if p4: passed += 1

    print(f"\nResult: {passed}/3 patterns triggered")
    print(f"Monitor: data/monitor/anomaly_*.jsonl")

if __name__ == "__main__":
    run()
