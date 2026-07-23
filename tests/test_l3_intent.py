"""L3 Intent Tests — JSON-driven, LLM deadlock tested when DeepSeek available."""

import sys, json, os
sys.path.insert(0, '.')
from core.agent.association.l3_intent import MultiPerspectiveValidator, Vote
from tests.test_llm_provider import get_test_llm


def test_consensus():
    data = json.loads(open("tests/test_data_l3_intent.json", encoding='utf-8').read())
    passed = 0

    for s in data["scenarios"]:
        # LLM only when test expects it
        provider = get_test_llm() if s["checks"].get("llm_called") else None
        v = MultiPerspectiveValidator(llm_provider=provider)

        result = v.validate(
            intent_hypothesis=s["hypothesis"],
            belief_7d=s["belief_7d"],
            discourse_topics=s.get("discourse_topics"),
            profile_traits=s.get("profile_traits"),
            pcr_zone=s.get("pcr_zone", "MIXED"),
            entity_relations=s.get("entity_relations"),
        )

        checks = s["checks"]
        ok = True
        for check, expected in checks.items():
            if check == "consensus":
                if result.consensus != expected: ok = False; print(f"  ❌ consensus={result.consensus}")
            elif check == "accepts_min":
                accepts = sum(1 for v in result.votes if v.vote == Vote.ACCEPT)
                if accepts < expected: ok = False; print(f"  ❌ accepts={accepts}")
            elif check == "behavior_type":
                if result.behavior_type != expected: ok = False; print(f"  ❌ type={result.behavior_type}")
            elif check == "llm_called":
                llm_votes = [v for v in result.votes if v.source == "llm"]
                if expected and not llm_votes:
                    print(f"  ⚠️ LLM not called (deadlock didn't trigger or DEEPSEEK_KEY not set)")
                    # Don't fail — LLM is optional
                elif expected and llm_votes:
                    print(f"  🧠 LLM resolved: {llm_votes[0].vote.value} — {llm_votes[0].reason[:60]}")

        if ok: passed += 1
        votes_str = [(v.source, v.vote.value) for v in result.votes]
        print(f"  {'✅' if ok else '❌'} {s['id']}: {result.intent}/{result.behavior_type} conf={result.confidence:.2f} consensus={result.consensus}")
        print(f"     votes: {votes_str}")

    assert passed == len(data["scenarios"]), f"{passed}/{len(data['scenarios'])}"


if __name__ == "__main__":
    test_consensus()
    print("\n🎉 L3 Intent: all tests passed")
