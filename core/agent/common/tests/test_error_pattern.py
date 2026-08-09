# -*- coding: utf-8 -*-
"""E5/E6 错误模式反思测试（ERROR_META_REFLECTION §三）.

覆盖:
  - classify_error 三类分类（type_mismatch/encoding/serialization）
  - E5 滑动窗口计数 ≥ 阈值 → meta_advice 事件（自动）
  - E6 maybe_user_explicit 关键词检测
  - E6 explicit_trigger → 最高优先级反思事件
  - executor 节点失败自动上报
  - engine.trigger_error_reflection 接线
"""
from __future__ import annotations

from core.agent.common.error_pattern import (
    ErrorPatternTracker, classify_error, maybe_user_explicit,
)
from core.agent.blueprint.decision_event import DecisionEventBus


# ═══════════════════════════════════════════════════════════════
# classify_error
# ═══════════════════════════════════════════════════════════════

def test_classify_type_mismatch():
    assert classify_error("TypeError: 'NoneType' object is not subscriptable") == "type_mismatch"
    assert classify_error("missing required args: ['path']") == "type_mismatch"
    assert classify_error("KeyError: 'foo'") == "type_mismatch"


def test_classify_encoding():
    assert classify_error("utf-8 codec can't decode") == "encoding"
    assert classify_error("乱码 ??????") == "encoding"


def test_classify_serialization():
    assert classify_error("Object of type set is not JSON serializable") == "serialization"
    assert classify_error("json decode error") == "serialization"


def test_classify_unknown():
    assert classify_error("something random happened") == "unknown"
    assert classify_error("") == "unknown"


# ═══════════════════════════════════════════════════════════════
# E5 自动触发
# ═══════════════════════════════════════════════════════════════

def test_e5_threshold_emits_meta_advice():
    bus = DecisionEventBus()
    t = ErrorPatternTracker(decision_bus=bus, threshold=3, window=10)
    for i in range(2):
        r = t.record("type_mismatch", example=f"err {i}")
        assert r["triggered"] is False
    r3 = t.record("type_mismatch", example="err 2")
    assert r3["triggered"] is True
    advices = bus.recent(kind="meta_advice")
    assert len(advices) == 1
    assert advices[0]["dimension"] == "error_pattern.type_mismatch"
    assert advices[0]["status"] == "proposed"
    assert "3 次" in advices[0]["reason"]


def test_e5_no_duplicate_until_window_resets():
    """达到阈值后继续计数, 不重复发事件（只在跨窗口重置后再次触发）."""
    bus = DecisionEventBus()
    t = ErrorPatternTracker(decision_bus=bus, threshold=3, window=3)
    for i in range(6):
        t.record("encoding", example=f"e{i}")
    # 阈值只触发一次（窗口内计数累计, 不每 3 次重复发）
    advices = bus.recent(kind="meta_advice")
    assert len(advices) == 1


def test_e5_no_bus_safe():
    """无 bus 时安全降级（内存计数, 不崩）."""
    t = ErrorPatternTracker(threshold=3)
    for i in range(3):
        r = t.record("unknown", example="x")
    assert r["triggered"] is True
    assert t.counts()["unknown"] == 3


def test_e5_summary():
    t = ErrorPatternTracker(threshold=3)
    t.record("encoding", example="bad")
    s = t.summary()
    assert s["threshold"] == 3
    assert s["counts"]["encoding"] == 1


# ═══════════════════════════════════════════════════════════════
# E6 用户明示
# ═══════════════════════════════════════════════════════════════

def test_e6_keyword_detection():
    assert maybe_user_explicit("这个错误反复出现")
    assert maybe_user_explicit("又失败了，还是老样子")
    assert maybe_user_explicit("每次都这样，很烦")
    assert not maybe_user_explicit("帮我查一下论文")
    assert not maybe_user_explicit("")


def test_e6_explicit_trigger_high_priority():
    bus = DecisionEventBus()
    t = ErrorPatternTracker(decision_bus=bus)
    r = t.explicit_trigger(reason="用户说反复出现")
    assert r["triggered"] is True
    advices = bus.recent(kind="meta_advice")
    assert len(advices) == 1
    assert advices[0]["actor"] == "user"
    assert advices[0]["dimension"] == "error_pattern.user_explicit"
    assert "用户明示" in advices[0]["reason"]


# ═══════════════════════════════════════════════════════════════
# executor 自动上报
# ═══════════════════════════════════════════════════════════════

def test_executor_reports_node_error():
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.executor import BlueprintExecutor
    from core.agent.common.error_pattern import ErrorPatternTracker

    bus = DecisionEventBus()
    tracker = ErrorPatternTracker(decision_bus=bus, threshold=1)

    class _FailExec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"status": "error", "error": "TypeError: boom"}

    ex = _FailExec(decision_bus=bus, error_pattern=tracker)
    dag = BlueprintDAG(
        nodes=[BlueprintNode("pcr_0", "pcr", priority=0),
               BlueprintNode("llm_1", "llm_reply", priority=1)],
        edges=[BlueprintEdge("pcr_0", "llm_1", "route")],
        strategy="TEMPLATE",
    )
    ex.execute(dag, user_text="x")
    advices = bus.recent(kind="meta_advice")
    assert len(advices) == 1
    assert advices[0]["dimension"] == "error_pattern.type_mismatch"


# ═══════════════════════════════════════════════════════════════
# engine 接线
# ═══════════════════════════════════════════════════════════════

def test_engine_trigger_error_reflection():
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    eng = CognitiveRuntimeEngine()
    r = eng.trigger_error_reflection(text="这个错误反复出现")
    assert r["triggered"] is True
    bus = getattr(eng, "_decision_bus", None)
    if bus is not None:
        advices = bus.recent(kind="meta_advice")
        assert any(a["dimension"] == "error_pattern.user_explicit" for a in advices)


def test_engine_trigger_no_keyword_noop():
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    eng = CognitiveRuntimeEngine()
    r = eng.trigger_error_reflection(text="帮我写代码")
    assert r["triggered"] is False
