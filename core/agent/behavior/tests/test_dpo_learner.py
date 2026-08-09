# -*- coding: utf-8 -*-
"""DPO 偏好学习测试（STATE_SNAPSHOT §1.2 粗糙点 + RECOVERY_PLAN §三 3.2）。

覆盖:
  3.1a 可观测 kind 门控（top1==summary 假 reject 池修复）
  3.1b no_response 自对丢弃（(summary, summary) 污染修复）
  3.1c 图权重应用（归一化匹配对齐率）
  3.2  反馈映射 / 阈值触发 / 图权重应用 / 白盒 stats
"""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from core.agent.behavior.dpo_learner import (
    DPOLearner,
    OBSERVABLE_ACTION_TYPES,
    PreferencePair,
)
from core.agent.behavior.models import BehaviorStep, BehaviorEdge


# ── 3.2a 反馈映射 ───────────────────────────────────────────────────────

def test_feedback_mapping_accept():
    d = DPOLearner(min_pairs=1)
    p = d.record("open config", "open config", "accept")
    assert p is not None
    assert p.label == "preferred"
    assert p.weight == 1.0
    assert p.source == "accept"


def test_feedback_mapping_reject():
    d = DPOLearner(min_pairs=1)
    p = d.record("run test", "open log", "reject")
    assert p.label == "dispreferred"
    assert p.weight == 1.0


def test_feedback_mapping_correction_weight():
    d = DPOLearner(min_pairs=1)
    p = d.record("predict A", "actual B", "correction")
    assert p.label == "preferred"
    assert 0.0 < p.weight < 1.0  # 0.8 默认，弱于 accept


def test_invalid_feedback_ignored():
    d = DPOLearner(min_pairs=1)
    assert d.record("a", "b", "unknown_signal") is None
    assert d.record("", "b", "accept") is None


# ── 3.1b no_response 自对丢弃 ───────────────────────────────────────────

def test_no_response_self_pair_dropped():
    d = DPOLearner(min_pairs=1)
    # 无预测时 summary==summary — 不构成偏好信号
    assert d.record("summary", "summary", "no_response") is None
    assert len(d.pairs()) == 0


def test_no_response_with_real_prediction_kept():
    d = DPOLearner(min_pairs=1)
    p = d.record("predicted action", "actual action", "no_response")
    assert p is not None
    assert p.source == "no_response"
    assert p.weight < 1.0  # 弱信号 ×0.3


# ── 3.1a 可观测 kind 门控（brain 侧行为验证）───────────────────────────

def test_observable_action_types_include_tool_ui():
    assert {"ui", "tool", "api", "config", "document"} <= OBSERVABLE_ACTION_TYPES
    assert "dialog" not in OBSERVABLE_ACTION_TYPES


def _brain_with_event():
    from core.agent.behavior.brain import BehaviorBrain, extract_action
    from core.agent.events.event_ir import EventIR
    brain = BehaviorBrain()
    return brain, extract_action, EventIR


def test_dialog_events_do_not_pollute_dpo_pool():
    brain, extract_action, EventIR = _brain_with_event()
    evt = EventIR(id="e1", kind="dialog.message",
                  payload={"text": "用户说了句话"}, metadata={}, timestamp=0)
    summary, atype = extract_action(evt)
    assert atype == "dialog"
    brain.learn_from_event(evt)
    assert len(brain.dpo.pairs()) == 0  # dialog 不进 DPO 池


def test_observable_events_with_prediction_record_pairs():
    brain, extract_action, EventIR = _brain_with_event()
    # 先造一个 pending prediction
    brain._pending_prediction = SimpleNamespace(predicted_top1="open settings")
    evt = EventIR(id="e2", kind="ui.click",
                  payload={"text": "open settings"}, metadata={}, timestamp=0)
    summary, atype = extract_action(evt)
    assert atype == "ui"
    brain.learn_from_event(evt)
    # 可观测 kind + top1 命中 → accept 对
    pairs = brain.dpo.pairs()
    assert len(pairs) == 1
    assert pairs[0].label == "preferred"
    assert pairs[0].source == "accept"


