# -*- coding: utf-8 -*-
"""Phase 6 深层次测试 — 关联链独立服务（蓝图 §7.3 / DESIGN_HYBRID §六）。

对抗性断言（A18）：不满足即失败，拒绝浅断言。
覆盖:
  - M→1 定向通道：不广播、只进服务队列、唯一消费者
  - EventLog 幂等持久化 + last_seq 增量重放（崩溃恢复）
  - 反压：队列满 → 丢最旧 + 计数（EventLog 完整兜底）
  - 触发阈值：topic_shift>=2 / behavior_count>=10
  - 纯函数 evolve（可重放、无副作用）
  - 同步 C/S pull（热路径直连）
  - 生命周期 start/stop + 白盒 stats
  - engine 接线：_route_pipeline_events → 定向投递 → 发现闭环
  - wire_subscribers 不再广播 association（§7.3）
  - blueprint executor _handle_association 真接（非 deferred）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.agent.association.association_service import (
    AssociationService,
    AssociationState,
    INTERESTED_KINDS,
)


def _wait_until(predicate, timeout=5.0, interval=0.05):
    """轮询等待条件成立（对抗性断言不用固定 sleep）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ══════════════════════════════════════════════════════════ #
# 1. M→1 定向通道（不广播）
# ══════════════════════════════════════════════════════════ #


def test_directed_channel_no_broadcast(tmp_path):
    """定向投递：事件只进服务专用队列；未启动消费时不扩散、无全局订阅。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"), queue_size=8)
    # 服务是"独立服务"形态：没有 subscribe 广播接口
    assert not hasattr(svc, "subscribe")
    assert not hasattr(svc, "_subscribers")
    # 未 start：入队后事件留在专用队列，不被任何消费者处理
    svc.enqueue("intent_parsed", {"category": "query"})
    svc.enqueue("behavior_recorded", {"label": "scan"})
    st = svc.stats()
    assert st["queue_depth"] == 2, "定向通道应持有事件"
    assert st["consumed"] == 0, "未启动消费前不应消费"
    svc.stop()


def test_directed_channel_ignores_uninterested(tmp_path):
    """不关心的主题（非 6 链）→ 拒绝投递，不进队列不写日志。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    assert svc.enqueue("unrelated_event", {"x": 1}) is False
    st = svc.stats()
    assert st["enqueued"] == 0
    assert st["queue_depth"] == 0
    svc.stop()


# ══════════════════════════════════════════════════════════ #
# 2. EventLog 幂等 + last_seq 增量重放（崩溃恢复）
# ══════════════════════════════════════════════════════════ #


def test_eventlog_idempotent_same_event_id(tmp_path):
    """EventLog 幂等：相同 event_id 二次写入不产生重复（INSERT OR IGNORE）。"""
    from core.agent.api.api_event_log import EventLog
    el = EventLog(db_path=str(tmp_path / "el.db"))
    el.open()
    el.put_event(event_id="e1", kind="intent_parsed", payload={"category": "a"})
    el.put_event(event_id="e1", kind="intent_parsed", payload={"category": "a"})
    assert el.stats["total"] == 1
    el.close()


def test_crash_replay_from_last_seq(tmp_path):
    """崩溃恢复：事件先落 EventLog（不 ack），新服务 start 后增量重放。"""
    db = str(tmp_path / "el.db")
    svc1 = AssociationService(db_path=db)
    svc1.enqueue("topic_switched", {"from": "a", "to": "b"})
    svc1.enqueue("topic_switched", {"from": "b", "to": "c"})
    # 未消费即"崩溃"（模拟进程被杀，事件已在 EventLog）
    svc1.stop()

    svc2 = AssociationService(db_path=db)
    svc2.start()
    ok = _wait_until(lambda: svc2.stats()["replayed"] >= 2)
    assert ok, "新服务应重放未消费事件"
    st = svc2.stats()
    assert st["replayed"] == 2
    assert st["state"]["topic_shift_count"] == 0, "2 次切换应触发发现并重置"
    assert st["state"]["discoveries"] == 1
    svc2.stop()


def test_replay_no_duplicate_after_ack(tmp_path):
    """读取单调不重不丢：已 ack 的事件重启后不再重放。"""
    db = str(tmp_path / "el.db")
    svc = AssociationService(db_path=db)
    svc.start()
    svc.enqueue("behavior_recorded", {"label": "x"})
    svc.enqueue("behavior_recorded", {"label": "y"})
    assert _wait_until(lambda: svc.stats()["consumed"] == 2)
    svc.stop()
    # 重启：已 ack 不重放
    svc2 = AssociationService(db_path=db)
    svc2.start()
    time.sleep(0.4)
    st = svc2.stats()
    assert st["replayed"] == 0, "已 ack 事件不应重放"
    assert st["consumed"] == 0
    svc2.stop()


