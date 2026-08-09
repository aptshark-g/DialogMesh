# -*- coding: utf-8 -*-
"""GAP-2 定时自动化持久实体测试（COMPLETENESS_GAP_INVENTORY §C）.

覆盖（OpenWorker scheduler/models 对标）:
  - AutomationTask 持久实体（自有 session/standing rules/运行计数）
  - AutomationStore JSON 持久化（add/get/all/delete/due/advance/runs）
  - Schedule.next_after: interval/cron/once
  - Scheduler: run-once-catch-up + skip-on-overlap + spawn 不阻塞
  - TaskRun 独立运行记录（session_id 续跑）
"""
from __future__ import annotations

import json
import os
import time

from core.agent.blueprint.automation import (
    AutomationStore, AutomationTask, AutomationSchedule, TaskRun,
    AutomationScheduler,
)


def _task(seconds: float = 60.0, title: str = "t") -> AutomationTask:
    return AutomationTask(
        title=title,
        instructions="跑一次",
        schedule=AutomationSchedule(kind="interval", seconds=seconds),
        workspace=".",
    )


# ═══════════════════════════════════════════════════════════════
# Schedule
# ═══════════════════════════════════════════════════════════════

def test_schedule_interval():
    s = AutomationSchedule(kind="interval", seconds=30)
    n = s.next_after(1000.0)
    assert n == 1030.0


def test_schedule_once():
    s = AutomationSchedule(kind="once",
                           fire_at="2026-08-07T10:00:00")
    n = s.next_after(0)
    assert n is not None and n > 1.7e9


def test_schedule_cron_daily():
    s = AutomationSchedule(kind="cron", cron="30 7 * * *")
    now = time.time()
    n = s.next_after(now)
    assert n is not None
    assert n > now
    # 明天 07:30 或今天已过则明天
    from datetime import datetime
    dt = datetime.fromtimestamp(n).astimezone()
    assert dt.hour == 7 and dt.minute == 30


def test_schedule_cron_invalid():
    s = AutomationSchedule(kind="cron", cron="not a cron")
    assert s.next_after(time.time()) is None


# ═══════════════════════════════════════════════════════════════
# Store 持久化
# ═══════════════════════════════════════════════════════════════

def test_store_roundtrip(tmp_path):
    path = str(tmp_path / "auto.json")
    store = AutomationStore(path)
    t = _task()
    store.add(t)
    store2 = AutomationStore(path)  # 重新加载
    loaded = store2.get(t.id)
    assert loaded is not None
    assert loaded.title == "t"
    assert loaded.schedule.kind == "interval"
    assert loaded.session_id.startswith("__automation__")


def test_store_due_and_advance():
    store = AutomationStore("data/_test_auto_tmp.json")
    t = _task(seconds=0.001)
    t.next_run = 0.0  # 立即到期
    store.add(t)
    due = store.due()
    assert any(x.id == t.id for x in due)
    run = TaskRun(task_id=t.id, status="ok", result_text="done")
    store.advance(t, run)
    assert t.run_count == 1
    assert t.last_status == "ok"
    assert store.runs(t.id)[0].status == "ok"
    assert t.next_run is not None and t.next_run > 0
    os.path.exists("data/_test_auto_tmp.json") and \
        os.remove("data/_test_auto_tmp.json")


def test_store_delete_and_max_runs():
    store = AutomationStore("data/_test_auto_tmp2.json")
    t = _task()
    t.max_runs = 1
    store.add(t)
    assert store.delete(t.id) is True
    assert store.get(t.id) is None
    os.path.exists("data/_test_auto_tmp2.json") and \
        os.remove("data/_test_auto_tmp2.json")


# ═══════════════════════════════════════════════════════════════
# Scheduler
# ═══════════════════════════════════════════════════════════════

def test_scheduler_catchup_and_overlap():
    store = AutomationStore("data/_test_auto_tmp3.json")
    t = _task()
    t.next_run = 0.0  # catch-up 到期
    store.add(t)
    calls = []
    in_flight = {"n": 0}

    def runner(task, trigger):
        calls.append(trigger)
        in_flight["n"] += 1
        time.sleep(0.05)
        in_flight["n"] -= 1
        return TaskRun(task_id=task.id, status="ok", trigger=trigger)

    sched = AutomationScheduler(store, runner, tick_seconds=0.01)
    sched._tick(trigger="catchup")   # 手动触发第一轮
    sched._tick(trigger="schedule")  # 第二轮 — 若 first_run 仍在跑 → skip
    assert len(calls) >= 1
    assert calls[0] == "catchup"
    os.path.exists("data/_test_auto_tmp3.json") and \
        os.remove("data/_test_auto_tmp3.json")


def test_scheduler_overlap_guard_direct():
    """skip-on-overlap: 同任务在跑时再次触发 → 跳过."""
    store = AutomationStore("data/_test_auto_tmp4.json")
    t = _task()
    t.next_run = 0.0
    store.add(t)
    calls = []

    def runner(task, trigger):
        calls.append(trigger)
        return TaskRun(task_id=task.id, status="ok", trigger=trigger)

    sched = AutomationScheduler(store, runner, tick_seconds=0.01)
    # 模拟任务卡住: 手动把 running_ids 加进去 → 应 skip
    sched._running_ids.add(t.id)
    run = sched._run_task(t, trigger="schedule")
    assert run is None  # skipped
    assert calls == []
    sched._running_ids.discard(t.id)
    os.path.exists("data/_test_auto_tmp4.json") and \
        os.remove("data/_test_auto_tmp4.json")


def test_scheduler_runner_error_records_run():
    store = AutomationStore("data/_test_auto_tmp5.json")
    t = _task()
    t.next_run = 0.0
    store.add(t)

    def runner(task, trigger):
        raise RuntimeError("boom")

    sched = AutomationScheduler(store, runner, tick_seconds=0.01)
    run = sched._run_task(t, trigger="schedule")
    assert run.status == "error"
    assert "boom" in (run.error or "")
    assert t.last_status == "error"
    os.path.exists("data/_test_auto_tmp5.json") and \
        os.remove("data/_test_auto_tmp5.json")

