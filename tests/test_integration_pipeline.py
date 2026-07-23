# tests/test_integration_pipeline.py
"""端到端集成测试：完整编译器管道 + DiscourseBlock Tree。

流程:
Raw Text → HeaderInjector (Stage 1) → SyntacticDecomposer (Stage 2) →
MacroMicroQuantizer (Stage 3) → Segmenter (切分) → Manager (路由) →
SummaryEngine (摘要) → ContextBuilder (上下文)
"""

import sys
import os
import importlib.util
import time

root = os.getcwd()

def load_module_from_path(module_name, rel_path):
    abs_path = os.path.join(root, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 加载所有模块
hi = load_module_from_path("header_injector", "core/agent/compiler/header_injector.py")
sd = load_module_from_path("syntactic_decomposer", "core/agent/compiler/syntactic_decomposer.py")
mm = load_module_from_path("macro_micro_quantizer", "core/agent/compiler/macro_micro_quantizer.py")
models = load_module_from_path("discourse_models", "core/agent/discourse_block_tree/models.py")
seg = load_module_from_path("segmenter", "core/agent/discourse_block_tree/segmenter.py")
manager = load_module_from_path("manager", "core/agent/discourse_block_tree/manager.py")
se = load_module_from_path("summary_engine", "core/agent/discourse_block_tree/summary_engine.py")
cb = load_module_from_path("context_builder", "core/agent/discourse_block_tree/context_builder.py")
idx = load_module_from_path("indexer", "core/agent/discourse_block_tree/indexer.py")

HeaderInjector = hi.HeaderInjector
SyntacticDecomposer = sd.SyntacticDecomposer
MacroMicroQuantizer = mm.MacroMicroQuantizer
EDU = models.EDU
DiscourseBlock = models.DiscourseBlock
BlockState = models.BlockState
Segmenter = seg.Segmenter
DiscourseBlockTreeManager = manager.DiscourseBlockTreeManager
SummaryEngine = se.SummaryEngine
ContextBuilder = cb.ContextBuilder
Indexer = idx.Indexer


# ── 辅助函数 ──────────────────────────────────────────────────────

def run_pipeline(text: str, turn_index: int = 0, session_id: str = "test") -> list:
    """运行完整编译器管道。

    Returns:
        输出的话语块列表
    """
    # Stage 1: HeaderInjector
    injector = HeaderInjector()
    injected = injector.inject(text, session_id)

    # Stage 2: SyntacticDecomposer
    decomposer = SyntacticDecomposer()
    clauses = decomposer.decompose(injected.text)

    # 转换为 EDU（简化：每个 clause 一个 EDU）
    edus = []
    for i, clause in enumerate(clauses):
        if not clause.parse_failed:
            edu = EDU(
                id=f"edu:T{turn_index}:U{i}",
                turn_index=turn_index,
                edu_index=i,
                raw_text=clause.raw_text,
                subject=clause.subject,
                predicate=clause.predicate,
                object=clause.object,
                subject_attrs=clause.subject_attrs,
                object_attrs=clause.object_attrs,
                negation=clause.negation,
                uncertainty=clause.uncertainty,
                imperative=clause.imperative,
                question=clause.question,
                raw_entities=clause.raw_entities,
                parse_failed=clause.parse_failed,
                intent_label="analyze" if clause.predicate else "statement",
            )
        else:
            # parse_failed 的整句
            edu = EDU(
                id=f"edu:T{turn_index}:U{i}",
                turn_index=turn_index,
                edu_index=i,
                raw_text=clause.raw_text,
                parse_failed=True,
                intent_label="statement",
            )
        edus.append(edu)

    # Stage 3: MacroMicroQuantizer
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    quantizer.quantize(edus)

    # Segmenter: 切分
    segmenter = Segmenter()
    blocks = segmenter.segment(edus)

    # 设置块意图（如果没有）
    for block in blocks:
        if not block.intent_label:
            block.intent_label = "statement"

    return blocks, injector, edus


# ── 测试函数 ──────────────────────────────────────────────────────

def test_pipeline_simple():
    """端到端：简单中文指令。"""
    blocks, injector, edus = run_pipeline("帮我写一个 Python 脚本")
    assert len(edus) >= 1
    assert len(blocks) >= 1
    # 检查头文件注入
    assert "Python" in injector._turn_entity_cache.get("test", [])


def test_pipeline_multi_clauses():
    """端到端：多子句输入。"""
    blocks, _, edus = run_pipeline("我喜欢 Python。Java 也不错。")
    assert len(edus) >= 2
    # 切分：两个子句意图不同（analyze vs statement）或低 cohesion → 可能切分
    assert len(blocks) >= 1


def test_pipeline_with_manager():
    """端到端：通过 Manager 管理。"""
    mgr = DiscourseBlockTreeManager()
    blocks, _, edus = run_pipeline("帮我scan内存地址", turn_index=0)
    routed = mgr.ingest_turn(edus)
    assert len(routed) >= 1
    assert mgr.block_count >= 1


def test_pipeline_with_summary():
    """端到端：生成摘要。"""
    blocks, _, edus = run_pipeline("User likes Python", turn_index=0)
    engine = SummaryEngine()
    for block in blocks:
        summary = engine.summarize_block(block)
        assert summary.v1 is not None
        assert summary.v2 is not None


def test_pipeline_with_context():
    """端到端：构建上下文。"""
    mgr = DiscourseBlockTreeManager()
    for turn in range(3):
        blocks, _, edus = run_pipeline(f"Turn {turn} content", turn_index=turn)
        mgr.ingest_turn(edus)

    builder = ContextBuilder(hot_turns=2)
    ctx = builder.build_context(mgr.get_blocks(), current_turn=2)
    assert len(ctx) > 0


def test_pipeline_with_indexer():
    """端到端：索引查询。"""
    indexer = Indexer()
    mgr = DiscourseBlockTreeManager()
    blocks, _, edus = run_pipeline("Python and Java", turn_index=0)
    mgr.ingest_turn(edus)
    for block in mgr.get_blocks():
        indexer.index_block(block)

    assert len(indexer.query_by_entity("Python")) >= 1
    assert len(indexer.query_by_entity("Java")) >= 1


def test_pipeline_with_history():
    """端到端：带历史上下文的注入。"""
    injector = HeaderInjector()
    history = [
        {"role": "user", "content": "我在喝汽水"},
    ]
    result = injector.inject("这个很甜", "session_2", session_history=history)
    assert "汽水" in result.text

    decomposer = SyntacticDecomposer()
    clauses = decomposer.decompose(result.text)
    assert len(clauses) >= 1


def test_pipeline_performance():
    """端到端性能：单轮 < 10ms。"""
    start = time.time()
    for _ in range(100):
        run_pipeline("帮我写一个 Python 脚本分析数据", turn_index=0)
    elapsed = time.time() - start
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 10.0, f"平均延迟 {avg_ms:.2f}ms，超过 10ms 阈值"


def test_pipeline_english():
    """端到端：英文指令。"""
    blocks, _, edus = run_pipeline("scan the memory at 0x4000", turn_index=0)
    assert len(edus) >= 1
    assert len(blocks) >= 1


def test_pipeline_complex_input():
    """端到端：复杂输入（parse_failed 标记）。"""
    text = "。".join([f"句子{i}" for i in range(10)])
    blocks, _, edus = run_pipeline(text, turn_index=0)
    # 复杂输入应标记 parse_failed
    assert any(e.parse_failed for e in edus)


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_pipeline_simple,
        test_pipeline_multi_clauses,
        test_pipeline_with_manager,
        test_pipeline_with_summary,
        test_pipeline_with_context,
        test_pipeline_with_indexer,
        test_pipeline_with_history,
        test_pipeline_performance,
        test_pipeline_english,
        test_pipeline_complex_input,
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
