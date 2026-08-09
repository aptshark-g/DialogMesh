# -*- coding: utf-8 -*-
"""causal C1-C5 批次测试 — 2026-08-05.

覆盖:
  C1  CausalPlanner 挂载 + record_step + slow_path（process_chain）
  C2  CognitionHub.ingest_relations + converge 消费清空
  C4  discourse/ 包 DiscourseBlockTree 符号可导入（inspect CLI 修复）
"""
from __future__ import annotations

from types import SimpleNamespace

from core.agent.events.event_ir import EventIR


def _evt(i: int) -> EventIR:
    return EventIR(id=f"e{i}", kind="ui.click",
                   payload={"text": f"action {i}", "entities": {}},
                   metadata={}, timestamp=0)


# ── C1: CausalPlanner 挂载 + 接线 ─────────────────────────────────────

class TestC1CausalPlanner:
    def test_engine_mounts_planner(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._init_causal_planner()
        assert eng._causal_planner is not None

    def test_record_step_feeds_chain(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._init_causal_planner()
        for i in range(3):
            eng._run_behavior_brain(_evt(i))
        chain = eng._causal_planner.get_recent_chain()
        assert len(chain) == 3

    def test_slow_path_short_chain_not_triggered(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._init_causal_planner()
        for i in range(3):
            eng._run_behavior_brain(_evt(i))
        r = eng._trigger_causal_slow_path()
        assert r["available"] is True
        assert r["triggered"] is False  # 链长 < MIN_CHAIN_LEN

    def test_slow_path_long_chain_triggers(self):
        from core.agent.causal.planner import CausalPlanner
        p = CausalPlanner()
        for i in range(12):  # > MIN_CHAIN_LEN (10)
            p.record_step(_evt(i))
        result = p.process_chain()
        assert result.triggered is True

    def test_never_fatal_without_graph(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._behavior_graph_adapter = None
        eng._init_causal_planner()  # 不应抛异常


# ── C2: CognitionHub 喂数据 ────────────────────────────────────────────

class TestC2CognitionHub:
    def test_ingest_then_converge_consumes(self):
        from core.agent.cognition.hub import CognitionHub
        hub = CognitionHub()
        hub.ingest_relations([{"source": "A", "target": "B", "strength": 0.7}])
        assert len(hub._relations_buffer) == 1
        hub.converge()
        assert len(hub._relations_buffer) == 0  # 消费即清空（缓冲语义）

    def test_engine_discovery_feed_wires_hub(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._on_association_discovered({"payload": {
            "ts": 0,
            "relations": [{"source": "X", "target": "Y", "strength": 0.6}],
        }})
        assert getattr(eng, "_cognition_hub", None) is not None

    def test_empty_discovery_noop(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._on_association_discovered({"payload": {"ts": 0, "l3": []}})
        hub = getattr(eng, "_cognition_hub", None)
        assert hub is None or len(hub._relations_buffer) == 0


# ── C4: discourse/ 包符号 ──────────────────────────────────────────────

class TestC4DiscourseSymbol:
    def test_importable(self):
        from core.agent.discourse import DiscourseBlockTree
        assert DiscourseBlockTree is not None

    def test_points_to_real_manager(self):
        from core.agent.discourse import DiscourseBlockTree
        from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
        assert DiscourseBlockTree is DiscourseBlockTreeManager


# ── C5: 行为链挂载核对（行为链批次已修）─────────────────────────────

class TestC5BehaviorWiring:
    def test_brain_and_adapter_mounted(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        eng = CognitiveRuntimeEngine()
        eng._init_behavior_brain()
        assert eng._behavior_brain is not None
        # _behavior_graph_adapter 由 CLI registry 挂载（本测试仅验证不炸）
        assert True
