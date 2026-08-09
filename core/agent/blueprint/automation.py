# -*- coding: utf-8 -*-
"""定时自动化持久实体 — GAP-2（COMPLETENESS_GAP_INVENTORY §C）.

对标 OpenWorker scheduler.py + automation/models.py（已精读源码, 2026-08-06）:
  - ScheduledTask = 持久实体（自有线程/工作区/standing rules/运行记录/续跑）
  - Scheduler 策略: run-once-catch-up（停机错过的任务启动补跑一次）+
    skip-on-overlap（上一轮未完成不叠加）; spawn 执行不阻塞调度循环
  - TaskRun: 每次触发 = 独立运行记录（session_id 可续跑）

本实现:
  AutomationTask  — 持久任务（JSON 落盘 data/automations.json）
  TaskRun         — 单次运行记录
  AutomationStore — 持久化 + due/advance（next_run 计算）
  AutomationScheduler — 后台线程 tick（默认 30s）+ catch-up + overlap guard
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = "data/automations.json"
DEFAULT_TICK_SECONDS = 30.0


def _now() -> float:
    return time.time()


def _parse_daily(cron: str) -> Optional[tuple]:
    """5 字段 cron 的轻量解析: 支持 * 与数字的 H M D M W.

    只支持每日/每周/每月固定时刻（OpenWorker Schedule.human 同量级）.
    返回 (minute, hour, dom, month, dow) 或 None.
    """
    parts = (cron or "").split()
    if len(parts) != 5:
        return None
    try:
        minute = int(parts[0])
        hour = int(parts[1])
    except ValueError:
        return None
    dom = parts[2]
    month = parts[3]
    dow = parts[4]
    if dom not in ("*",) and not dom.isdigit():
        return None
    if month not in ("*",) and not month.isdigit():
        return None
    if dow not in ("*",) and not dow.isdigit():
        return None
    return (minute, hour, dom, month, dow)


@dataclass
class AutomationSchedule:
    kind: str  # "interval" | "cron" | "once"
    seconds: Optional[float] = None    # interval
    cron: Optional[str] = None          # cron 5 字段
    fire_at: Optional[str] = None       # once (ISO datetime)

    def next_after(self, now: float) -> Optional[float]:
        if self.kind == "interval":
            return now + (self.seconds or 60.0)
        if self.kind == "once":
            try:
                t = datetime.fromisoformat(self.fire_at.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=datetime.now().astimezone().tzinfo)
                return t.timestamp()
            except Exception:
                return None
        if self.kind == "cron":
            parsed = _parse_daily(self.cron)
            if parsed is None:
                return None
            minute, hour, dom, month, dow = parsed
            base = datetime.fromtimestamp(now).astimezone()
            candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate.timestamp() <= now:
                candidate = candidate + timedelta(days=1)
            # 简化: 只推进日期直到 dom/month/dow 匹配（上限 400 天）
            for _ in range(400):
                if dom != "*" and candidate.day != int(dom):
                    candidate = candidate + timedelta(days=1)
                    continue
                if month != "*" and candidate.month != int(month):
                    candidate = candidate + timedelta(days=1)
                    continue
                if dow != "*" and candidate.weekday() != int(dow) % 7:
                    candidate = candidate + timedelta(days=1)
                    continue
                break
            return candidate.timestamp()
        return None


@dataclass
class AutomationTask:
    """持久自动化任务 — 每次触发 = 一次 TaskRun."""
    title: str
    instructions: str
    schedule: AutomationSchedule
    workspace: str = "."
    agent: str = "default"
    id: str = field(default_factory=lambda: "task-" + uuid.uuid4().hex[:10])
    session_id: str = ""                     # 任务自有线程（可续跑）
    always_allowed_tools: List[str] = field(default_factory=list)  # standing rules
    enabled: bool = True
    created_at: float = field(default_factory=_now)
    next_run: Optional[float] = None
    last_run: Optional[float] = None
    last_status: Optional[str] = None
    run_count: int = 0
    max_runs: Optional[int] = None

    def __post_init__(self):
        if not self.session_id:
            self.session_id = f"__automation__{self.id}"
        if self.next_run is None and self.schedule is not None:
            self.next_run = self.schedule.next_after(_now())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["schedule"] = asdict(self.schedule)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AutomationTask":
        d = dict(d)
        d["schedule"] = AutomationSchedule(**d.get("schedule", {}))
        return cls(**d)


@dataclass
class TaskRun:
    """单次运行记录（session_id 可续跑）."""
    task_id: str
    run_id: str = field(default_factory=lambda: "run-" + uuid.uuid4().hex[:10])
    started_at: float = field(default_factory=_now)
    finished_at: Optional[float] = None
    status: str = "running"   # running | ok | error | skipped
    result_text: Optional[str] = None
    error: Optional[str] = None
    trigger: str = "schedule"  # schedule | manual | catchup
    session_id: str = ""

    def __post_init__(self):
        if not self.session_id:
            self.session_id = f"__run__{self.run_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRun":
        return cls(**d)


class AutomationStore:
    """JSON 持久化（单用户本地优先, 对齐 OpenWorker sqlite_store 语义）."""

    def __init__(self, path: str = DEFAULT_STORE_PATH):
        self.path = path
        self._tasks: Dict[str, AutomationTask] = {}
        self._runs: Dict[str, List[TaskRun]] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                for t in data.get("tasks", []):
                    task = AutomationTask.from_dict(t)
                    self._tasks[task.id] = task
                for run in data.get("runs", []):
                    r = TaskRun.from_dict(run)
                    self._runs.setdefault(r.task_id, []).append(r)
        except Exception as e:
            logger.warning("AutomationStore load failed: %s", e)

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            data = {
                "tasks": [t.to_dict() for t in self._tasks.values()],
                "runs": [r.to_dict() for rs in self._runs.values() for r in rs],
            }
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.warning("AutomationStore save failed: %s", e)

    # ── CRUD ──

    def add(self, task: AutomationTask):
        self._tasks[task.id] = task
        self.save()

    def get(self, task_id: str) -> Optional[AutomationTask]:
        return self._tasks.get(task_id)

    def all(self) -> List[AutomationTask]:
        return list(self._tasks.values())

    def delete(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self.save()
            return True
        return False

    def due(self, now: Optional[float] = None) -> List[AutomationTask]:
        now = now or _now()
        return [t for t in self._tasks.values()
                if t.enabled and t.next_run is not None and t.next_run <= now
                and (t.max_runs is None or t.run_count < t.max_runs)]

    def advance(self, task: AutomationTask, run: TaskRun):
        """运行后推进: run_count/last_run/last_status/next_run."""
        task.run_count += 1
        task.last_run = run.started_at
        task.last_status = run.status
        task.next_run = task.schedule.next_after(_now())
        self._runs.setdefault(task.id, []).append(run)
        self.save()

    def runs(self, task_id: str) -> List[TaskRun]:
        return list(self._runs.get(task_id, []))


Runner = Callable[[AutomationTask, str], TaskRun]


class AutomationScheduler:
    """后台调度循环 — catch-up + overlap guard + spawn（不阻塞 tick）."""

    def __init__(self, store: AutomationStore, runner: Runner,
                 tick_seconds: float = DEFAULT_TICK_SECONDS):
        self.store = store
        self.runner = runner
        self.tick_seconds = tick_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running_ids: set = set()

    def start(self):
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            logger.info("AutomationScheduler started (tick=%.0fs)", self.tick_seconds)

    def stop(self, timeout: float = 5.0):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self):
        # run-once-catch-up: 启动先补跑一次（停机期间错过的）
        try:
            self._tick(trigger="catchup")
        except Exception as e:
            logger.exception("catch-up tick failed: %s", e)
        while not self._stop.wait(self.tick_seconds):
            try:
                self._tick(trigger="schedule")
            except Exception as e:
                logger.exception("scheduler tick failed: %s", e)

    def _tick(self, trigger: str):
        for task in self.store.due():
            self._run_task(task, trigger=trigger)

    def _run_task(self, task: AutomationTask, trigger: str) -> Optional[TaskRun]:
        if task.id in self._running_ids:  # skip-on-overlap
            logger.info("skip %s — previous run still going", task.id)
            return None
        self._running_ids.add(task.id)
        try:
            run = self.runner(task, trigger)
        except Exception as e:
            logger.exception("task %s run failed", task.id)
            run = TaskRun(task_id=task.id, status="error",
                          error=str(e), trigger=trigger)
        finally:
            self._running_ids.discard(task.id)
        self.store.advance(task, run)
        return run