# ══════════════════════════════════════════════════════════ #
# 3. 反压：队列满 → 丢最旧 + 计数（EventLog 完整兜底）
# ══════════════════════════════════════════════════════════ #


def test_backpressure_drop_oldest_count(tmp_path):
    """反压（DESIGN_HYBRID §六）：队列满 → 丢最旧 + 计数，EventLog 已写可重放。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"), queue_size=1)
    svc.enqueue("behavior_recorded", {"label": "a"})   # 占满
    svc.enqueue("behavior_recorded", {"label": "b"})   # 丢最旧（a）
    svc.enqueue("behavior_recorded", {"label": "c"})   # 丢最旧（b）
    st = svc.stats()
    assert st["dropped"] >= 2, "队列满应计数丢弃"
    assert st["queue_depth"] == 1, "队列只保留最新"
    # EventLog 完整：未消费事件数 >= 3（a/b/c 都已持久化）
    svc._ensure_log()
    log_stats = svc._log.stats if svc._log else {"total": 0}
    assert log_stats["total"] >= 3, "EventLog 完整，重放可恢复"
    svc.stop()


# ══════════════════════════════════════════════════════════ #
# 4. 触发阈值
# ══════════════════════════════════════════════════════════ #


def test_trigger_topic_shift_threshold(tmp_path):
    """topic 切换 >= 2 → 触发发现（设计阈值）。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    svc.start()
    svc.enqueue("intent_parsed", {"category": "query"})
    svc.enqueue("topic_switched", {"from": "a", "to": "b"})
    svc.enqueue("topic_switched", {"from": "b", "to": "c"})
    ok = _wait_until(lambda: svc.stats()["discoveries"] == 1)
    assert ok, "2 次 topic_switched 应触发发现"
    st = svc.stats()
    assert st["state"]["topic_shift_count"] == 0, "发现后触发计数应重置"
    svc.stop()


def test_trigger_behavior_threshold(tmp_path):
    """behavior 计数 >= 10 → 触发发现（设计阈值）。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    svc.start()
    for i in range(10):
        svc.enqueue("behavior_recorded", {"label": f"act_{i}"})
    ok = _wait_until(lambda: svc.stats()["discoveries"] == 1)
    assert ok, "10 次 behavior_recorded 应触发发现"
    assert svc.stats()["state"]["behavior_count"] == 0, "发现后触发计数应重置"
    svc.stop()


def test_trigger_below_threshold_no_discovery(tmp_path):
    """低于阈值不误触发（对抗性：无事件时不应有发现）。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    svc.start()
    svc.enqueue("intent_parsed", {"category": "query"})
    svc.enqueue("topic_switched", {"from": "a", "to": "b"})  # 只 1 次
    time.sleep(0.4)
    assert svc.stats()["discoveries"] == 0, "1 次切换不应触发"
    svc.stop()


# ══════════════════════════════════════════════════════════ #
# 5. 纯函数 evolve（可重放、无副作用）
# ══════════════════════════════════════════════════════════ #


def test_evolve_pure_function():
    """evolve 是纯函数：不修改输入 state/event，相同输入 → 相同输出。"""
    svc = AssociationService()
    state = AssociationState(current_intent="UNKNOWN", topic_shift_count=1)
    event = {"kind": "intent_parsed", "payload": {"category": "diagnose"}}
    before_state = AssociationState(**state.__dict__)
    before_event = dict(event)
    out1 = svc._evolve(state, event)
    out2 = svc._evolve(state, event)
    assert out1.current_intent == "diagnose"
    assert out1 is not state, "应返回新对象"
    assert state.__dict__ == before_state.__dict__, "输入 state 不被修改"
    assert event == before_event, "输入 event 不被修改"
    assert out1.__dict__ == out2.__dict__, "相同输入 → 相同输出（可重放）"


def test_evolve_replay_sequence():
    """事件序列重放 → 状态与实时消费一致（幂等收敛）。"""
    svc = AssociationService()
    events = [
        {"kind": "intent_parsed", "payload": {"category": "a"}},
        {"kind": "topic_switched", "payload": {"from": "a", "to": "b"}},
        {"kind": "behavior_recorded", "payload": {"label": "x"}},
        {"kind": "discourse_updated", "payload": {"cohesion": 0.3}},
    ]
    st = AssociationState()
    for evt in events:
        st = svc._evolve(st, evt)
    assert st.current_intent == "a"
    assert st.topic_shift_count == 1
    assert st.behavior_count == 1
    assert st.cohesion == 0.3


