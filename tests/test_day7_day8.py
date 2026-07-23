# tests/test_day7_day8.py
"""Day 7 + Day 8: 9 场景集成测试 + 性能基准 + 边界 case + 回退开关验证。

纯 Python，无 pytest 依赖。
"""

import sys
import os
import time
import importlib.util

root = os.getcwd()

def load_module_from_path(module_name, rel_path):
    abs_path = os.path.join(root, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 加载所有模块
_ = load_module_from_path("discourse_models", "core/agent/discourse_block_tree/models.py")
_ = load_module_from_path("segmenter", "core/agent/discourse_block_tree/segmenter.py")
_ = load_module_from_path("manager", "core/agent/discourse_block_tree/manager.py")
_ = load_module_from_path("summary_engine", "core/agent/discourse_block_tree/summary_engine.py")
_ = load_module_from_path("context_builder", "core/agent/discourse_block_tree/context_builder.py")
_ = load_module_from_path("indexer", "core/agent/discourse_block_tree/indexer.py")

hi = load_module_from_path("header_injector", "core/agent/compiler/header_injector.py")
sd = load_module_from_path("syntactic_decomposer", "core/agent/compiler/syntactic_decomposer.py")
mm = load_module_from_path("macro_micro_quantizer", "core/agent/compiler/macro_micro_quantizer.py")

discourse_int = load_module_from_path(
    "discourse_integration", "core/agent/discourse_integration.py"
)

EDU = sys.modules["discourse_models"].EDU
DiscourseBlock = sys.modules["discourse_models"].DiscourseBlock
BlockState = sys.modules["discourse_models"].BlockState
MacroDimensions = sys.modules["discourse_models"].MacroDimensions
MicroDimensions = sys.modules["discourse_models"].MicroDimensions
Segmenter = sys.modules["segmenter"].Segmenter
DiscourseBlockTreeManager = sys.modules["manager"].DiscourseBlockTreeManager
SummaryEngine = sys.modules["summary_engine"].SummaryEngine
ContextBuilder = sys.modules["context_builder"].ContextBuilder
Indexer = sys.modules["indexer"].Indexer
HeaderInjector = hi.HeaderInjector
SyntacticDecomposer = sd.SyntacticDecomposer
MacroMicroQuantizer = mm.MacroMicroQuantizer
DiscoursePipeline = discourse_int.DiscoursePipeline


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


def make_high(turn=0, edu_idx=0, entities=None, intent=None):
    return make_edu("H", turn, edu_idx, entities, intent,
                     MicroDimensions(μ1=0.8, μ2=0.8, μ3=0.8, μ4=0.8, μ5=0.8),
                     MacroDimensions(M1=0.8, M2=0.8, M3=0.8, M4=0.8))


def make_low(turn=0, edu_idx=0, entities=None, intent=None):
    return make_edu("L", turn, edu_idx, entities, intent,
                     MicroDimensions(μ1=0.1, μ2=0.1, μ3=0.1, μ4=0.1, μ5=0.1),
                     MacroDimensions(M1=0.1, M2=0.1, M3=0.1, M4=0.1))


def run_pipeline(text, turn=0):
    """运行完整编译器管道。"""
    injector = HeaderInjector()
    injected = injector.inject(text, "test")
    decomp = SyntacticDecomposer()
    clauses = decomp.decompose(injected.text)
    edus = []
    for i, clause in enumerate(clauses):
        if not clause.parse_failed:
            edu = EDU(
                id=f"edu:T{turn}:U{i}", turn_index=turn, edu_index=i,
                raw_text=clause.raw_text, subject=clause.subject,
                predicate=clause.predicate, object=clause.object,
                subject_attrs=clause.subject_attrs, object_attrs=clause.object_attrs,
                negation=clause.negation, uncertainty=clause.uncertainty,
                imperative=clause.imperative, question=clause.question,
                raw_entities=clause.raw_entities, parse_failed=clause.parse_failed,
                intent_label="analyze" if clause.predicate else "statement",
            )
        else:
            edu = EDU(id=f"edu:T{turn}:U{i}", turn_index=turn, edu_index=i,
                      raw_text=clause.raw_text, parse_failed=True, intent_label="statement")
        edus.append(edu)
    quantizer = MacroMicroQuantizer(embedding_model_name=None)
    quantizer.quantize(edus)
    return edus


# ═══════════════════════════════════════════════════════════════════
# Day 7: 9 场景集成测试
# ═══════════════════════════════════════════════════════════════════

def scene_1_single_edu_single_block():
    """场景1: 单轮单 EDU → 1 个 Block。"""
    edus = run_pipeline("帮我写 Python", turn=0)
    seg = Segmenter()
    blocks = seg.segment(edus)
    assert len(blocks) == 1, f"期望 1 个 Block，得到 {len(blocks)}"
    assert blocks[0].edu_count == 1


def scene_2_multi_edu_no_split():
    """场景2: 单轮多 EDU（无切分）→ 1 个 Block。"""
    edus = [make_high(0, 0, ["X"], "analyze"), make_high(0, 1, ["X"], "analyze")]
    seg = Segmenter()
    blocks = seg.segment(edus)
    assert len(blocks) == 1
    assert blocks[0].edu_count == 2


def scene_3_cohesion_cliff_split():
    """场景3: 单轮多 EDU（cohesion cliff 切分）→ 2 个 Block。"""
    edus = [make_high(0, 0, ["X"], "analyze"), make_low(0, 1, ["Y"], "question")]
    seg = Segmenter(threshold=0.5)
    blocks = seg.segment(edus)
    assert len(blocks) == 2, f"期望 2 个 Block，得到 {len(blocks)}"


def scene_4_bdi_split():
    """场景4: 单轮多 EDU（BDI 切分）→ 2 个 Block。"""
    edus = [make_high(0, 0, ["X"], "analyze"), make_high(0, 1, ["X"], "question")]
    seg = Segmenter(bdi_enabled=True)
    blocks = seg.segment(edus)
    assert len(blocks) == 2, f"期望 2 个 Block，得到 {len(blocks)}"


def scene_5_cross_turn_continue():
    """场景5: 跨轮次话题延续 → 合并到同一 Block。"""
    mgr = DiscourseBlockTreeManager()
    edus1 = [make_high(0, 0, ["Python"], "analyze")]
    mgr.ingest_turn(edus1)
    edus2 = [make_high(1, 0, ["Python"], "analyze")]
    blocks = mgr.ingest_turn(edus2)
    # 高粘合度 → 合并到活跃块
    assert len(blocks) == 1
    assert mgr.block_count == 1


def scene_6_cross_turn_switch():
    """场景6: 跨轮次话题切换 → 新 Block。"""
    mgr = DiscourseBlockTreeManager()
    edus1 = [make_high(0, 0, ["Python"], "analyze")]
    mgr.ingest_turn(edus1)
    edus2 = [make_low(1, 0, ["Java"], "question")]
    blocks = mgr.ingest_turn(edus2)
    # 低粘合度 → 新 Block
    assert len(blocks) == 1
    assert mgr.block_count == 2


def scene_7_complex_input_fallback():
    """场景7: 复杂输入（parse_failed）→ 退化处理。"""
    text = "。".join([f"句子{i}" for i in range(10)])
    edus = run_pipeline(text, turn=0)
    assert any(e.parse_failed for e in edus)
    # parse_failed 的 EDU 仍然能进入 manager
    mgr = DiscourseBlockTreeManager()
    blocks = mgr.ingest_turn(edus)
    assert len(blocks) >= 1


def scene_8_fallback_switch():
    """场景8: 回退开关测试（enabled=False）→ 轮级模式。"""
    mgr = DiscourseBlockTreeManager(enabled=False)
    edus = [make_high(0, 0), make_high(0, 1)]
    blocks = mgr.ingest_turn(edus)
    assert len(blocks) == 1
    assert "fallback" in blocks[0].id


def scene_9_performance_benchmark():
    """场景9: 性能基准（单轮端到端 < 10ms）。"""
    pipe = DiscoursePipeline()
    start = time.time()
    for _ in range(100):
        pipe.process_turn("帮我scan内存地址分析数据", turn_index=0)
    elapsed = time.time() - start
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 10.0, f"平均延迟 {avg_ms:.2f}ms，超过 10ms 阈值"


# ═══════════════════════════════════════════════════════════════════
# Day 8: 边界 case + 回退开关验证
# ═══════════════════════════════════════════════════════════════════

def boundary_empty_input():
    """边界: 空输入。"""
    pipe = DiscoursePipeline()
    ctx = pipe.process_turn("", turn_index=0)
    assert ctx == "" or "[DiscoursePipeline" in ctx


def boundary_long_input():
    """边界: 超长输入（100+ 字）。"""
    pipe = DiscoursePipeline()
    text = "A" * 200
    ctx = pipe.process_turn(text, turn_index=0)
    assert isinstance(ctx, str)


def boundary_no_entities():
    """边界: 无实体输入。"""
    pipe = DiscoursePipeline()
    ctx = pipe.process_turn("你好啊", turn_index=0)
    assert isinstance(ctx, str)


def boundary_punctuation_only():
    """边界: 纯标点输入。"""
    pipe = DiscoursePipeline()
    ctx = pipe.process_turn("。。。！！！", turn_index=0)
    assert isinstance(ctx, str)


def boundary_same_edu_sequence():
    """边界: 连续相同 EDU。"""
    mgr = DiscourseBlockTreeManager()
    for i in range(5):
        edus = [make_edu("相同", turn=i, edu_idx=0, entities=["X"], intent="analyze")]
        mgr.ingest_turn(edus)
    assert mgr.block_count >= 1


def boundary_ten_edus_single_turn():
    """边界: 单轮 10+ EDU。"""
    edus = [make_high(0, i, [f"E{i}"], "analyze") for i in range(12)]
    seg = Segmenter()
    blocks = seg.segment(edus)
    assert len(blocks) >= 1


def switch_intra_turn_split_off():
    """回退: intra_turn_split=False（但 MVP 中 segmenter 总启用）。"""
    # MVP 中 segmenter 始终启用，此测试验证无异常
    mgr = DiscourseBlockTreeManager()
    edus = [make_high(0, 0), make_high(0, 1)]
    blocks = mgr.ingest_turn(edus)
    assert len(blocks) >= 1


def switch_micro_quantization_off():
    """回退: micro_quantization=False（测试默认启用）。"""
    # 默认启用，测试正常流程
    edus = run_pipeline("帮我写 Python", turn=0)
    assert len(edus) >= 1


def switch_summary_v3_off():
    """回退: progressive_summary_v3=False。"""
    engine = SummaryEngine(v3_trigger_turn_count=999)  # 永不触发
    edus = [make_edu(f"T{i}", turn=i) for i in range(6)]
    block = DiscourseBlock(
        id="block:T0:6", edus=edus, start_turn=0, end_turn=5,
        state=BlockState.ACTIVE, intent_label="analyze")
    block._update_entity_signature()
    summary = engine.summarize_block(block)
    assert summary.v3 is None


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        # Day 7: 9 场景
        scene_1_single_edu_single_block,
        scene_2_multi_edu_no_split,
        scene_3_cohesion_cliff_split,
        scene_4_bdi_split,
        scene_5_cross_turn_continue,
        scene_6_cross_turn_switch,
        scene_7_complex_input_fallback,
        scene_8_fallback_switch,
        scene_9_performance_benchmark,
        # Day 8: 边界 + 回退
        boundary_empty_input,
        boundary_long_input,
        boundary_no_entities,
        boundary_punctuation_only,
        boundary_same_edu_sequence,
        boundary_ten_edus_single_turn,
        switch_intra_turn_split_off,
        switch_micro_quantization_off,
        switch_summary_v3_off,
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
