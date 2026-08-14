# -*- coding: utf-8 -*-
"""决策变更事件测试（META_ARBITER 设计 §3.2）.

覆盖:
  - schema: kind 校验 / before-after / actor / status
  - 双写: EventLog + CorrectionJournal 都记录
  - 回看: recent() git log 语义（倒序, 可过滤 kind）
  - 介入: comment/status=rejected 追加, 不打断执行
  - engine 装配: bootstrap 后 _decision_bus 可用
"""
from __future__ import annotations

import os
import tempfile

import pytest

from core.agent.blueprint.decision_event import DecisionEvent, DecisionEventBus, VALID_KINDS


class TestSchema:
    """DecisionEvent 数据契约。"""

    def test_valid_kinds(self):
        # 2026-08-14: exec_tree_audit 加入（执行树消费器审计事件, 检测层）
        assert VALID_KINDS == {"strategy_switch", "plan_gate", "meta_advice",
                               "user_correction", "exec_tree_audit"}

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValueError):
            DecisionEvent(kind="nonsense", dimension="plan")

    def test_to_dict_serializable(self):
        ev = DecisionEvent(
            kind="strategy_switch", dimension="plan",
            before={"mode": "handcraft"}, after={"mode": "forge"},
            reason="预计超时", actor="meta", turn=3,
        )
        d = ev.to_dict()
        assert d["kind"] == "strategy_switch"
        assert d["after"]["mode"] == "forge"
        assert d["actor"] == "meta"
        assert d["status"] == "applied"

    def test_object_before_serialized(self):
        class FakePlan:
            def __str__(self):
                return "<plan handcraft>"
        ev = DecisionEvent(kind="meta_advice", dimension="subgraph",
                           before=FakePlan(), after="forge")
        d = ev.to_dict()
        assert d["before"] == "<plan handcraft>"


class TestBus:
    """DecisionEventBus 双写 + 回看。"""

    def _bus(self):
        tmp = tempfile.mkdtemp(prefix="decision_")
        # EventLog 用内存/临时 db
        from core.agent.api.api_event_log import EventLog
        el = EventLog(db_path=os.path.join(tmp, "event_log.db"))
        el.open()
        # CorrectionJournal 用临时 JSONL
        from core.agent.v4.cognitive.correction_journal import CorrectionJournal
        journal = CorrectionJournal(path=os.path.join(tmp, "journal.jsonl"))
        bus = DecisionEventBus(event_log=el, journal=journal)
        return bus, el, journal, tmp

    def test_record_dual_write(self):
        bus, el, journal, tmp = self._bus()
        bus.log(kind="strategy_switch", dimension="plan",
                before="handcraft", after="forge", reason="超时", actor="meta", turn=1)
        # EventLog 有记录
        events = el.recent(limit=10)
        assert len(events) >= 1
        # CorrectionJournal 有记录
        entries = journal.entries_since(limit=10)
        assert len(entries) >= 1
        assert entries[0].before == "handcraft"
        assert entries[0].after == "forge"
        bus._event_log.close()

    def test_recent_reversed_and_filtered(self):
        bus, el, journal, tmp = self._bus()
        bus.log(kind="meta_advice", dimension="strategy", after="hybrid", turn=1)
        bus.log(kind="user_correction", dimension="constraint",
                comment="禁止下载", status="rejected", turn=2)
        bus.log(kind="strategy_switch", dimension="plan", after="forge", turn=3)
        recent = bus.recent(limit=2)
        assert len(recent) == 2
        assert recent[0]["turn"] == 3  # 倒序, 最新在前
        only_switch = bus.recent(kind="strategy_switch")
        assert len(only_switch) == 1
        assert only_switch[0]["after"] == "forge"
        bus._event_log.close()

    def test_intervention_comment_rejected(self):
        """用户介入: 追加 comment + status=rejected, 不影响后续记录."""
        bus, el, journal, tmp = self._bus()
        bus.log(kind="strategy_switch", dimension="plan", after="forge", turn=1)
        bus.log(kind="user_correction", dimension="plan",
                before="forge", after="handcraft", comment="还是手搓吧",
                actor="user", status="rejected", turn=2)
        evs = bus.all()
        assert len(evs) == 2
        assert evs[1]["actor"] == "user"
        assert evs[1]["status"] == "rejected"
        assert evs[1]["comment"] == "还是手搓吧"
        bus._event_log.close()


class TestEngineAssembly:
    """bootstrap 后 engine._decision_bus 可用。"""

    def test_engine_has_decision_bus(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        from core.agent.llm_providers.mock_provider import MockProvider
        e = CognitiveRuntimeEngine(llm_provider=MockProvider("mock", {}))
        e.bootstrap()
        bus = getattr(e, "_decision_bus", None)
        assert bus is not None, "_decision_bus 未装配"
        d = bus.log(kind="meta_advice", dimension="strategy",
                    after="hybrid", reason="bootstrap test", turn=0)
        assert d["kind"] == "meta_advice"
        assert len(bus.all()) >= 1
        e.stop()
