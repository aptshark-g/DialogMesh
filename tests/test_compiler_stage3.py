# tests/test_compiler_stage3.py
"""测试 MacroMicroQuantizer Stage 3 宏观微观量化器（纯 Python，无 pytest 依赖）。"""

import sys
import os
import math
import time
import importlib.util

# 直接从文件路径加载被测模块，绕过 core.agent 包级联导入
def load_module_from_path(module_name, rel_path):
    abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

macro_micro_quantizer_module = load_module_from_path(
    "macro_micro_quantizer",
    "core/agent/compiler/macro_micro_quantizer.py"
)
models_module = load_module_from_path(
    "discourse_models",
    "core/agent/discourse_block_tree/models.py"
)

MacroMicroQuantizer = macro_micro_quantizer_module.MacroMicroQuantizer
EDU = models_module.EDU
MicroDimensions = models_module.MicroDimensions
MacroDimensions = models_module.MacroDimensions


# ── 辅助函数 ──────────────────────────────────────────────────────

def make_edu(text, turn=0, entities=None, intent=None):
    return EDU(
        id=f"edu:T{turn}:U0",
        turn_index=turn,
        edu_index=0,
        raw_text=text,
        raw_entities=entities or [],
        intent_label=intent,
    )


# ── 测试函数 ──────────────────────────────────────────────────────

def test_basic_quantize():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("我喜欢 Python", entities=["Python"], intent="analyze"),
        make_edu("Python 很强大", entities=["Python"], intent="analyze"),
    ]
    result = quantizer.quantize(edus)
    assert len(result) == 2
    assert result[0].micro_dimensions is not None
    assert result[0].macro_dimensions is not None
    assert result[1].micro_dimensions is not None
    assert result[1].macro_dimensions is not None


def test_embedding_computed():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edu = make_edu("测试文本")
    quantizer.quantize([edu])
    assert edu.embedding is not None
    assert len(edu.embedding) == quantizer._embedding_dim


def test_micro_dimensions_range():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edu = make_edu("因为 Python 很好，所以用它")
    quantizer.quantize([edu])
    micro = edu.micro_dimensions
    assert 0.0 <= micro.μ1 <= 1.0
    assert 0.0 <= micro.μ2 <= 1.0
    assert 0.0 <= micro.μ3 <= 1.0
    assert 0.0 <= micro.μ4 <= 1.0
    assert 0.0 <= micro.μ5 <= 1.0


def test_macro_dimensions_similarity():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("相同文本", entities=["A"], intent="test"),
        make_edu("相同文本", entities=["A"], intent="test"),
    ]
    quantizer.quantize(edus)
    macro = edus[1].macro_dimensions
    assert macro.M1 == 1.0
    assert macro.M2 == 1.0
    assert macro.M3 == 1.0
    assert macro.M4 == 1.0


def test_macro_dimensions_different_intent():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("文本A", intent="analyze"),
        make_edu("文本B", intent="question"),
    ]
    quantizer.quantize(edus)
    macro = edus[1].macro_dimensions
    assert macro.M2 == 0.0


def test_inter_edu_cohesion():
    """相邻 EDU 粘合度计算。"""
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("我喜欢 Python", entities=["Python"], intent="analyze"),
        make_edu("Python 很强大", entities=["Python"], intent="analyze"),
    ]
    quantizer.quantize(edus)
    cohesion = quantizer.compute_inter_edu_cohesion(edus[0], edus[1])
    assert 0.0 <= cohesion <= 1.0
    # 相同意图 + 相同实体 → 粘合度应 > 0.3（M2/M3/M4 贡献）
    assert cohesion > 0.3


def test_block_cohesion():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("A", entities=["X"]),
        make_edu("B", entities=["X"]),
        make_edu("C", entities=["X"]),
    ]
    quantizer.quantize(edus)
    block_cohesion = quantizer.compute_block_cohesion(edus)
    assert 0.0 <= block_cohesion <= 1.0


def test_pseudo_embedding_deterministic():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    v1 = quantizer._pseudo_embedding("相同文本")
    v2 = quantizer._pseudo_embedding("相同文本")
    assert v1 == v2


def test_pseudo_embedding_normalized():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    v = quantizer._pseudo_embedding("任意文本")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6


def test_cosine_similarity_same():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    v = [1.0, 0.0, 0.0]
    sim = quantizer._cosine_similarity(v, v)
    assert abs(sim - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    sim = quantizer._cosine_similarity(v1, v2)
    assert abs(sim) < 1e-6


def test_jaccard_same():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    assert quantizer._jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    assert quantizer._jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_empty():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    assert quantizer._jaccard(set(), set()) == 1.0


def test_temporal_decay():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu("文本A", turn=0),
        make_edu("文本B", turn=5),
    ]
    quantizer.quantize(edus)
    macro = edus[1].macro_dimensions
    assert macro.M4 < 1.0


def test_micro_dimensions_causal():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edu = make_edu("因为 Python 很好，所以用它")
    quantizer.quantize([edu])
    micro = edu.micro_dimensions
    assert micro.μ2 > 0.0


def test_micro_dimensions_reference():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edu = make_edu("这个很好，那个也不错")
    quantizer.quantize([edu])
    micro = edu.micro_dimensions
    assert micro.μ3 > 0.0


def test_performance_quantize_3_edus():
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    edus = [
        make_edu(f"文本{i}", entities=["X"])
        for i in range(3)
    ]
    start = time.time()
    for _ in range(100):
        quantizer.quantize(edus)
    elapsed = time.time() - start
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 5.0, f"平均延迟 {avg_ms:.2f}ms，超过 5ms 阈值"


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_basic_quantize,
        test_embedding_computed,
        test_micro_dimensions_range,
        test_macro_dimensions_similarity,
        test_macro_dimensions_different_intent,
        test_inter_edu_cohesion,
        test_block_cohesion,
        test_pseudo_embedding_deterministic,
        test_pseudo_embedding_normalized,
        test_cosine_similarity_same,
        test_cosine_similarity_orthogonal,
        test_jaccard_same,
        test_jaccard_disjoint,
        test_jaccard_empty,
        test_temporal_decay,
        test_micro_dimensions_causal,
        test_micro_dimensions_reference,
        test_performance_quantize_3_edus,
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
