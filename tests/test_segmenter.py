# tests/test_segmenter.py
"""测试 Segmenter 轮内切分器（纯 Python，无 pytest 依赖）。"""

import sys
import os
import importlib.util

root = os.getcwd()

def load_module_from_path(module_name, rel_path):
    abs_path = os.path.join(root, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

models_module = load_module_from_path("discourse_models", "core/agent/discourse_block_tree/models.py")
segmenter_module = load_module_from_path("segmenter", "core/agent/discourse_block_tree/segmenter.py")

EDU = models_module.EDU
DiscourseBlock = models_module.DiscourseBlock
BlockState = models_module.BlockState
BoundaryType = models_module.BoundaryType
MacroDimensions = models_module.MacroDimensions
MicroDimensions = models_module.MicroDimensions
Segmenter = segmenter_module.Segmenter


# ── 辅助函数 ──────────────────────────────────────────────────────

def make_edu(text, turn=0, edu_idx=0, entities=None, intent=None, micro=None, macro=None):
    edu = EDU(
        id=f"edu:T{turn}:U{edu_idx}",
        turn_index=turn,
        edu_index=edu_idx,
        raw_text=text,
        raw_entities=entities or [],
        intent_label=intent,
    )
    edu.micro_dimensions = micro or MicroDimensions()
    edu.macro_dimensions = macro or MacroDimensions()
    return edu


def make_high_cohesion_edu(text, turn=0, edu_idx=0, entities=None, intent=None):
    """高粘合度 EDU（与相邻 EDU 高 cohesion）。"""
    return make_edu(
        text, turn, edu_idx, entities, intent,
        micro=MicroDimensions(μ1=0.8, μ2=0.8, μ3=0.8, μ4=0.8, μ5=0.8),
        macro=MacroDimensions(M1=0.8, M2=0.8, M3=0.8, M4=0.8),
    )


def make_low_cohesion_edu(text, turn=0, edu_idx=0, entities=None, intent=None):
    """低粘合度 EDU（与相邻 EDU 低 cohesion）。"""
    return make_edu(
        text, turn, edu_idx, entities, intent,
        micro=MicroDimensions(μ1=0.1, μ2=0.1, μ3=0.1, μ4=0.1, μ5=0.1),
        macro=MacroDimensions(M1=0.1, M2=0.1, M3=0.1, M4=0.1),
    )


# ── 测试函数 ──────────────────────────────────────────────────────

def test_empty_edus():
    seg = Segmenter()
    blocks = seg.segment([])
    assert blocks == []


def test_single_edu():
    seg = Segmenter()
    edu = make_high_cohesion_edu("A")
    blocks = seg.segment([edu])
    assert len(blocks) == 1
    assert blocks[0].edu_count == 1


def test_no_boundary_all_high():
    """全部高粘合度，不切分。"""
    seg = Segmenter()
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["X"], intent="analyze"),
        make_high_cohesion_edu("B", edu_idx=1, entities=["X"], intent="analyze"),
        make_high_cohesion_edu("C", edu_idx=2, entities=["X"], intent="analyze"),
    ]
    blocks = seg.segment(edus)
    assert len(blocks) == 1
    assert blocks[0].edu_count == 3


def test_cohesion_cliff_split():
    """粘合度悬崖 → 切分。"""
    seg = Segmenter(threshold=0.5)
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["X"], intent="analyze"),
        make_low_cohesion_edu("B", edu_idx=1, entities=["Y"], intent="question"),
    ]
    blocks = seg.segment(edus)
    assert len(blocks) == 2
    assert blocks[0].edu_count == 1
    assert blocks[1].edu_count == 1


def test_bdi_split():
    """BDI 意图漂移 → 强制切分。"""
    seg = Segmenter(bdi_enabled=True)
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["X"], intent="analyze"),
        make_high_cohesion_edu("B", edu_idx=1, entities=["X"], intent="question"),
    ]
    # 虽然 cohesion 高，但 BDI 强制切分
    blocks = seg.segment(edus)
    assert len(blocks) == 2
    assert edus[1].boundary_type == BoundaryType.BDI


def test_bdi_disabled():
    """BDI 关闭 → 不切分。"""
    seg = Segmenter(bdi_enabled=False)
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["X"], intent="analyze"),
        make_high_cohesion_edu("B", edu_idx=1, entities=["X"], intent="question"),
    ]
    blocks = seg.segment(edus)
    assert len(blocks) == 1


def test_mixed_boundaries():
    """混合场景：高 cohesion + cliff + BDI。"""
    seg = Segmenter(threshold=0.5)
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["X"], intent="analyze"),
        make_high_cohesion_edu("B", edu_idx=1, entities=["X"], intent="analyze"),
        make_low_cohesion_edu("C", edu_idx=2, entities=["Y"], intent="question"),
        make_low_cohesion_edu("D", edu_idx=3, entities=["Z"], intent="command"),
    ]
    blocks = seg.segment(edus)
    # A+B 高 cohesion 不切分，C 低 cohesion 切分，D 与 C 不同意图 + 低 cohesion 切分
    assert len(blocks) >= 2


