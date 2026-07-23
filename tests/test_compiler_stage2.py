# tests/test_compiler_stage2.py
"""测试 SyntacticDecomposer Stage 2 语法分解器（纯 Python，无 pytest 依赖）。"""

import sys
import os
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

syntactic_decomposer_module = load_module_from_path(
    "syntactic_decomposer",
    "core/agent/compiler/syntactic_decomposer.py"
)

SyntacticDecomposer = syntactic_decomposer_module.SyntacticDecomposer
ParsedClause = syntactic_decomposer_module.ParsedClause


# ── 测试函数 ──────────────────────────────────────────────────────

def test_simple_statement():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("我喜欢 Python 编程")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.raw_text == "我喜欢 Python 编程"
    assert c.predicate is not None
    assert c.parse_failed is False


def test_question():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("Python 是什么？")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.question is True
    assert c.predicate is not None


def test_negation():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("我不想用 Java")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.negation is True


def test_imperative():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("帮我写一个 Python 脚本")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.imperative is True


def test_multiple_clauses():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("我喜欢 Python。Java 也不错。")
    assert len(clauses) >= 2
    texts = [c.raw_text for c in clauses]
    assert any("Python" in t for t in texts)
    assert any("Java" in t for t in texts)


def test_tech_entities():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("用 Redis 缓存数据，0x7FFF 是地址")
    assert len(clauses) >= 1
    c = clauses[0]
    assert "Redis" in c.raw_entities
    assert any("0x7FFF" in e for e in c.raw_entities)


def test_english_imperative():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("scan the memory at 0x4000")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.imperative is True
    assert c.predicate == "scan"


def test_complex_input_detection():
    decomp = SyntacticDecomposer()
    text = "。".join([f"句子{i}" for i in range(10)])
    clauses = decomp.decompose(text)
    assert len(clauses) == 1
    assert clauses[0].parse_failed is True
    assert clauses[0].parse_failed_reason == "complex_input"


def test_multiple_subjects_detection():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("这个很好，那个也不错")
    for c in clauses:
        if "这个" in c.raw_text and "那个" in c.raw_text:
            assert c.parse_failed is True
            assert c.parse_failed_reason == "multiple_subjects"


def test_uncertainty_detection():
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose("也许可以用 Python")
    assert len(clauses) == 1
    c = clauses[0]
    assert c.uncertainty is True


def test_parsed_clause_to_compact():
    c = ParsedClause(
        raw_text="测试",
        subject="我",
        predicate="喜欢",
        object="Python",
        negation=False,
    )
    compact = c.to_compact()
    assert "我" in compact
    assert "喜欢" in compact
    assert "Python" in compact


def test_parsed_clause_entity_signature():
    c = ParsedClause(
        raw_text="测试",
        subject="Python",
        predicate="是",
        object="语言",
        negation=True,
        subject_attrs=["好的"],
    )
    sig = c.to_entity_signature()
    assert "NOT" in sig
    assert "Python" in sig
    assert "语言" in sig


def test_fast_path_performance():
    decomp = SyntacticDecomposer()
    start = time.time()
    for _ in range(1000):
        decomp.decompose("帮我scan内存地址0x7FFF")
    elapsed = time.time() - start
    avg_ms = (elapsed / 1000) * 1000
    assert avg_ms < 1.0, f"平均延迟 {avg_ms:.2f}ms，超过 1ms 阈值"


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_simple_statement,
        test_question,
        test_negation,
        test_imperative,
        test_multiple_clauses,
        test_tech_entities,
        test_english_imperative,
        test_complex_input_detection,
        test_multiple_subjects_detection,
        test_uncertainty_detection,
        test_parsed_clause_to_compact,
        test_parsed_clause_entity_signature,
        test_fast_path_performance,
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