def test_observable_reject_no_fake_pool():
    brain, extract_action, EventIR = _brain_with_event()
    brain._pending_prediction = SimpleNamespace(predicted_top1="open settings")
    evt = EventIR(id="e3", kind="tool.invoke",
                  payload={"text": "run grep"}, metadata={}, timestamp=0)
    brain.learn_from_event(evt)
    pairs = brain.dpo.pairs()
    assert len(pairs) == 1
    assert pairs[0].source == "reject"  # 真实预测 vs 真实动作


# ── 3.2b 阈值触发 ───────────────────────────────────────────────────────

def test_ready_threshold():
    d = DPOLearner(min_pairs=3)
    assert not d.ready()
    for i in range(3):
        d.record(f"pred {i}", f"act {i}", "accept")
    assert d.ready()


@pytest.mark.asyncio
async def test_learn_resets_pool_and_records_count():
    d = DPOLearner(min_pairs=2)
    d.record("a1", "b1", "accept")
    d.record("a2", "b2", "reject")
    deltas = await d.learn()
    assert deltas is not None  # 规则蒸馏回退
    assert d.stats()["learn_count"] == 1
    assert len(d.pairs()) == 0  # 池已重置


# ── 3.2c 图权重应用 + 3.1c 归一化匹配 ──────────────────────────────────

def _graph_with_edge(from_summary="open settings", to_summary="Open Settings"):
    from core.agent.behavior.graph_store import BehaviorGraph
    g = BehaviorGraph()
    fs = BehaviorStep(step_id="s1", action_summary=from_summary, action_type="ui")
    ts = BehaviorStep(step_id="s2", action_summary=to_summary, action_type="ui")
    g.add_step(fs)
    g.add_step(ts)
    g.record_edge(fs, ts)
    return g, ts


def test_apply_exact_match():
    d = DPOLearner(min_pairs=1)
    g, ts = _graph_with_edge(to_summary="open settings")
    d._last_deltas = {"open settings": 0.2}
    edge = list(g.edges.values())[0]
    before = edge.weight
    applied = d.apply_to_graph(g)
    assert applied == 1
    assert edge.weight == min(1.0, before + 0.2)


def test_apply_normalized_match():
    """3.1c: LLM 蒸馏 key 带大小写/空白差异仍命中。"""
    d = DPOLearner(min_pairs=1)
    g, ts = _graph_with_edge(to_summary="Open Settings")
    d._last_deltas = {"open settings": 0.1}  # 大小写不同
    edge = list(g.edges.values())[0]
    before = edge.weight
    applied = d.apply_to_graph(g)
    assert applied == 1
    assert edge.weight == min(1.0, before + 0.1)


def test_apply_no_match_skips():
    d = DPOLearner(min_pairs=1)
    g, _ = _graph_with_edge(to_summary="unrelated action")
    d._last_deltas = {"nothing matches": 0.3}
    assert d.apply_to_graph(g) == 0


def test_apply_clamps_weight():
    d = DPOLearner(min_pairs=1)
    g, _ = _graph_with_edge(to_summary="open settings")
    d._last_deltas = {"open settings": 0.9}  # 超上限
    edge = list(g.edges.values())[0]
    edge.weight = 0.8
    d.apply_to_graph(g)
    assert edge.weight <= 1.0


# ── 3.2d 白盒 stats ─────────────────────────────────────────────────────

def test_stats_whitebox():
    d = DPOLearner(min_pairs=5)
    d.record("a", "b", "accept")
    d.record("c", "d", "reject")
    s = d.stats()
    assert s["pool_size"] == 2
    assert s["by_label"]["preferred"] == 1
    assert s["by_label"]["dispreferred"] == 1
    assert s["by_source"]["accept"] == 1
    assert s["ready"] is False
    assert s["learn_count"] == 0


@pytest.mark.asyncio
async def test_stats_after_learn():
    d = DPOLearner(min_pairs=1)
    d.record("a", "b", "accept")
    await d.learn()
    s = d.stats()
    assert s["learn_count"] == 1
    assert s["pool_size"] == 0
    assert s["last_deltas"] is not None
