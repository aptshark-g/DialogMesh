# tests/test_manager.py
"""测试 DiscourseBlockTreeManager（纯 Python，无 pytest 依赖）。"""

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
manager_module = load_module_from_path("manager", "core/agent/discourse_block_tree/manager.py")

EDU = models_module.EDU
DiscourseBlock = models_module.DiscourseBlock
BlockState = models_module.BlockState
MacroDimensions = models_module.MacroDimensions
MicroDimensions = models_module.MicroDimensions
Segmenter = segmenter_module.Segmenter
DiscourseBlockTreeManager = manager_module.DiscourseBlockTreeManager


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
    return make_edu(text, turn, edu_idx, entities, intent,
        micro=MicroDimensions(μ1=0.8, μ2=0.8, μ3=0.8, μ4=0.8, μ5=0.8),
        macro=MacroDimensions(M1=0.8, M2=0.8, M3=0.8, M4=0.8))


def make_low_cohesion_edu(text, turn=0, edu_idx=0, entities=None, intent=None):
    return make_edu(text, turn, edu_idx, entities, intent,
        micro=MicroDimensions(μ1=0.1, μ2=0.1, μ3=0.1, μ4=0.1, μ5=0.1),
        macro=MacroDimensions(M1=0.1, M2=0.1, M3=0.1, M4=0.1))


# ── 测试函数 ──────────────────────────────────────────────────────

def test_basic_ingest():
    """基本接收轮次。"""
    mgr = DiscourseBlockTreeManager()
    edus = [
        make_high_cohesion_edu("A", turn=0, edu_idx=0),
        make_high_cohesion_edu("B", turn=0, edu_idx=1),
    ]
    blocks = mgr.ingest_turn(edus)
    assert len(blocks) >= 1
    assert mgr.block_count >= 1
    assert mgr.current_turn == 0


def test_state_transition():
    """块状态随轮次距离转换。"""
    mgr = DiscourseBlockTreeManager(hot_turns=2, warm_turns=4)
    # Turn 0: 创建块
    edus0 = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    mgr.ingest_turn(edus0)
    assert mgr.get_latest_block().state == BlockState.ACTIVE

    # Turn 3: 距离 > 2, <= 4 → COOLING
    edus3 = [make_high_cohesion_edu("B", turn=3, edu_idx=0)]
    mgr.ingest_turn(edus3)
    blocks = mgr.get_blocks()
    # 第一个块（end_turn=0）距离 3 → COOLING
    first_block = [b for b in blocks if b.start_turn == 0][0]
    assert first_block.state == BlockState.COOLING

    # Turn 6: 距离 > 4 → COLD
    edus6 = [make_high_cohesion_edu("C", turn=6, edu_idx=0)]
    mgr.ingest_turn(edus6)
    first_block = [b for b in mgr.get_blocks() if b.start_turn == 0][0]
    assert first_block.state == BlockState.COLD


def test_hot_warm_cold_filter():
    """按状态筛选块。"""
    mgr = DiscourseBlockTreeManager(hot_turns=1, warm_turns=2)
    for turn in range(5):
        edus = [make_high_cohesion_edu(f"T{turn}", turn=turn, edu_idx=0)]
        mgr.ingest_turn(edus)

    hot = mgr.get_hot_blocks()
    warm = mgr.get_warm_blocks()
    cold = mgr.get_cold_blocks()

    # Turn 4 最新 → ACTIVE
    assert len(hot) >= 1
    # Turn 2,3 → COOLING
    assert len(warm) >= 1
    # Turn 0,1 → COLD
    assert len(cold) >= 1


