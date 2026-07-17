"""SNIPS/CLINC150 benchmark: evaluate PerspectivePlanner strategy accuracy.

SNIPS has 7 intent classes that map to our perspective strategies:
  GetWeather, SearchCreativeWork → COMPANION → evolution
  BookRestaurant, PlayMusic          → TOOL       → engineering  
  AddToPlaylist, RateBook            → ADVISOR    → architecture
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/../../../..")
from typing import Dict, List


# SNIPS-like test cases for perspective mapping
SNIPS_TEST_CASES = [
    # (text, expected_strategy, expected_expectation)
    # TOOL → engineering
    ("Book a table for two at the Italian restaurant", "engineering", "TOOL"),
    ("Play some jazz music on Spotify", "engineering", "TOOL"),
    ("Add this song to my evening playlist", "engineering", "TOOL"),
    ("Set an alarm for 7am tomorrow", "engineering", "TOOL"),
    ("Send a message to John about the meeting", "engineering", "TOOL"),

    # ADVISOR → architecture
    ("Rate this book 5 stars", "architecture", "ADVISOR"),
    ("What's the best restaurant near me?", "architecture", "ADVISOR"),
    ("Is this movie appropriate for children?", "architecture", "ADVISOR"),
    ("Recommend me a good sci-fi book", "architecture", "ADVISOR"),
    ("How long should I cook pasta for?", "architecture", "ADVISOR"),

    # COMPANION → evolution
    ("What's the weather like today?", "evolution", "COMPANION"),
    ("Tell me something interesting about space", "evolution", "COMPANION"),
    ("Who directed the movie Inception?", "evolution", "COMPANION"),
    ("What's the latest news about AI?", "evolution", "COMPANION"),
    ("How do I feel more productive?", "evolution", "COMPANION"),

    # Our domain-specific tests
    ("Explain the runtime architecture", "architecture", "ADVISOR"),
    ("Why was this design decision made?", "evolution", "ADVISOR"),
    ("Show me the code for the parser", "engineering", "TOOL"),
    ("How does the pipeline execute step by step?", "execution", "TOOL"),
    ("What modules depend on ContextCompiler?", "architecture", "ADVISOR"),
]


class SNIPSBenchmark:
    """Evaluate PerspectivePlanner strategy selection accuracy."""

    def __init__(self):
        from core.agent.v4.compiler.perspective_planner import PerspectivePlanner
        self.planner = PerspectivePlanner()

    def evaluate(self) -> Dict:
        results = {"correct": 0, "wrong": 0, "errors": [], "total": len(SNIPS_TEST_CASES)}
        for text, expected_strat, _ in SNIPS_TEST_CASES:
            try:
                p = self.planner.plan(text)
                if p.strategy == expected_strat:
                    results["correct"] += 1
                else:
                    results["wrong"] += 1
                    results["errors"].append(
                        f"'{text[:40]}' → {p.strategy} (expected {expected_strat})"
                    )
            except Exception as e:
                results["wrong"] += 1
                results["errors"].append(f"'{text[:40]}' → ERROR: {e}")

        results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
        return results

    def print_report(self, results: Dict):
        print("\n════════════════════════════════════════════")
        print("SNIPS Perspective Selection Benchmark")
        print("════════════════════════════════════════════")
        print(f"Total: {results['total']} | Correct: {results['correct']} | Wrong: {results['wrong']}")
        print(f"Accuracy: {results['accuracy']:.1%}")
        print()
        if results["errors"]:
            print("Errors:")
            for err in results["errors"][:10]:
                print(f"  {err}")
        print()
        if results["accuracy"] > 0.8:
            print("✅ ACCEPTABLE (>80%)")
        elif results["accuracy"] > 0.6:
            print("⚠️  MARGINAL (60-80%)")
        else:
            print("❌ FAILED (<60%)")


if __name__ == "__main__":
    b = SNIPSBenchmark()
    r = b.evaluate()
    b.print_report(r)
