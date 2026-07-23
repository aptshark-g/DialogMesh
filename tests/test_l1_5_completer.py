"""L1.5 Completer Tests — JSON-driven, tests syntax path + LLM fallback."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l1_5_completer import CollaborativeCompleter, CompletionResult, CompletionCandidate


def load_tests():
    return json.loads(open("tests/test_data_l1_5_completer.json", encoding='utf-8').read())["tests"]


def run_test(t: dict):
    """Run one test case from JSON without LLM."""
    completer = CollaborativeCompleter()  # No LLM — syntax-only path
    result = completer.complete(
        text=t["text"],
        modifier_context=t.get("modifier_context", ""),
        entity_clusters=t.get("entity_clusters", {}),
    )
    
    tid = t["id"]
    issues = []
    
    # Check completion
    if result.ambiguous and not t.get("expected_ambiguous"):
        issues.append(f"unexpected ambiguity: {result.reasoning_trace}")
    
    if result.candidates:
        best = result.candidates[0]
        expected_cluster = t.get("expected_best_cluster")
        if expected_cluster and best.cluster_id != expected_cluster:
            issues.append(f"best_cluster: {best.cluster_id} (expected {expected_cluster})")
    
    if not result.candidates and t.get("expected_best_cluster") is not None:
        issues.append("no candidates but expected_best_cluster is set")
    
    status = "✅" if not issues else "❌"
    print(f"  {status} {tid:30s} | {' | '.join(issues) if issues else 'ok'}")
    print(f"     completed: {result.completed_text[:60]}")
    print(f"     candidates: {[(c.cluster_id, f'{c.confidence:.2f}') for c in result.candidates[:3]]}")
    print(f"     consensus={result.consensus} ambiguous={result.ambiguous} trace={result.reasoning_trace[:80]}")
    return len(issues) == 0


def test_json_structure():
    tests = load_tests()
    for t in tests:
        assert "id" in t and "text" in t, f"Missing required fields in {t}"
    print(f"✅ {len(tests)} JSON test cases loaded")


if __name__ == "__main__":
    test_json_structure()
    tests = load_tests()
    passed = 0
    for t in tests:
        if run_test(t):
            passed += 1
    print(f"\n🎉 L1.5 Completer: {passed}/{len(tests)} passed")
