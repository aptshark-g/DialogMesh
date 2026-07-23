# tests/test_day5.py
"""测试 SummaryEngine + ContextBuilder + Indexer（纯 Python，无 pytest 依赖）。"""

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
se_module = load_module_from_path("summary_engine", "core/agent/discourse_block_tree/summary_engine.py")
cb_module = load_module_from_path("context_builder", "core/agent/discourse_block_tree/context_builder.py")
idx_module = load_module_from_path("indexer", "core/agent/discourse_block_tree/indexer.py")

EDU = models_module.EDU
DiscourseBlock = models_module.DiscourseBlock
BlockState = models_module.BlockState
MacroDimensions = models_module.MacroDimensions
MicroDimensions = models_module.MicroDimensions
SummaryEngine = se_module.SummaryEngine
ContextBuilder = cb_module.ContextBuilder
Indexer = idx_module.Indexer


# ── 辅助函数 ──────────────────────────────────────────────────────

def make_edu(text, turn=0, edu_idx=0, entities=None, intent=None, subject=None, predicate=None, obj=None, negation=False):
    edu = EDU(
        id=f"edu:T{turn}:U{edu_idx}",
        turn_index=turn,
        edu_index=edu_idx,
        raw_text=text,
        raw_entities=entities or [],
        intent_label=intent,
        subject=subject,
        predicate=predicate,
        object=obj,
        negation=negation,
    )
    edu.micro_dimensions = MicroDimensions()
    edu.macro_dimensions = MacroDimensions()
    return edu


def make_block(edus, turn=0, intent=None):
    block = DiscourseBlock(
        id=f"block:T{turn}:0",
        edus=list(edus),
        start_turn=turn,
        end_turn=turn,
        state=BlockState.ACTIVE,
        intent_label=intent,
    )
    block._update_entity_signature()
    return block


# ── SummaryEngine 测试 ──────────────────────────────────────────

def test_v1_single_edu():
    """v1 单轮压缩。"""
    engine = SummaryEngine()
    edu = make_edu("A", subject="User", predicate="likes", obj="Python", entities=["Python"])
    block = make_block([edu])
    summary = engine.summarize_block(block)
    assert summary.v1 is not None
    assert "User" in summary.v1
    assert "likes" in summary.v1
    assert "Python" in summary.v1


def test_v1_negation():
    """v1 否定标记。"""
    engine = SummaryEngine()
    edu = make_edu("A", subject="User", predicate="likes", obj="Java", negation=True)
    block = make_block([edu])
    summary = engine.summarize_block(block)
    assert "NOT" in summary.v1


def test_v2_block_summary():
    """v2 块内合并。"""
    engine = SummaryEngine()
    edus = [
        make_edu("A", entities=["Python"], intent="analyze", subject="User", predicate="likes"),
        make_edu("B", entities=["Python", "Java"], intent="analyze", subject="User", predicate="uses"),
    ]
    block = make_block(edus, intent="analyze")
    summary = engine.summarize_block(block)
    assert summary.v2 is not None
    assert "analyze" in summary.v2
    assert "Python" in summary.v2
    assert "likes" in summary.v2 or "uses" in summary.v2


def test_v3_trigger():
    """v3 在轮次 > 5 时触发。"""
    engine = SummaryEngine(v3_trigger_turn_count=5)
    # 创建跨 6 轮的块
    edus = []
    for turn in range(6):
        edus.append(make_edu(f"T{turn}", turn=turn, entities=["X"], intent="analyze"))
    block = DiscourseBlock(
        id="block:T0:6",
        edus=edus,
        start_turn=0,
        end_turn=5,
        state=BlockState.ACTIVE,
        intent_label="analyze",
    )
    block._update_entity_signature()
    summary = engine.summarize_block(block)
    assert summary.v3 is not None
    assert summary.v3_trigger_reason == "turn_count>5"


def test_v3_no_trigger():
    """v3 在轮次 <= 5 时不触发。"""
    engine = SummaryEngine(v3_trigger_turn_count=5)
    edus = [make_edu("A", turn=0, entities=["X"])]
    block = make_block(edus)
    summary = engine.summarize_block(block)
    assert summary.v3 is None


def test_update_v1():
    """更新 v1 后重置 v2/v3。"""
    engine = SummaryEngine()
    edus = [make_edu("A", subject="User", predicate="likes", obj="Python")]
    block = make_block(edus)
    engine.summarize_block(block)
    assert block.summary.v2 is not None

    # 添加新 EDU
    block.edus.append(make_edu("B", subject="User", predicate="hates", obj="Java"))
    engine.update_v1(block)
    assert block.summary.v1 is not None
    assert block.summary.v2 is None  # 被重置