def test_block_routing_merge():
    """高粘合度块路由 → 合并到活跃块。"""
    mgr = DiscourseBlockTreeManager()
    # 第一个块
    edus1 = [make_high_cohesion_edu("A", turn=0, edu_idx=0, entities=["X"], intent="analyze")]
    blocks1 = mgr.ingest_turn(edus1)
    assert len(blocks1) == 1
    block1 = blocks1[0]

    # 第二个块：高粘合度（相同实体 + 相同意图）→ 合并
    edus2 = [make_high_cohesion_edu("B", turn=0, edu_idx=1, entities=["X"], intent="analyze")]
    blocks2 = mgr.ingest_turn(edus2)
    # 合并后应返回同一个块
    assert len(blocks2) == 1
    assert blocks2[0].id == block1.id
    assert blocks2[0].edu_count == 2  # 两个 EDU 合并


def test_block_routing_new():
    """低粘合度块路由 → 新建块。"""
    mgr = DiscourseBlockTreeManager()
    # 第一个块
    edus1 = [make_high_cohesion_edu("A", turn=0, edu_idx=0, entities=["X"], intent="analyze")]
    mgr.ingest_turn(edus1)
    block1 = mgr.get_latest_block()

    # 第二个块：低粘合度（不同实体 + 不同意图）→ 新块
    edus2 = [make_low_cohesion_edu("B", turn=0, edu_idx=1, entities=["Y"], intent="question")]
    blocks2 = mgr.ingest_turn(edus2)
    assert len(blocks2) == 1
    block2 = blocks2[0]
    assert block2.id != block1.id
    assert mgr.block_count == 2


def test_fallback_mode():
    """退化模式：enabled=False 时每个轮次作为一个整块。"""
    mgr = DiscourseBlockTreeManager(enabled=False)
    edus = [
        make_edu("A", turn=0, edu_idx=0),
        make_edu("B", turn=0, edu_idx=1),
    ]
    blocks = mgr.ingest_turn(edus)
    assert len(blocks) == 1
    assert blocks[0].edu_count == 2
    assert "fallback" in blocks[0].id


def test_get_block_by_id():
    """通过 ID 获取块。"""
    mgr = DiscourseBlockTreeManager()
    edus = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    blocks = mgr.ingest_turn(edus)
    block_id = blocks[0].id
    found = mgr.get_block_by_id(block_id)
    assert found is not None
    assert found.id == block_id


def test_get_latest_block():
    """获取最新块。"""
    mgr = DiscourseBlockTreeManager()
    assert mgr.get_latest_block() is None
    edus = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    mgr.ingest_turn(edus)
    assert mgr.get_latest_block() is not None


def test_active_block():
    """活跃块追踪。"""
    mgr = DiscourseBlockTreeManager()
    assert mgr.get_active_block() is None
    edus = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    mgr.ingest_turn(edus)
    assert mgr.get_active_block() is not None


def test_reset():
    """重置状态。"""
    mgr = DiscourseBlockTreeManager()
    edus = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    mgr.ingest_turn(edus)
    assert mgr.block_count == 1
    mgr.reset()
    assert mgr.block_count == 0
    assert mgr.get_latest_block() is None
    assert mgr.current_turn == 0


def test_serialization():
    """序列化状态。"""
    mgr = DiscourseBlockTreeManager()
    edus = [make_high_cohesion_edu("A", turn=0, edu_idx=0)]
    mgr.ingest_turn(edus)
    data = mgr.to_dict()
    assert "current_turn" in data
    assert "block_count" in data
    assert data["block_count"] == 1


def test_multi_turn_blocks():
    """多轮次创建多个块。"""
    mgr = DiscourseBlockTreeManager()
    for turn in range(3):
        edus = [make_low_cohesion_edu(f"T{turn}", turn=turn, edu_idx=0, entities=[f"E{turn}"])]
        mgr.ingest_turn(edus)
    assert mgr.block_count == 3


# ── 测试运行器 ────────────────────────────────────────────────────

def run_tests():
    tests = [
        test_basic_ingest,
        test_state_transition,
        test_hot_warm_cold_filter,
        test_block_routing_merge,
        test_block_routing_new,
        test_fallback_mode,
        test_get_block_by_id,
        test_get_latest_block,
        test_active_block,
        test_reset,
        test_serialization,
        test_multi_turn_blocks,
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
