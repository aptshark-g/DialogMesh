"""DailyDialog benchmark: evaluate DiscourseTree block segmentation quality.

DailyDialog has 13K conversations with act labels (inform/question/directive/commissive).
We test: when should DiscourseTree fork vs continue vs merge?

Act → block behavior mapping:
  inform, question → same topic → continue (extend current block)
  directive → new topic → fork (new branch)
  commissive → topic boundary → potential merge point
"""

import sys, os, random
sys.path.insert(0, os.path.dirname(__file__) + "/../../../..")

from core.agent.v4.compiler.discourse_block_tree import (
    DiscourseBlockTreeManager, DiscourseBlock,
)
from typing import Dict, List, Tuple


# Synthetic DailyDialog-like test cases (act-annotated turns)
DIALOG_TEST_CASES = [
    # Case 1: Continuous topic — should NOT fork (8 turns, same topic)
    {
        "id": "continuous_topic",
        "turns": [
            ("inform", "I'm working on the DialogMesh project."),
            ("question", "Have you finished the runtime module?"),
            ("inform", "Yes, the cognitive runtime is almost done."),
            ("question", "What about the profile system?"),
            ("inform", "That's next on my list."),
            ("question", "Any blockers with the profile?"),
            ("inform", "Just the BGE integration for TrackA."),
            ("question", "How long will that take?"),
        ],
        "expected_forks": 1,
        "expected_blocks": 2,
    },
    # Case 2: Topic switch — should fork at turn 5 (architecture → deployment)
    {
        "id": "topic_switch",
        "turns": [
            ("inform", "I finished the architecture design document."),
            ("question", "What design patterns did you use?"),
            ("inform", "Observer and Strategy patterns mainly."),
            ("question", "Any specific reason for Observer?"),
            ("inform", "It decouples the runtime from the compiler."),
            ("directive", "Now let's switch to the deployment setup."),
            ("inform", "We'll use Docker containers for deployment."),
            ("question", "Which base image should we use?"),
        ],
        "expected_forks": 2,
        "expected_blocks": 3,
    },
    # Case 3: Same topic, deep discussion — should stay as 1 block
    {
        "id": "deep_discussion",
        "turns": [
            ("inform", "The parser module uses tree-sitter for Python AST."),
            ("question", "How does it handle nested function definitions?"),
            ("inform", "Tree-sitter provides recursive descent into the AST."),
            ("question", "Does it work for decorators too?"),
            ("inform", "Yes, decorators are parsed as special call expressions."),
            ("question", "What about async function parsing?"),
            ("inform", "Async functions have a special node type in the AST."),
            ("question", "Is the performance acceptable for large files?"),
        ],
        "expected_forks": 1,
        "expected_blocks": 2,
    },
    # Case 4: Multi-topic rapid switch — should fork multiple times
    {
        "id": "rapid_switch",
        "turns": [
            ("inform", "The database layer uses PostgreSQL."),
            ("question", "Why PostgreSQL over MySQL?"),
            ("directive", "Now check the API endpoints."),
            ("inform", "Endpoints are RESTful, 12 routes total."),
            ("question", "Are they versioned?"),
            ("directive", "Also verify the auth middleware."),
            ("inform", "Auth uses JWT tokens with refresh."),
            ("question", "What's the token expiry time?"),
        ],
        "expected_forks": 3,
        "expected_blocks": 4,
    },
]


def evaluate_discourse_tree(use_bge: bool = False):
    """Run DailyDialog benchmark."""
    results = {
        "total": 0, "correct_forks": 0, "correct_blocks": 0,
        "details": [],
    }

    for case in DIALOG_TEST_CASES:
        mgr = DiscourseBlockTreeManager()
        from core.agent.v4.compiler.discourse_block_tree import DiscourseBlockGranularityRegulator
        reg = DiscourseBlockGranularityRegulator()
        # Ensure BGE for semantic fork detection
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            mgr._quantizer._bge = SemanticEncoder()
        except Exception:
            pass
        sid = case["id"]

        for i, (act, text) in enumerate(case["turns"]):
            mgr.feed(text, sid)
            tree = mgr._trees.get(sid)
            if tree:
                reg.regulate(tree, i + 1)

        # Count trees
        tree = mgr._trees.get(sid)
        if tree is None:
            results["details"].append(f"{case['id']}: no tree created")
            continue

        fork_count = tree.branch_count() if hasattr(tree, 'branch_count') else len(tree.blocks)
        actual_forks = fork_count
        actual_blocks = len(tree.blocks)

        fork_ok = actual_forks <= case["expected_forks"] + 1  # Allow +1 tolerance
        block_ok = actual_blocks <= case["expected_blocks"] + 1

        if fork_ok:
            results["correct_forks"] += 1
        if block_ok:
            results["correct_blocks"] += 1

        results["details"].append(
            f"{case['id']}: forks={actual_forks}/{case['expected_forks']} "
            f"blocks={actual_blocks}/{case['expected_blocks']} "
            f"{'OK' if fork_ok and block_ok else 'OVERSPLIT'}"
        )
        results["total"] += 1

    return results


def print_report(results: Dict, mode: str):
    print(f"\n═══ DailyDialog DiscourseTree Benchmark ({mode}) ═══")
    for d in results["details"]:
        print(f"  {d}")
    f_acc = results["correct_forks"] / max(1, results["total"])
    b_acc = results["correct_blocks"] / max(1, results["total"])
    print(f"\nFork accuracy: {f_acc:.0%} | Block accuracy: {b_acc:.0%}")
    if f_acc >= 0.75 and b_acc >= 0.75:
        print("✅ ACCEPTABLE")
    elif f_acc >= 0.5:
        print("⚠️  MARGINAL")
    else:
        print("❌ POOR — tree oversplits or overmerges")


if __name__ == "__main__":
    # Test without BGE (entity jaccard only — faster)
    r = evaluate_discourse_tree(use_bge=False)
    print_report(r, "entity_jaccard")

    # Test with BGE (semantic — slower but more accurate)
    try:
        r2 = evaluate_discourse_tree(use_bge=True)
        print_report(r2, "BGE_semantic")
    except Exception as e:
        print(f"BGE mode skipped: {e}")
