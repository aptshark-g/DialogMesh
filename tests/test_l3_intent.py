"""L3 Pragmatic Intent Tests — multi-perspective voting, JSON-driven."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l3_intent import MultiPerspectiveValidator, Vote


def test_consensus():
    v = MultiPerspectiveValidator()
    data = json.loads(open("tests/test_data_l3_intent.json", encoding='utf-8').read())
    passed = 0
    for s in data["scenarios"]:
        result = v.validate(
            intent_hypothesis=s["hypothesis"],
            belief_7d=s["belief_7d"],
            discourse_topics=s.get("discourse_topics"),
            profile_traits=s.get("profile_traits"),
            pcr_zone=s.get("pcr_zone", "MIXED"),
            entity_relations=s.get("entity_relations"),
        )
        checks = s["checks"]
        issues = []
        if checks.get("consensus") != result.consensus:
            issues.append(f"consensus={result.consensus} != {checks['consensus']}")
        if "accepts_min" in checks:
            accepts = sum(1 for v in result.votes if v.vote == Vote.ACCEPT)
            if accepts < checks["accepts_min"]:
                issues.append(f"accepts={accepts} < {checks['accepts_min']}")
        if "rejects_max" in checks:
            rejects = sum(1 for v in result.votes if v.vote == Vote.REJECT)
            if rejects > checks["rejects_max"]:
                issues.append(f"rejects={rejects} > {checks['rejects_max']}")
        if "behavior_type" in checks:
            if result.behavior_type != checks["behavior_type"]:
                issues.append(f"behavior_type={result.behavior_type} != {checks['behavior_type']}")

        status = "✅" if not issues else "❌"
        votes_summary = [(v.source, v.vote.value) for v in result.votes]
        print(f"  {status} {s['id']}: intent={result.intent} type={result.behavior_type} conf={result.confidence:.2f} consensus={result.consensus}")
        print(f"     votes: {votes_summary}")
        if issues:
            for iss in issues:
                print(f"     ❌ {iss}")
        if not issues:
            passed += 1

    assert passed == len(data["scenarios"]), f"{passed}/{len(data['scenarios'])}"


if __name__ == "__main__":
    test_consensus()
    print("\n🎉 L3 Intent: all tests passed")
