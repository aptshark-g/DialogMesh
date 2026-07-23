"""DiscourseBlockTree Tests."""

import sys
sys.path.insert(0, '.')
from core.agent.compiler.discourse_block_tree import DiscourseBlockTreeManager, DiscourseBlockGranularityRegulator


def test_feed():
    m = DiscourseBlockTreeManager()
    r = m.feed("scan 0x401000 for entry point", "s1")
    assert r.decision.value in ("continue", "merge", "split")
    tree = m.get_tree("s1")
    assert tree is not None
    assert len(tree.blocks) >= 1
    print(f"✅ feed: {len(tree.blocks)} blocks, decision={r.decision.value}")


def test_summary():
    m = DiscourseBlockTreeManager()
    m.feed("scan 0x401000 analyze encryption algorithm", "s2")
    block = list(m.get_tree("s2").blocks.values())[0]
    for t, name in [(0, "Hot"), (1, "Warm"), (2, "Cold"), (3, "Frozen")]:
        block.temperature = t
        s = block.summarize()
        assert len(s) > 0
        print(f"  {name}(t={t}): {s[:50]}...")
    print("✅ 4-level summary")


def test_bor():
    reg = DiscourseBlockGranularityRegulator()
    reg.bor_history = [0.5, 0.6, 0.4]
    reg._adapt_threshold()
    assert reg.global_split_threshold < 0.25
    print(f"✅ BOR: {reg.global_split_threshold:.2f}")


def test_context():
    m = DiscourseBlockTreeManager()
    for t in ["scan memory", "analyze encryption", "patch binary"]:
        m.feed(t, "s3")
    ctx = m.build_context("s3", 3)
    assert len(ctx) > 0
    print(f"✅ build_context: {len(ctx)} chars")


if __name__ == "__main__":
    test_feed()
    test_summary()
    test_bor()
    test_context()
    print("\n🎉 DiscourseBlockTree: all tests passed")
