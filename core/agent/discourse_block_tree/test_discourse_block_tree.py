# -*- coding: utf-8 -*-
"""DiscourseBlockTree - comprehensive tests (rebuilt 2026-08-03).

The original file was GBK-damaged (all Chinese replaced by '?' and it pointed
at a deleted worktree path). Rebuilt with unicode escapes + repo-relative
imports, aligned to the model-first SyntacticDecomposer (R-decision).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.discourse_block_tree import (
    DiscourseBlockTreeManager, EDU, DiscourseBlock,
    HeaderInjector, SyntacticDecomposer, MacroMicroQuantizer,
    Segmenter, GranularityRegulator, SummaryEngine,
    ContextBuilder, Indexer,
)


def test_edu_basics():
    e = EDU(index=0, raw_text="\u7528Python\u5206\u6790\u6570\u636e")
    assert e.index == 0
    assert "Python" in e.raw_text
    d = e.to_dict()
    assert d["index"] == 0
    print("  PASS: test_edu_basics")


def test_cohesion_score():
    from core.agent.discourse_block_tree.models import CohesionScore
    c = CohesionScore(left_index=0, right_index=1, macro_score=0.8, micro_score=0.7)
    assert c.total_score == 0.6 * 0.8 + 0.4 * 0.7
    assert c.decision == "continue"
    c2 = CohesionScore(left_index=1, right_index=2, macro_score=0.2, micro_score=0.2)
    assert c2.decision == "fork"
    c3 = CohesionScore(left_index=2, right_index=3, macro_score=0.5, micro_score=0.5)
    assert c3.decision == "gray_zone"
    print("  PASS: test_cohesion_score")


def test_progressive_summary():
    from core.agent.discourse_block_tree.models import ProgressiveSummary
    ps = ProgressiveSummary()
    ps.v1_raw = "\u7528Python\u5206\u6790\u6570\u636e"
    assert ps.version == 1
    assert ps.get_best() == "\u7528Python\u5206\u6790\u6570\u636e"
    ps.upgrade_v2([], "write")
    assert ps.version == 2
    assert "write" in ps.v2_entity
    ps.upgrade_v3(["step1", "step2"])
    assert ps.version == 3
    assert "step1" in ps.v3_evolution
    ps.upgrade_v4("some compressed text")
    assert ps.version == 4
    assert ps.v4_compressed == "some compressed text"
    print("  PASS: test_progressive_summary")


def test_header_injector():
    hi = HeaderInjector()
    # Demonstrative pronoun resolves to recent entity (rebuilt constants)
    hi.cache.push([__import__("core.agent.discourse_block_tree.models", fromlist=["DiscourseEntity"]).DiscourseEntity(
        text="DomainSelector", etype="context", confidence=0.9)])
    result = hi.inject("\u8fd9\u4e2a\u6a21\u5757\u5f88\u91cd\u8981")
    assert "DomainSelector" in result
    # Entity extraction (structural)
    entities = hi.extract_entities("scan 0x1000")
    assert len(entities) > 0
    # Negation detection (rebuilt markers)
    p = hi.detect_pragmatics("\u8fd9\u4e2a\u4e0d\u884c")
    assert p["negation"]
    print("  PASS: test_header_injector")


def test_syntactic_decomposer():
    sd = SyntacticDecomposer()
    edus = sd.decompose("\u7528Python\u5206\u6790\u6570\u636e")
    assert len(edus) >= 1
    edus2 = sd.decompose("\u5148\u5b9a\u4f4d\u5ef6\u8fdf\uff0c\u7136\u540e\u4fee\u590d")
    assert len(edus2) >= 2
    print("  PASS: test_syntactic_decomposer")


def test_macro_micro_quantizer():
    q = MacroMicroQuantizer()
    e1 = EDU(index=0, raw_text="\u7528Python\u5206\u6790", predicate="\u5206\u6790", obj="Python", entities=["Python"])
    e2 = EDU(index=1, raw_text="\u8bfbCSV\u6587\u4ef6", predicate="\u8bfb", obj="CSV", entities=["CSV"])
    score = q.score_pair(e1, e2)
    assert score.left_index == 0
    assert score.right_index == 1
    print("  PASS: test_macro_micro_quantizer")


def test_manager_ingest_and_context():
    m = DiscourseBlockTreeManager()
    bids = m.ingest_turn(1, "\u6709\u8bb0\u5fc6\u5417")
    assert bids
    ctx = m.build_context()
    assert len(ctx) > 0
    print("  PASS: test_manager_ingest_and_context")


def test_v3_field_consistency():
    from core.agent.discourse_block_tree.models import ProgressiveSummary
    from core.agent.discourse_block_tree.summary_engine import SummaryEngine
    ps = ProgressiveSummary()
    block = type("B", (), {
        "summary": ps,
        "atomic_units": [],
        "primary_intent": "fix",
        "name": "topic",
        "entities": [],
    })()
    SummaryEngine()._v3_upgrade(block, turn=1)
    assert ps.version == 3
    assert ps.v3_evolution
    assert ps.get_best() == ps.v3_evolution
    print("  PASS: test_v3_field_consistency")


TESTS = [
    test_edu_basics,
    test_cohesion_score,
    test_progressive_summary,
    test_header_injector,
    test_syntactic_decomposer,
    test_macro_micro_quantizer,
    test_manager_ingest_and_context,
    test_v3_field_consistency,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(TESTS)} total")