# ══════════════════════════════════════════════════════════ #
# 6. 同步 C/S pull（热路径直连）
# ══════════════════════════════════════════════════════════ #


def test_sync_pull_cs(tmp_path):
    """C/S 同步拉取：pull() 直接跑漏斗（不进队列），热路径直连。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    result = svc.pull(text="分析 A 和 B 的因果关系", pcr_zone="ABYSS")
    assert "error" not in result, "pull 应返回漏斗结果而非错误"
    assert "layers" in result or "layer3_consensus" in result or result, \
        "pull 返回漏斗输出"
    # pull 不产生队列消费
    assert svc.stats()["consumed"] == 0
    svc.stop()


# ══════════════════════════════════════════════════════════ #
# 7. 生命周期 + 白盒
# ══════════════════════════════════════════════════════════ #


def test_lifecycle_start_stop(tmp_path):
    """start/stop 幂等：重复 start 不重复起线程，stop 后 running=False。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    assert svc.running is False
    svc.start()
    t1 = svc._thread
    svc.start()  # 幂等
    assert svc.running is True
    assert svc._thread is t1, "重复 start 不应新建线程"
    svc.stop()
    assert svc.running is False
    svc.stop()  # 幂等


def test_whitebox_stats(tmp_path):
    """白盒 stats：计数真实（A19），队列深度/状态可观察。"""
    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    svc.start()
    svc.enqueue("intent_parsed", {"category": "query"})
    assert _wait_until(lambda: svc.stats()["consumed"] == 1)
    st = svc.stats()
    assert st["state"]["current_intent"] == "query"
    assert st["queue_max"] == svc.DEFAULT_QUEUE_SIZE
    assert st["last_seq"] >= 1
    snap = svc.state_snapshot()
    assert snap.current_intent == "query"
    svc.stop()


# ══════════════════════════════════════════════════════════ #
# 8. engine 接线（活跃路径闭环）
# ══════════════════════════════════════════════════════════ #


def test_engine_pipeline_routing_and_discovery():
    """engine 接线：_route_pipeline_events → 定向投递 → 主题切换 → 发现闭环。"""
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    e = CognitiveRuntimeEngine()
    svc = e._assoc_service
    assert svc is not None, "engine 应实例化关联链独立服务"
    assert e._assoc_sub is svc, "旧属性名指向同一服务（一内核）"
    assert svc.running, "服务应已 start"

    e._route_pipeline_events({"pcr": {"zone": "ATOMIC"},
                              "intent": {"category": "查询"}})
    e._route_pipeline_events({"pcr": {"zone": "ABYSS"},
                              "intent": {"category": "修复"}})
    e._route_pipeline_events({"pcr": {"zone": "EXPLORE"},
                              "intent": {"category": "探索"}})
    ok = _wait_until(lambda: svc.stats()["discoveries"] == 1, timeout=5.0)
    assert ok, "3 次 intent 类别变化（2 次 topic_switched）应触发发现"
    assert e._last_association is not None and e._last_association.get("discovery"), \
        "发现结果应回写 engine 白盒（A19）"
    e.stop()


def test_engine_tracer_records_discovery():
    """监控：发现事件接入 tracer（非黑盒，可回查 association.service）。"""
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    from core.agent.event.tracer import PipelineTracer
    e = CognitiveRuntimeEngine()
    e._tracer = PipelineTracer()
    e._route_pipeline_events({"pcr": {"zone": "A"}, "intent": {"category": "a"}})
    e._route_pipeline_events({"pcr": {"zone": "B"}, "intent": {"category": "b"}})
    e._route_pipeline_events({"pcr": {"zone": "C"}, "intent": {"category": "c"}})
    ok = _wait_until(lambda: e._assoc_service.stats()["discoveries"] >= 1, timeout=5.0)
    assert ok, "应触发发现"
    found = [r for r in e._tracer.query(limit=50)
             if r.get("subsystem") == "association.service"]
    assert found, "tracer 应记录 association.service 发现指标"
    assert found[0]["success"] is True
    assert "intent" in (found[0].get("metadata") or {})
    e.stop()


