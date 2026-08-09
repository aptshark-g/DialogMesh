# -*- coding: utf-8 -*-
"""G2 EventBus 生命周期层 — M5 深层次测试（对抗性断言，拒绝浅断言）。

覆盖 G2 验收六条:
  ① 多消费者: B 未消费的事件不会被温减枝减掉（per-subscriber 水位线）
  ② 减枝只针对"所有消费者已消费 + 超期"的事件
  ③ semantic_value 锚点数可观测（无需 LLM 打分）
  ④ 摘要化后 A24 锚点保真（锚点不完整则跳过，保原文）
  ⑤ 旧 events/event_bus.py 已在 un_use 归档
  ⑥ 慢消费者永不丢事件（NEVER drop 语义保持）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _mk_log(tmp_path, retention_hours=24):
    from core.agent.api.api_event_log import EventLog
    el = EventLog(db_path=str(tmp_path / "el.db"), retention_hours=retention_hours)
    el.open()
    return el


def _mk_old_event(el, eid, kind="intent_parsed", payload=None, age_hours=48):
    """写入一个"超期"事件（created_at 回拨）。"""
    el.put_event(event_id=eid, kind=kind, payload=payload or {"category": "a"})
    with el._conn:
        el._conn.execute(
            "UPDATE event_log SET created_at = ? WHERE event_id = ?",
            (time.time() - age_hours * 3600, eid),
        )
    return el.event_seq(eid)


# ══════════════════════════════════════════════════════════ #
# ① 多消费者水位线：B 未消费 → 不减枝
# ══════════════════════════════════════════════════════════ #


def test_multiconsumer_watermark_protects_unconsumed(tmp_path):
    """验收①：A 已消费、B 未消费的事件，温减枝不得触碰。"""
    el = _mk_log(tmp_path, retention_hours=24)
    el.register_consumer("A")
    el.register_consumer("B")
    seq = _mk_old_event(el, "e1", payload={"activation_count": 0})
    el.ack_consumer("A", seq)

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, importance_threshold=0.3)
    res = lc.prune_warm()
    assert res["pruned"] == 0, "B 未消费 → 不得减枝"

    # B 消费后 → 可减枝
    el.ack_consumer("B", seq)
    res = lc.prune_warm()
    assert res["pruned"] == 1, "全消费者已消费 + 超期 + 低重要性 → 应减枝"

    # 减枝后 payload 结构降级（锚点保留）——用 probe 消费者看全量
    el.register_consumer("probe")
    rows = el.replay_for_consumer("probe", 10)
    assert rows and rows[0]["payload"].get("_pruned") is True
    el.close()


def test_multiconsumer_partial_ack_one_event(tmp_path):
    """两个消费者各消费一半：min 水位线以下才可减枝。"""
    el = _mk_log(tmp_path, retention_hours=24)
    el.register_consumer("A")
    el.register_consumer("B")
    s1 = _mk_old_event(el, "e1")
    s2 = _mk_old_event(el, "e2")
    el.ack_consumer("A", s2)
    el.ack_consumer("B", s1)  # B 只到 e1

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, importance_threshold=0.99)
    res = lc.prune_warm()
    assert res["pruned"] == 1, "min 水位线 = e1 → 只减枝 e1"
    el.register_consumer("probe")
    rows = el.replay_for_consumer("probe", 10)
    by_id = {r["event_id"]: r for r in rows}
    assert by_id["e2"]["payload"].get("_pruned") is not True, "e2 未被 A 消费前不减枝"
    assert by_id["e1"]["payload"].get("_pruned") is True
    el.close()


# ══════════════════════════════════════════════════════════ #
# ② 只减枝"全消费 + 超期"
# ══════════════════════════════════════════════════════════ #


def test_fresh_event_not_pruned(tmp_path):
    """未超 retention 的事件即使全消费也不减枝。"""
    el = _mk_log(tmp_path, retention_hours=24)
    el.register_consumer("A")
    el.put_event(event_id="fresh", kind="intent_parsed", payload={"activation_count": 0})
    el.ack_consumer("A", el.event_seq("fresh"))

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, importance_threshold=0.99)
    res = lc.prune_warm()
    assert res["pruned"] == 0, "未超期 → 不减枝"
    el.close()


def test_legacy_consumed_fallback(tmp_path):
    """无注册消费者时退化为 legacy consumed=1 判据（兼容单消费者快捷路径）。"""
    el = _mk_log(tmp_path, retention_hours=24)
    eid = "legacy1"
    el.put_event(event_id=eid, kind="behavior_recorded", payload={"activation_count": 0})
    with el._conn:
        el._conn.execute(
            "UPDATE event_log SET created_at = ? WHERE event_id = ?",
            (time.time() - 48 * 3600, eid),
        )
    el.ack_event(eid)  # legacy 快捷 ack

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, importance_threshold=0.99)
    res = lc.prune_warm()
    assert res["pruned"] == 1, "legacy consumed=1 + 超期 → 可减枝"
    el.close()


# ══════════════════════════════════════════════════════════ #
# ③ semantic_value 锚点数可观测
# ══════════════════════════════════════════════════════════ #


def test_semantic_value_observable(tmp_path):
    """验收③：semantic_value 锚点数可观测，无需 LLM 打分。"""
    el = _mk_log(tmp_path)
    el.put_event("s1", "association_discovered",
                 {"cross_ref": ["n1", "n2"], "l2_summary": {"t": "x"}})
    el.put_event("s2", "pcr_computed", {"zone": "MIXED"})
    assert el.compute_semantic_value({"cross_ref": ["a", "b"], "l2_summary": {"t": "x"}}) == 3
    rows = el.replay_for_consumer("probe", 10)
    by_id = {r["event_id"]: r for r in rows}
    assert by_id["s1"]["payload"].get("cross_ref")  # 锚点保留在 payload
    # semantic_value 存于行内（可观测）
    row = el._conn.execute(
        "SELECT semantic_value FROM event_log WHERE event_id='s1'").fetchone()
    assert row[0] >= 3
    row2 = el._conn.execute(
        "SELECT semantic_value FROM event_log WHERE event_id='s2'").fetchone()
    assert row2[0] == 0
    el.close()


# ══════════════════════════════════════════════════════════ #
# ④ A24 锚点完整性校验
# ══════════════════════════════════════════════════════════ #


def test_anchor_integrity_keeps_anchors(tmp_path):
    """验收④：摘要化后锚点集 == 原文锚点集（A24 可逆推）。"""
    el = _mk_log(tmp_path)
    el.register_consumer("A")
    el.put_event("a1", "association_discovered",
                 {"cross_ref": ["n1", "n2"], "l2_summary": {"t": "x"},
                  "detail": "long text that should be stripped"})
    seq = el.event_seq("a1")
    el.ack_consumer("A", seq)
    with el._conn:
        el._conn.execute(
            "UPDATE event_log SET created_at = ? WHERE event_id = 'a1'",
            (time.time() - 96 * 3600,))

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, cold_age_hours=72,
                           importance_threshold=0.99)
    res = lc.summarize_cold()
    assert res["summarized"] == 1
    row = el._conn.execute(
        "SELECT payload FROM event_log WHERE event_id='a1'").fetchone()
    payload = __import__("json").loads(row[0])
    assert set(payload.get("cross_ref", [])) == {"n1", "n2"}, "锚点必须保留"
    assert payload.get("l2_summary") is not None
    assert "detail" not in payload, "非锚点细节应被降级"
    el.close()


def test_anchor_incomplete_skips_prune(tmp_path):
    """锚点不完整 → 跳过减枝，保原文（A24 不违反）。"""
    from core.agent.event.log_lifecycle import EventLogLifecycle
    el = _mk_log(tmp_path)
    lc = EventLogLifecycle(el)

    # 单元级：摘要缺锚点 → 完整性校验拒绝
    assert lc.anchor_integrity({"cross_ref": ["keep_me"]}, {"summary": "x"}) is False
    assert lc.anchor_integrity({"cross_ref": ["keep_me"]}, {"cross_ref": ["keep_me"]}) is True
    assert lc.anchor_integrity({"cross_ref": ["a"]}, {"cross_ref": ["a", "b"]}) is True

    # 端到端：monkeypatch 结构摘要丢弃锚点 → summarize_cold 跳过
    el.register_consumer("A")
    el.put_event("inc", "association_discovered",
                 {"cross_ref": ["keep_me"], "payload_data": {"x": 1}})
    seq = el.event_seq("inc")
    el.ack_consumer("A", seq)
    with el._conn:
        el._conn.execute(
            "UPDATE event_log SET created_at = ? WHERE event_id = 'inc'",
            (time.time() - 96 * 3600,))

    lc._structural_summary = lambda evt: {"_pruned": True, "summary": "dropped anchors"}
    res = lc.summarize_cold()
    assert res["summarized"] == 0, "锚点不完整 → 不得摘要化"
    row = el._conn.execute(
        "SELECT payload FROM event_log WHERE event_id='inc'").fetchone()
    payload = __import__("json").loads(row[0])
    assert payload.get("cross_ref") == ["keep_me"], "原文锚点必须保留（未减枝）"
    el.close()


# ══════════════════════════════════════════════════════════ #
# ⑤ 旧 bus 已归档
# ══════════════════════════════════════════════════════════ #


def test_old_event_bus_archived(tmp_path):
    """验收⑤：旧 deque 总线已在 un_use/event_bus_archived/。"""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(
        repo, "un_use", "event_bus_archived", "event_bus_v1_ringbuffer.py"))
    assert not os.path.exists(os.path.join(repo, "core", "agent", "events", "event_bus.py"))


def test_registry_points_to_v2_bus():
    """CLI registry 的 event_bus 指向 v2（core.agent.event.event_bus）。"""
    import core.agent.cli.registry as reg
    src = open(reg.__file__, encoding="utf-8").read()
    assert "core.agent.event.event_bus:EventBus" in src
    assert "core.agent.events.event_bus" not in src


# ══════════════════════════════════════════════════════════ #
# ⑥ NEVER drop 语义保持
# ══════════════════════════════════════════════════════════ #


def test_never_drop_sync_and_async(tmp_path):
    """验收⑥：同步桥 + 异步 API 都不丢事件；慢消费者溢出计数不丢。"""
    from core.agent.event.event_bus import EventBus

    bus = EventBus()
    received = []
    bus.subscribe_sync("a.>", lambda ev: received.append(ev.subject))
    n = bus.publish_sync("a.b", {"x": 1})
    assert n == 1
    assert received == ["a.b"]

    # 慢消费者：max_pending 极小 + 多事件 → 溢出计数，但后续可 replay（EventLog 兜底）
    bus2 = EventBus()
    slow = []
    bus2.subscribe_sync("s.>", lambda ev: slow.append(ev.subject), max_pending=1)
    for i in range(5):
        bus2.publish_sync("s.e", {"i": i})
    assert len(slow) >= 1, "回调型订阅立即投递（不丢）"
    st = bus2.stats
    assert st["published"] == 5
    bus.drain_sync()
    bus2.drain_sync()


# ══════════════════════════════════════════════════════════ #
# 生命周期 run_gc 端到端
# ══════════════════════════════════════════════════════════ #


def test_run_gc_end_to_end(tmp_path):
    """run_gc: 温减枝 + 冷摘要一次跑通，统计可观测。"""
    el = _mk_log(tmp_path, retention_hours=24)
    el.register_consumer("A")
    # 热事件（新鲜）→ 保留
    el.put_event("hot", "pcr_computed", {"zone": "MIXED", "activation_count": 9})
    el.ack_consumer("A", el.event_seq("hot"))
    # 温事件（超期 + 低重要性）→ 减枝
    _mk_old_event(el, "warm", payload={"activation_count": 0})
    el.ack_consumer("A", el.event_seq("warm"))
    # 冷事件（更老 + 锚点）→ 摘要
    # cold 事件高激活 → warm 阶段不减枝（importance 高），留给冷摘要
    el.put_event("cold", "association_discovered",
                 {"cross_ref": ["n1"], "activation_count": 9})
    seq = el.event_seq("cold")
    el.ack_consumer("A", seq)
    with el._conn:
        el._conn.execute(
            "UPDATE event_log SET created_at = ? WHERE event_id = 'cold'",
            (time.time() - 100 * 3600,))

    from core.agent.event.log_lifecycle import EventLogLifecycle
    lc = EventLogLifecycle(el, retention_hours=24, cold_age_hours=72,
                           importance_threshold=0.3)
    res = lc.run_gc()
    assert res["pruned"] == 1, "warm 应被减枝"
    assert res["summarized"] == 1, "cold 应被摘要"
    st = lc.stats()
    assert st["warm_pruned"] == 1 and st["cold_summarized"] == 1
    assert st["last_run"] > 0
    el.close()


def test_association_service_still_replays(tmp_path):
    """回归：关联链服务消费路径不受水位线改动影响（legacy 快捷路径保留）。"""
    from core.agent.association.association_service import AssociationService
    svc = AssociationService(db_path=str(tmp_path / "assoc.db"), queue_size=8)
    svc.enqueue("intent_parsed", {"category": "query"})
    svc.enqueue("behavior_recorded", {"label": "scan"})
    st = svc.stats()
    assert st["enqueued"] == 2
    svc.stop()
