# tests/test_compiler_stage1.py
"""测试 HeaderInjector Stage 1 预处理器（纯 Python，无 pytest 依赖）。"""

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

header_injector_module = load_module_from_path(
    "header_injector",
    "core/agent/compiler/header_injector.py"
)

HeaderInjector = header_injector_module.HeaderInjector
InjectionResult = header_injector_module.InjectionResult
EntityCandidate = header_injector_module.EntityCandidate


# ── 测试函数 ──────────────────────────────────────────────────────

def test_basic_inject_no_pronoun():
    injector = HeaderInjector()
    result = injector.inject("帮我写一个 Python 脚本", "session_1")
    assert result.text == "帮我写一个 Python 脚本"
    assert result.replacements == []
    assert result.unresolved_pronouns == []


def test_pronoun_resolution_context_entity():
    injector = HeaderInjector()
    history = [
        {"role": "user", "content": "我喜欢喝汽水"},
    ]
    result = injector.inject("这个很甜", "session_1", session_history=history)
    assert "汽水" in result.text
    assert result.replacements
    assert result.replacements[0][0] == "这个"
    assert result.replacements[0][1] == "汽水"


def test_pronoun_resolution_same_turn():
    injector = HeaderInjector()
    result = injector.inject("Python 这个语言很有趣，这个很强大", "session_1")
    assert result.text.startswith("Python")
    assert "Python" in result.text.replace("Python", "", 1)


def test_omitted_object_completion():
    injector = HeaderInjector()
    result = injector.inject("帮我scan", "session_1")
    assert result.text.endswith("内存")
    assert any("scan" in r[2].reason for r in result.replacements)


def test_causal_kb_inference():
    injector = HeaderInjector()
    history = [
        {"role": "user", "content": "我在喝汽水"},
    ]
    result = injector.inject("那个很呛", "session_1", session_history=history)
    assert "汽水" in result.text


def test_multiple_pronouns_only_first():
    """只处理第一个代词，避免过度推断。"""
    injector = HeaderInjector()
    history = [
        {"role": "user", "content": "我喜欢 Python"},
    ]
    result = injector.inject("这个很好，那个也不错", "session_1", session_history=history)
    # 第一个 "这个" 应解析为 "Python"（上下文继承）
    assert result.replacements
    assert result.replacements[0][0] == "这个"
    assert result.replacements[0][1] == "Python"
    # 第二个 "那个" 不应被处理（break 只处理第一个）
    assert "那个" not in [r[0] for r in result.replacements]


def test_unresolved_pronoun():
    injector = HeaderInjector()
    result = injector.inject("这个很好", "session_1")
    assert "这个" in result.unresolved_pronouns


def test_verb_with_object_no_change():
    injector = HeaderInjector()
    result = injector.inject("帮我scan内存地址", "session_1")
    assert result.text == "帮我scan内存地址"
    assert result.replacements == []


def test_history_entity_pool():
    injector = HeaderInjector(context_window_size=3)
    history = [
        {"role": "user", "content": "我在用 Redis 做缓存"},
        {"role": "assistant", "content": "Redis 是个好选择"},
        {"role": "user", "content": "那个性能怎么样"},
    ]
    result = injector.inject("这个很稳定", "session_1", session_history=history)
    assert "Redis" in result.text


def test_reload_kb():
    injector = HeaderInjector()
    injector.reload_kb()
    assert injector._causal_kb is not None


def test_default_kb_created():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        kb_path = os.path.join(tmpdir, "kb.json")
        injector = HeaderInjector(kb_path=kb_path)
        assert os.path.exists(kb_path)


def test_domain_specific_kb():
    injector = HeaderInjector(domain="tech_reverse")
    result = injector.inject("那个蓝屏了", "session_1")
    assert "驱动" in result.text


def test_complex_input_with_entity():
    injector = HeaderInjector()
    text = "0x7FFF0000 这个地址帮我scan"
    result = injector.inject(text, "session_1")
    assert result.text.startswith("0x7FFF0000")
    assert result.replacements


def test_performance_fast():
    injector = HeaderInjector()
    start = time.time()
    for _ in range(100):
        injector.inject("这个很甜", "perf_session", session_history=[
            {"role": "user", "content": "我喜欢汽水"},
        ])
    elapsed = time.time() - start
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 5.0, f"平均延迟 {avg_ms:.2f}ms，超过 5ms 阈值"


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_basic_inject_no_pronoun,
        test_pronoun_resolution_context_entity,
        test_pronoun_resolution_same_turn,
        test_omitted_object_completion,
        test_causal_kb_inference,
        test_multiple_pronouns_only_first,
        test_unresolved_pronoun,
        test_verb_with_object_no_change,
        test_history_entity_pool,
        test_reload_kb,
        test_default_kb_created,
        test_domain_specific_kb,
        test_complex_input_with_entity,
        test_performance_fast,
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