def test_latest_summary():
    """latest 返回最高可用摘要。"""
    engine = SummaryEngine(v3_trigger_turn_count=5)
    edus = [make_edu(f"T{i}", turn=i, entities=["X"]) for i in range(6)]
    block = DiscourseBlock(
        id="block:T0:6", edus=edus, start_turn=0, end_turn=5,
        state=BlockState.ACTIVE, intent_label="analyze")
    block._update_entity_signature()
    summary = engine.summarize_block(block)
    assert summary.latest == summary.v3


# ── ContextBuilder 测试 ─────────────────────────────────────────

def test_build_context_hot():
    """Hot 块包含完整文本。"""
    builder = ContextBuilder(hot_turns=5)
    edus = [make_edu("A", turn=0)]
    block = make_block(edus, turn=0)
    block.summary = models_module.ProgressiveSummary(v1="summary")
    ctx = builder.build_context([block], current_turn=0)
    assert "Hot" in ctx
    assert "A" in ctx


def test_build_context_warm():
    """Warm 块只包含摘要。"""
    builder = ContextBuilder(hot_turns=2)
    edus = [make_edu("A", turn=0)]
    block = make_block(edus, turn=0)
    block.summary = models_module.ProgressiveSummary(v2="[analyze] entities=Python actions=likes")
    ctx = builder.build_context([block], current_turn=3)  # turn_distance=3, warm (2 < 3 <= 4)
    assert "Warm" in ctx
    assert "analyze" in ctx


def test_build_context_cold():
    """Cold 块包含 v3 或 archived。"""
    builder = ContextBuilder(hot_turns=2)
    edus = [make_edu("A", turn=0)]
    block = make_block(edus, turn=0)
    ctx = builder.build_context([block], current_turn=10)
    assert "Cold" in ctx


def test_build_context_order():
    """上下文按时间顺序排列。"""
    builder = ContextBuilder(hot_turns=5)
    blocks = [
        make_block([make_edu("A", turn=0)], turn=0),
        make_block([make_edu("B", turn=1)], turn=1),
    ]
    ctx = builder.build_context(blocks, current_turn=1)
    assert ctx.index("A") < ctx.index("B")


# ── Indexer 测试 ────────────────────────────────────────────────

def test_index_entity():
    """实体索引。"""
    idx = Indexer()
    edus = [make_edu("A", entities=["Python", "Java"])]
    block = make_block(edus)
    idx.index_block(block)
    assert idx.query_by_entity("Python") == [block.id]
    assert idx.query_by_entity("Java") == [block.id]


def test_index_intent():
    """意图索引。"""
    idx = Indexer()
    edus = [make_edu("A", intent="analyze")]
    block = make_block(edus, intent="analyze")
    idx.index_block(block)
    assert idx.query_by_intent("analyze") == [block.id]


def test_index_turn():
    """轮次索引。"""
    idx = Indexer()
    edus = [make_edu("A", turn=5)]
    block = make_block(edus, turn=5)
    idx.index_block(block)
    assert idx.query_by_turn(5) == [block.id]


def test_remove_block():
    """移除索引。"""
    idx = Indexer()
    block = make_block([make_edu("A", entities=["Python"])])
    idx.index_block(block)
    assert idx.query_by_entity("Python") == [block.id]
    idx.remove_block(block.id)
    assert idx.query_by_entity("Python") == []


def test_frequency_stats():
    """频率统计。"""
    idx = Indexer()
    block1 = make_block([make_edu("A", entities=["Python"], intent="analyze")], turn=0)
    block2 = make_block([make_edu("B", entities=["Python"], intent="analyze")], turn=1)
    idx.index_block(block1)
    idx.index_block(block2)
    assert idx.get_entity_frequency()["Python"] == 2
    assert idx.get_intent_frequency()["analyze"] == 2


def test_clear():
    """清空索引。"""
    idx = Indexer()
    block = make_block([make_edu("A", entities=["Python"])])
    idx.index_block(block)
    idx.clear()
    assert idx.get_entities() == []


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_v1_single_edu,
        test_v1_negation,
        test_v2_block_summary,
        test_v3_trigger,
        test_v3_no_trigger,
        test_update_v1,
        test_latest_summary,
        test_build_context_hot,
        test_build_context_warm,
        test_build_context_cold,
        test_build_context_order,
        test_index_entity,
        test_index_intent,
        test_index_turn,
        test_remove_block,
        test_frequency_stats,
        test_clear,
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
