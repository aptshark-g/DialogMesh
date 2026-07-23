"""L2.5 Belief Accumulator Tests — JSON-driven."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l2_5_belief import BeliefAccumulator, Evidence, BayesianUpdater


def test_bayesian():
    up = BayesianUpdater()
    priors = {"诊断": 0.25, "修复": 0.25, "探索": 0.25, "吐槽": 0.25}
    ev = Evidence("e1", "延迟", "causes", 0.85, 1)
    post = up.update(priors, ev)
    assert post["诊断"] > post["吐槽"], "causal evidence should boost 诊断"
    print(f"✅ Bayesian: 诊断 {priors['诊断']:.2f}→{post['诊断']:.2f}")

def test_entropy():
    up = BayesianUpdater()
    assert up.entropy({"诊断": 0.9, "修复": 0.05, "探索": 0.05}) < 0.5
    assert up.entropy({"诊断": 0.34, "修复": 0.33, "探索": 0.33}) > 0.7
    print("✅ Entropy")

def test_scenarios():
    data = json.loads(open("tests/test_data_l2_5_belief.json", encoding='utf-8').read())
    passed = 0
    for s in data["scenarios"]:
        acc = BeliefAccumulator()
        for t in s["turns"]:
            ev = Evidence(f"{s['id']}_{t['evidence']['turn']}", t["evidence"]["entity_name"],
                         t["evidence"]["relation_type"], t["evidence"]["confidence"],
                         t["evidence"]["turn"])
            acc.ingest(ev)
        ok = True
        for check, expected in s["checks"].items():
            if check == "locked_after_turns":
                if acc.locked_intent is None: ok = False; print(f"  ❌ not locked")
            elif check == "locked_intent":
                if acc.locked_intent != expected: ok = False; print(f"  ❌ locked={acc.locked_intent} != {expected}")
            elif check == "trace_count":
                if len(acc.trace) != expected: ok = False; print(f"  ❌ trace {len(acc.trace)} != {expected}")
            elif check == "needs_llm_after_turns":
                if not acc.needs_llm(): ok = False; print(f"  ❌ needs_llm=false")
            elif check == "not_locked":
                if acc.locked_intent: ok = False; print(f"  ❌ locked={acc.locked_intent}")
        if ok: passed += 1
        print(f"  {'✅' if ok else '❌'} {s['id']}: locked={acc.locked_intent} entropy={acc.bayesian.entropy(acc.priors):.2f}")
    assert passed == len(data["scenarios"]), f"{passed}/{len(data['scenarios'])}"

if __name__ == "__main__":
    test_bayesian()
    test_entropy()
    test_scenarios()
    print("\n🎉 L2.5 Belief Accumulator: all tests passed")