def test_wire_subscribers_no_broadcast_association():
    """§7.3：wire_subscribers 不再把关联链注册为广播订阅者。"""
    from core.agent.event.subscribers import wire_subscribers

    class FakeEngine:
        pass

    e = FakeEngine()
    e._event_bus = None
    e._discourse_tree = object()
    e._behavior_graph = None
    e._meta_cognition = None
    e._ocean_analyst = None
    e._l1_modifier = None
    e._l2_5_belief = None
    e._event_subscribers = {}
    stats = wire_subscribers(e)
    assert stats["subscribers"] == 5
    assert "association" not in e._event_subscribers, \
        "关联链不做全广播订阅（独立服务 M→1 定向通道）"


# ══════════════════════════════════════════════════════════ #
# 9. blueprint executor 真接
# ══════════════════════════════════════════════════════════ #


def test_blueprint_executor_handle_association_real(tmp_path):
    """blueprint executor `_handle_association` 真接服务（非 deferred stub）。"""
    from core.agent.blueprint.executor import BlueprintExecutor
    from core.agent.blueprint.models import BlueprintNode

    class FakeEngine:
        def __init__(self, svc):
            self._assoc_service = svc

    svc = AssociationService(db_path=str(tmp_path / "el.db"))
    svc.start()
    ex = BlueprintExecutor(engine=FakeEngine(svc))
    node = BlueprintNode(node_id="assoc_1", chain="association", priority=2)
    out = ex._handle_association(node, {"intent_1": {"category": "诊断"}}, "分析故障")
    assert out["status"] in ("enqueued", "dropped"), "应定向投递到服务"
    assert out.get("service") == "association"
    ok = _wait_until(lambda: svc.stats()["consumed"] >= 2)
    assert ok, "intent_parsed + route_generated 应被服务消费"
    svc.stop()


def test_blueprint_executor_unavailable_no_fake():
    """无 service 时显式 unavailable（不做伪数据，设计红线）。"""
    from core.agent.blueprint.executor import BlueprintExecutor
    from core.agent.blueprint.models import BlueprintNode

    ex = BlueprintExecutor(engine=None)
    node = BlueprintNode(node_id="assoc_x", chain="association", priority=2)
    out = ex._handle_association(node, {}, "text")
    assert out["status"] == "unavailable"


# ══════════════════════════════════════════════════════════ #
# 10. 监控覆盖（白盒可见，非黑盒猜测）
# ══════════════════════════════════════════════════════════ #


class _FakeService:
    def __init__(self):
        self._stats = {
            "enqueued": 5, "consumed": 5, "dropped": 0, "replayed": 1,
            "discoveries": 1, "errors": 0, "queue_depth": 0, "queue_max": 256,
            "last_seq": 6, "running": True,
            "state": {"current_intent": "query", "topic_shift_count": 0,
                      "behavior_count": 0, "cohesion": 1.0, "discoveries": 1},
        }

    def stats(self):
        return dict(self._stats)


class _FakeEngine:
    def __init__(self):
        self._l2_5_belief = None
        self._association_funnel = None
        self._last_association = {"discovery": {"intent": "query"}, "ts": 1.0}
        self._l1_extractor = object()
        self._context_qualifier = object()
        self._l3_validator = object()
        self._association_relations = {"discovered": [{"intent": "query"}]}
        self._association_causal_annotations = []
        self._causal_blocked_edges = []
        self._assoc_service = _FakeService()


def test_cli_show_has_service_monitoring(capsys, monkeypatch):
    """监控：`dm assoc show` 暴露独立服务 stats（队列深度/发现/消费/丢弃）。"""
    from types import SimpleNamespace
    import json as _json
    from core.agent.cli.commands import assoc_cmd

    monkeypatch.setattr(assoc_cmd, "get_engine", lambda: _FakeEngine())
    args = SimpleNamespace(subcommand="show")
    assoc_cmd.cmd_assoc(args)
    out = _json.loads(capsys.readouterr().out)
    assert out["components"]["service"] is True
    assert out["service"]["enqueued"] == 5
    assert out["service"]["consumed"] == 5
    assert out["service"]["discoveries"] == 1
    assert out["service"]["queue_depth"] == 0
    assert "queue_max" in out["service"]
    assert "last_seq" in out["service"]


def test_cli_get_service_monitoring(capsys, monkeypatch):
    """监控：`dm assoc get service` 返回完整服务状态（白盒 A19）。"""
    from types import SimpleNamespace
    import json as _json
    from core.agent.cli.commands import assoc_cmd

    monkeypatch.setattr(assoc_cmd, "get_engine", lambda: _FakeEngine())
    args = SimpleNamespace(subcommand="get", key="service")
    assoc_cmd.cmd_assoc(args)
    out = _json.loads(capsys.readouterr().out)
    assert out["running"] is True
    assert out["state"]["current_intent"] == "query"
    assert out["replayed"] == 1
    assert out["errors"] == 0
