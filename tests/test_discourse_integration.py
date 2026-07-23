# tests/test_discourse_integration.py
"""测试 DiscoursePipeline 集成模块（纯 Python，无 pytest 依赖）。"""

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

# 加载所有依赖模块
_ = load_module_from_path("discourse_models", "core/agent/discourse_block_tree/models.py")
_ = load_module_from_path("segmenter", "core/agent/discourse_block_tree/segmenter.py")
_ = load_module_from_path("manager", "core/agent/discourse_block_tree/manager.py")
_ = load_module_from_path("summary_engine", "core/agent/discourse_block_tree/summary_engine.py")
_ = load_module_from_path("context_builder", "core/agent/discourse_block_tree/context_builder.py")

discourse_int = load_module_from_path(
    "discourse_integration", "core/agent/discourse_integration.py"
)

DiscoursePipeline = discourse_int.DiscoursePipeline


# ── 测试函数 ──────────────────────────────────────────────────────

def test_disabled():
    """disabled 时返回空字符串。"""
    pipe = DiscoursePipeline(enabled=False)
    ctx = pipe.process_turn("帮我写 Python", turn_index=0)
    assert ctx == ""


def test_basic_turn():
    """基本单轮处理。"""
    pipe = DiscoursePipeline()
    ctx = pipe.process_turn("帮我写 Python 脚本", turn_index=0)
    assert len(ctx) > 0
    assert "Hot" in ctx


def test_multi_turn():
    """多轮次处理。"""
    pipe = DiscoursePipeline()
    for turn in range(4):
        ctx = pipe.process_turn(f"Turn {turn} content", turn_index=turn)
    # 第 4 轮，第 0 轮已变为 Warm
    assert "Hot" in ctx or "Warm" in ctx or "Cold" in ctx


def test_with_history():
    """带历史上下文的处理。"""
    pipe = DiscoursePipeline()
    history = [
        {"role": "user", "content": "我喜欢 Python"},
        {"role": "assistant", "content": "Python 很好"},
    ]
    ctx = pipe.process_turn("这个很强大", session_history=history, turn_index=1)
    assert len(ctx) > 0


def test_reset():
    """重置状态。"""
    pipe = DiscoursePipeline()
    pipe.process_turn("A", turn_index=0)
    assert pipe.manager.block_count == 1
    pipe.reset()
    assert pipe.manager.block_count == 0


def test_complex_input():
    """复杂输入处理（parse_failed 回退）。"""
    pipe = DiscoursePipeline()
    text = "。".join([f"句子{i}" for i in range(10)])
    ctx = pipe.process_turn(text, turn_index=0)
    # 即使 parse_failed 也不应抛异常
    assert isinstance(ctx, str)


def test_header_injection():
    """头文件注入效果。"""
    pipe = DiscoursePipeline()
    history = [{"role": "user", "content": "我喜欢汽水"}]
    ctx = pipe.process_turn("这个很甜", session_history=history, turn_index=1)
    assert "汽水" in ctx or "[DiscoursePipeline" in ctx


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_disabled,
        test_basic_turn,
        test_multi_turn,
        test_with_history,
        test_reset,
        test_complex_input,
        test_header_injection,
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
