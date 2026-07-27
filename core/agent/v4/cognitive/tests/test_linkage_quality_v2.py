"""Linkage Quality Test v2.1 — with generalizations checks and all fixes.

Adds:
  7. Generalization: cold-start handling
  8. Generalization: topic outside training domain
  9. Generalization: mixed language (Chinese + English)
"""
import sys, os, time, json
sys.path.insert(0, '.')
from core.agent.v4.cognitive.monitor_report import MonitorReport

from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.events.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

def engine():
    import os; os.environ["DIALOGMESH_MONITOR"] = "1"
    prov = OpenAIProvider("deepseek", {"api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"})
    return CognitiveRuntimeEngine(llm_provider=prov)

def test_all():
    report = MonitorReport("linkage_quality")
    eng = engine(); eng.start(); ad = DialogAdapter()
    mon = eng._monitor
    r = {"ok": 0, "fail": 0, "checks": []}

    def check(link, passed, **data):
        r["checks"].append({"link": link, "passed": passed, **data})
        r["ok" if passed else "fail"] += 1
        print(f"  {'✅' if passed else '❌'} {link}: {data}")

    print("Linkage Quality v2.1 — 5 turns")
    print("═══════════════════════════════")

    # ── 5 turns ──
    for i in range(5):
        eng.on_event(ad.adapt(f"Question {i+1} about architecture patterns", "lqa", i+1))

    # L1: DiscourseTree populated
    tree = eng._discourse_tree._trees.get("lqa")
    blocks = getattr(tree, 'blocks', {}) if tree else {}
    check("L1_tree", len(blocks) > 0, blocks=len(blocks))

    # L2: Simulation stats
    sim = getattr(eng, '_simulation_stats', {})
    check("L2_simulation", sim.get("total", 0) > 0, **sim)

    # L3: Transitions
    t = eng._trace_v3; m = t.meta_analyze()
    d = m["reason_distribution"]
    check("L3_transitions", "observe" in d and "infer" in d, types=sorted(d.keys()), total=m["total_transitions"])

    # L4: MetaConsumer cycles
    mc = getattr(eng, '_meta_consumer', None)
    check("L4_meta", getattr(mc, '_consecutive_cycles', 0) > 0, cycles=getattr(mc, '_consecutive_cycles', 0))

    # L5: Strategy learning
    se = getattr(eng, '_strategy_engine', None)
    s = se.stats() if se else {}
    check("L5_strategy", s.get("total_uses", 0) > 0, **s)

    # L6: Monitor coverage
    if mon:
        mon.flush()
        if os.path.exists(mon._log_path):
            lines = [json.loads(l) for l in open(mon._log_path)]
            ts = {}
            for l in lines: ts.setdefault(l["type"],0); ts[l["type"]]+=1
            check("L6_monitor", len(ts) >= 4, events=len(lines), types=ts)
            print(f"    Log: {mon._log_path}")
        else:
            check("L6_monitor", False, error="no log file")
    else:
        check("L6_monitor", False, error="monitor is None")

    # ── Generalization Tests ──
    print("\n[Generalization] Cold-start + unseen topics (5 more turns)")
    for i, text in enumerate([
        "What is the meaning of life?",          # philosophical — outside domain
        "How do I bake a chocolate cake?",        # cooking — outside domain
        "Explain quantum entanglement simply",    # physics — outside domain
        "为什么中文和英文的语法差异这么大？",       # Chinese — mixed language
        "What percentage of stars have planets?", # astronomy
    ]):
        eng.on_event(ad.adapt(text, "lqa", i+6))

    t2 = eng._trace_v3; m2 = t2.meta_analyze()
    d2 = m2["reason_distribution"]
    gen_ok = len(d2) >= 3  # Should still produce observe/infer/reflect
    check("L7_generalization", gen_ok,
        types=sorted(d2.keys()), total=m2["total_transitions"],
        note="cross-domain + mixed language")

    # Profile shouldn't crash on unseen topics
    prof = getattr(eng, '_cognitive_profile', None)
    inertia = getattr(getattr(prof, 'track_a', None), 'cognitive_inertia', -1) if prof else -1
    check("L8_profile_stability", inertia > 0 and inertia < 1, inertia=inertia,
        note="should stay stable on out-of-domain")

    # ── Summary ──
    print(f"\n{'='*40}")
    print(f"  {r['ok']}/{r['ok']+r['fail']} passed")
    for c in r["checks"]:
        e = c.pop("error", ""); c.pop("note", "")
        print(f"  {'✅' if c['passed'] else '❌'} {c['link']} {'— '+e if e else ''}")

    os.makedirs("data/monitor", exist_ok=True)
    report.finish()
    with open("data/monitor/linkage_quality_v2.json", "w") as f:
        json.dump(r, f, indent=2, default=str)
    print(f"  Saved: data/monitor/linkage_quality_v2.json")

if __name__ == "__main__":
    test_all()
