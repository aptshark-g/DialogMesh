"""DiscourseBlockTree - comprehensive tests"""
import sys, os
sys.path.insert(0, r"C:\\Users\\APTShark\\.codex\\worktrees\\bd48\\DialogMesh")

from core.agent.discourse_block_tree import (
    DiscourseBlockTreeManager, EDU, DiscourseBlock,
    HeaderInjector, SyntacticDecomposer, MacroMicroQuantizer,
    Segmenter, GranularityRegulator, SummaryEngine,
    ContextBuilder, Indexer,
)


def test_edu_basics():
    e = EDU(index=0, raw_text="???Python??")
    assert e.index == 0
    assert "Python" in e.raw_text
    d = e.to_dict()
    assert d["index"] == 0
    assert d["text"] == "???Python??"
    print("  PASS: test_edu_basics")


def test_cohesion_score():
    from core.agent.discourse_block_tree.models import CohesionScore
    c = CohesionScore(left_index=0, right_index=1, macro_score=0.8, micro_score=0.7)
    assert c.total_score == 0.6*0.8 + 0.4*0.7
    assert c.decision == "continue"
    c2 = CohesionScore(left_index=1, right_index=2, macro_score=0.2, micro_score=0.2)
    assert c2.decision == "fork"
    c3 = CohesionScore(left_index=2, right_index=3, macro_score=0.5, micro_score=0.5)
    assert c3.decision == "gray_zone"
    print("  PASS: test_cohesion_score")


def test_progressive_summary():
    from core.agent.discourse_block_tree.models import ProgressiveSummary
    ps = ProgressiveSummary()
    ps.v1_raw = "???Python??"
    assert ps.version == 1
    assert ps.get_best() == "???Python??"
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
    # ?????
    result = hi.inject("??????")
    assert "??" in result
    # ????
    entities = hi.extract_entities("scan 0x1000")
    assert len(entities) > 0
    # ????
    p = hi.detect_pragmatics("????????")
    assert p["negation"]
    print("  PASS: test_header_injector")


def test_syntactic_decomposer():
    sd = SyntacticDecomposer()
    edus = sd.decompose("???Python??")
    assert len(edus) >= 1
    # ???
    edus2 = sd.decompose("???Python?????????????????????")
    assert len(edus2) >= 2
    print("  PASS: test_syntactic_decomposer")


def test_macro_micro_quantizer():
    q = MacroMicroQuantizer()
    e1 = EDU(index=0, raw_text="???Python??", predicate="?", obj="Python??", entities=["Python"])
    e2 = EDU(index=1, raw_text="??CSV??", predicate="??", obj="CSV??", entities=["CSV"])
    score = q.score_pair(e1, e2)
    assert score.left_index == 0
    assert score.right_index == 1
    # ??? vs ???
    e3 = EDU(index=1, raw_text="??????????", predicate="???", obj="??", entities=["????"])
    score2 = q.score_pair(e1, e3)
    print(f"    macro={score.macro_score:.3f} micro={score.micro_score:.3f} total={score.total_score:.3f}")
    print(f"    cross macro={score2.macro_score:.3f} micro={score2.micro_score:.3f} total={score2.total_score:.3f}")
    print("  PASS: test_macro_micro_quantizer")


def test_segmenter():
    sd = SyntacticDecomposer()
    seg = Segmenter()
    text = "???Python???????????????????????????embedding???"
    edus = sd.decompose(text)
    blocks = seg.segment(edus)
    assert len(blocks) >= 1
    print(f"    {len(edus)} EDUs -> {len(blocks)} blocks")
    print("  PASS: test_segmenter")


def test_manager_basic():
    mgr = DiscourseBlockTreeManager()
    ids = mgr.ingest_turn(1, "???Python??")
    assert len(ids) >= 1
    assert mgr.current_block_id is not None
    ctx = mgr.build_context()
    assert len(ctx) > 0
    summary = mgr.get_tree_summary()
    assert summary["total_blocks"] >= 1
    assert summary["turn"] == 1
    print("  PASS: test_manager_basic")


def test_manager_multi_turn():
    mgr = DiscourseBlockTreeManager()
    ids1 = mgr.ingest_turn(1, "???Python?????????????????????")
    assert len(ids1) >= 1
    ids2 = mgr.ingest_turn(2, "??????embedding??")
    assert len(ids2) >= 1
    summary = mgr.get_tree_summary()
    assert summary["total_blocks"] >= 2
    ctx = mgr.build_context()
    assert len(ctx) > 0
    print(f"    turns=2, blocks={summary['total_blocks']}, context_len={len(ctx)}")
    print("  PASS: test_manager_multi_turn")


def test_context_builder():
    cb = ContextBuilder(max_tokens=1024)
    from core.agent.discourse_block_tree.models import DiscourseBlock, EDU
    b1 = DiscourseBlock(block_id="b1", name="Python??")
    b1.add_edu(EDU(index=0, raw_text="???Python??"))
    b2 = DiscourseBlock(block_id="b2", name="embedding??", parent_id="b1")
    b1.child_ids.append("b2")
    blocks = {"b1": b1, "b2": b2}
    ctx = cb.build(blocks, "b2")
    assert "????" in ctx
    print(f"    build context: {len(ctx)} chars")
    print("  PASS: test_context_builder")


def test_indexer():
    idx = Indexer()
    from core.agent.discourse_block_tree.models import DiscourseBlock, EDU
    b = DiscourseBlock(block_id="b1", name="test", primary_intent="write")
    b.add_edu(EDU(index=0, raw_text="???Python??", entities=["Python"]))
    idx.index_block(b)
    assert len(idx.find_by_intent("write")) > 0
    assert len(idx.find_by_reference("Python")) > 0
    print("  PASS: test_indexer")


def test_granularity_regulator():
    gr = GranularityRegulator()
    from core.agent.discourse_block_tree.models import DiscourseBlock
    blocks = {}
    for i in range(10):
        b = DiscourseBlock(block_id=f"b{i}", name=f"block{i}", parent_id="root")
        blocks[b.block_id] = b
    modified = gr.regulate(blocks, 10)
    assert isinstance(modified, list)
    print(f"    regulate 10 blocks -> {len(modified)} modified")
    print("  PASS: test_granularity_regulator")


def test_summary_engine():
    se = SummaryEngine()
    from core.agent.discourse_block_tree.models import DiscourseBlock, EDU
    b = DiscourseBlock(block_id="b1", name="test")
    b.created_at_turn = 1
    for i in range(5):
        b.add_edu(EDU(index=i, raw_text=f"step{i}"))
    upgraded = se.check_upgrade(b, 10)
    print(f"    summary upgraded from triggered -> {b.summary.version}")
    print("  PASS: test_summary_engine")


if __name__ == "__main__":
    tests = [
        test_edu_basics,
        test_cohesion_score,
        test_progressive_summary,
        test_header_injector,
        test_syntactic_decomposer,
        test_macro_micro_quantizer,
        test_segmenter,
        test_manager_basic,
        test_manager_multi_turn,
        test_context_builder,
        test_indexer,
        test_granularity_regulator,
        test_summary_engine,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")