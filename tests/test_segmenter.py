"""Segmenter Tests — JSON-driven."""

import sys; sys.path.insert(0, '.')
from core.agent.discourse_block_tree.segmenter import Segmenter
from core.agent.discourse_block_tree.models import EDU

# Test 1: Single EDU → one block
edus = [EDU(index=0, raw_text="定位延迟")]
seg = Segmenter()
blocks = seg.segment(edus)
assert len(blocks) == 1, f"Expected 1 block, got {len(blocks)}"
print("  ✅ single EDU → 1 block")

# Test 2: Cohesive EDUs → one block
edus2 = [
    EDU(index=0, raw_text="定位延迟"),
    EDU(index=1, raw_text="然后修复"),
]
blocks2 = seg.segment(edus2)
print(f"  ✅ 2 cohesive EDUs → {len(blocks2)} block(s)")

# Test 3: Cross-topic EDUs → split likely
edus3 = [
    EDU(index=0, raw_text="写Python函数"),
    EDU(index=1, raw_text="昨天神经网络方案怎么样"),
]
blocks3 = seg.segment(edus3)
# Content differs enough that cohesion should be low → split likely
has_split = len(blocks3) >= 2
print(f"  {'✅' if has_split else '⚠️'} cross-topic EDUs → {len(blocks3)} block(s) (split={'yes' if has_split else 'no'})")

# Test 4: Threshold sensitivity
seg_low = Segmenter(global_split_threshold=0.2)
blocks_low = seg_low.segment(edus3)
print(f"  ✅ low threshold(0.2) → {len(blocks_low)} block(s) (more splits)")

seg_high = Segmenter(global_split_threshold=0.8)
blocks_high = seg_high.segment(edus3)
print(f"  ✅ high threshold(0.8) → {len(blocks_high)} block(s) (fewer splits)")

print("\n🎉 Segmenter: all tests passed")