def test_block_embedding_aggregated():
    """块级 embedding 是 EDU embedding 的平均。"""
    seg = Segmenter()
    edus = [
        make_high_cohesion_edu("A", edu_idx=0),
        make_high_cohesion_edu("B", edu_idx=1),
    ]
    edus[0].embedding = [1.0, 0.0, 0.0]
    edus[1].embedding = [0.0, 1.0, 0.0]
    blocks = seg.segment(edus)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.macro_embedding is not None
    assert len(block.macro_embedding) == 3
    # 平均向量 = [0.5, 0.5, 0.0]
    assert abs(block.macro_embedding[0] - 0.5) < 1e-6
    assert abs(block.macro_embedding[1] - 0.5) < 1e-6


def test_block_intent_label():
    """块级意图是主导意图。"""
    seg = Segmenter(bdi_enabled=False)  # 关闭 BDI，避免意图漂移切分
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, intent="analyze"),
        make_high_cohesion_edu("B", edu_idx=1, intent="analyze"),
        make_high_cohesion_edu("C", edu_idx=2, intent="question"),
    ]
    blocks = seg.segment(edus)
    assert len(blocks) == 1
    assert blocks[0].intent_label == "analyze"


def test_block_entity_signature():
    """块级实体签名聚合。"""
    seg = Segmenter()
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, entities=["Python"]),
        make_high_cohesion_edu("B", edu_idx=1, entities=["Python", "Java"]),
    ]
    blocks = seg.segment(edus)
    assert blocks[0].entity_signature == "Python Java"


def test_block_turn_range():
    """块覆盖的轮次范围。"""
    seg = Segmenter()
    edus = [
        make_high_cohesion_edu("A", turn=0, edu_idx=0),
        make_high_cohesion_edu("B", turn=0, edu_idx=1),
    ]
    blocks = seg.segment(edus)
    assert blocks[0].start_turn == 0
    assert blocks[0].end_turn == 0
    assert blocks[0].turn_count == 1


def test_boundary_type_marked():
    """边界类型被正确标记。"""
    seg = Segmenter(threshold=0.5)
    edus = [
        make_high_cohesion_edu("A", edu_idx=0, intent="analyze"),
        make_low_cohesion_edu("B", edu_idx=1, intent="question"),
    ]
    seg.segment(edus)
    assert edus[1].boundary_type == BoundaryType.BDI  # BDI 优先级高于 cohesion cliff


def test_cosine_similarity():
    """余弦相似度工具方法。"""
    seg = Segmenter()
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert abs(seg._cosine_similarity(v1, v2) - 1.0) < 1e-6

    v3 = [0.0, 1.0, 0.0]
    assert abs(seg._cosine_similarity(v1, v3)) < 1e-6


def test_jaccard():
    """Jaccard 工具方法。"""
    seg = Segmenter()
    assert seg._jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert seg._jaccard({"a"}, {"b"}) == 0.0
    assert seg._jaccard(set(), set()) == 1.0


def test_block_boundary_cohesion():
    """块间边界粘合度计算。"""
    seg = Segmenter()
    block_a = DiscourseBlock(id="a", edus=[])
    block_a.macro_embedding = [1.0, 0.0, 0.0]
    block_a.intent_label = "analyze"
    block_a.entity_signature = "Python"

    block_b = DiscourseBlock(id="b", edus=[])
    block_b.macro_embedding = [1.0, 0.0, 0.0]
    block_b.intent_label = "analyze"
    block_b.entity_signature = "Python"

    cohesion = seg.compute_block_boundary_cohesion(block_a, block_b)
    assert cohesion > 0.8  # 高相似度


def test_compute_cohesion_formula():
    """验证 cohesion 公式: 0.6*macro + 0.4*micro。"""
    seg = Segmenter()
    edu_i = make_edu("A",
                     micro=MicroDimensions(μ1=1.0, μ2=1.0, μ3=1.0, μ4=1.0, μ5=1.0),
                     macro=MacroDimensions(M1=1.0, M2=1.0, M3=1.0, M4=1.0))
    edu_j = make_edu("B",
                     micro=MicroDimensions(μ1=0.0, μ2=0.0, μ3=0.0, μ4=0.0, μ5=0.0),
                     macro=MacroDimensions(M1=0.0, M2=0.0, M3=0.0, M4=0.0))
    cohesion = seg._compute_cohesion(edu_i, edu_j)
    # macro=0, micro=0 → cohesion=0
    assert cohesion == 0.0

    edu_j2 = make_edu("C",
                      micro=MicroDimensions(μ1=1.0, μ2=1.0, μ3=1.0, μ4=1.0, μ5=1.0),
                      macro=MacroDimensions(M1=1.0, M2=1.0, M3=1.0, M4=1.0))
    cohesion2 = seg._compute_cohesion(edu_i, edu_j2)
    # macro=1.0, micro=1.0 → cohesion=1.0
    assert abs(cohesion2 - 1.0) < 1e-6


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_empty_edus,
        test_single_edu,
        test_no_boundary_all_high,
        test_cohesion_cliff_split,
        test_bdi_split,
        test_bdi_disabled,
        test_mixed_boundaries,
        test_block_embedding_aggregated,
        test_block_intent_label,
        test_block_entity_signature,
        test_block_turn_range,
        test_boundary_type_marked,
        test_cosine_similarity,
        test_jaccard,
        test_block_boundary_cohesion,
        test_compute_cohesion_formula,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {test.__name__}: {e}")
            failed += 1
    print(f"\n结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 个测试")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
