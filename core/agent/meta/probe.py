# -*- coding: utf-8 -*-
"""ProactiveHealthProbe — 主动体检（元认知定期自检, 2026-08-16 P1-①）。

设计: SELF_REPAIR_DESIGN_20260816 §八 + PARADIGM A10（元认知第二大脑）
  诊断器原为"被动触发"（失败信号 → 诊断）; 主动体检 = **无触发也定期**
  用 introspection 薄弱点巡检, 复用诊断器做证据收集 + 根因分析 ——
  兑现"自修定期巡检（无触发也主动体检）"。

流程（daemon 线程, 周期 interval）:
  1. 信号收集: introspection.weak_spots + governor breakers + llm-calls
     （近窗逐阶段空返回/错误/重试统计）
  2. 薄弱点识别: 有失败记录的 scope / 空返回或错误>0 的 LLM 阶段
  3. 触发诊断: 每薄弱点 get_diagnoser.trigger()（诊断器自身频率门控兜底）
  4. 记录（A17）: 每轮巡检 findings/triggered/skipped → 内存环 + JSONL 落盘

白盒: GET /v6/probe（状态/历史）; POST /v6/probe/run（立即巡检一次）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "data", "probe_history.jsonl")


class ProactiveHealthProbe:
    """主动体检器（周期巡检; 线程安全; 单例使用）。"""

    def __init__(self, interval_s: float = 1800.0,
                 startup_delay_s: float = 120.0,
                 path: str = "",
                 governor: Any = None,
                 diagnoser: Any = None,
                 recorder: Any = None,
                 bus: Any = None):
        self._interval = max(10.0, float(interval_s))
        self._startup_delay = max(0.0, float(startup_delay_s))
        self._path = path or _default_path()
        self._gov = governor
        self._diag = diagnoser
        self._rec = recorder
        self._bus = bus
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._history: List[Dict[str, Any]] = []
        self._last_run: Optional[Dict[str, Any]] = None
        self._next_due: Optional[float] = None
        self._load_history()

    # ── 生命周期 ─────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._worker, daemon=True)
            self._thread.start()
            self._next_due = time.time() + self._startup_delay

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def _worker(self) -> None:
        first = True
        while True:
            with self._lock:
                if not self._running:
                    return
                delay = self._startup_delay if first else self._interval
            first = False
            self._sleep_checked(delay)
            with self._lock:
                if not self._running:
                    return
                self._next_due = time.time() + self._interval
            try:
                self.run_once()
            except Exception as e:
                logger.warning("probe run failed: %s", e)

    def _sleep_checked(self, seconds: float) -> None:
        remaining = float(seconds)
        while remaining > 0:
            with self._lock:
                if not self._running:
                    return
            step = min(1.0, remaining)
            time.sleep(step)
            remaining -= step

    # ── 巡检 ─────────────────────────────────────────────

    def run_once(self) -> Dict[str, Any]:
        """执行一轮主动体检（同步收集, 诊断异步入诊断器队列）。"""
        signals = self._gather()
        findings = self._detect(signals)
        triggered, skipped = [], []
        for f in findings:
            scope = str(f.get("scope", ""))
            if not scope:
                continue
            try:
                ok = self._diagnoser().trigger(
                    scope, f"proactive_check:{f.get('signal', '?')}",
                    {"probe": True, "detail": f.get("detail", "")})
                (triggered if ok else skipped).append(scope)
            except Exception as e:
                logger.debug("probe trigger failed: %s", e)
        rec = {
            "ts": time.time(),
            "interval_s": self._interval,
            "signals": {
                "breakers": len(signals.get("breakers", [])),
                "llm_calls": len(signals.get("llm_calls", [])),
                "diagnosis_reports": signals.get("weak_spots", {}).get(
                    "diagnosis_reports", 0),
            },
            "findings": findings,
            "triggered": triggered,
            "skipped": skipped,
        }
        with self._lock:
            self._history.append(rec)
            if len(self._history) > 200:
                self._history = self._history[-200:]
            self._last_run = rec
            self._persist(rec)
        return rec

    def _gather(self) -> Dict[str, Any]:
        signals: Dict[str, Any] = {}
        try:
            from core.agent.meta.introspection import weak_spots
            signals["weak_spots"] = weak_spots()
        except Exception:
            signals["weak_spots"] = {}
        try:
            signals["breakers"] = list(
                self._governor().stats().get("breakers", []))
        except Exception:
            signals["breakers"] = []
        try:
            if self._rec is not None:
                signals["llm_calls"] = self._rec.recent(500)
            else:
                from core.agent.llm.call_recorder import llm_call_recent
                signals["llm_calls"] = llm_call_recent(500)
        except Exception:
            signals["llm_calls"] = []
        return signals

    def _detect(self, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
        """薄弱点识别: 熔断失败 scope + LLM 阶段空返回/错误。"""
        findings: List[Dict[str, Any]] = []
        for b in signals.get("breakers", []):
            failures = int(b.get("total_failures", 0) or 0)
            state = str(b.get("state", "closed"))
            if failures > 0 or state != "closed":
                findings.append({
                    "scope": str(b.get("scope", "?")),
                    "signal": "breaker",
                    "severity": "high" if state != "closed" else "medium",
                    "detail": (
                        f"state={state} failures={failures} "
                        f"calls={b.get('total_calls', 0)}"),
                })
        per_stage: Dict[str, Dict[str, int]] = {}
        for c in signals.get("llm_calls", []):
            stage = str(c.get("stage", "?"))
            d = per_stage.setdefault(
                stage, {"count": 0, "empty": 0, "errors": 0, "retries": 0})
            d["count"] += 1
            if c.get("empty"):
                d["empty"] += 1
            if c.get("error"):
                d["errors"] += 1
            d["retries"] += int(c.get("retries", 0) or 0)
        for stage, d in per_stage.items():
            if d["empty"] > 0 or d["errors"] > 0:
                findings.append({
                    "scope": f"llm:{stage}", "signal": "llm_stage",
                    "severity": "medium",
                    "detail": (
                        f"count={d['count']} empty={d['empty']} "
                        f"errors={d['errors']} retries={d['retries']}"),
                })
        return findings

    # ── 依赖（可注入, 默认单例）────────────────────────────

    def _governor(self) -> Any:
        if self._gov is not None:
            return self._gov
        from core.agent.meta.governor import get_governor
        return get_governor(bus=self._bus)

    def _diagnoser(self) -> Any:
        if self._diag is not None:
            return self._diag
        from core.agent.meta.diagnosis import get_diagnoser
        return get_diagnoser(bus=self._bus)

    # ── 记录（A17: 巡检历史不删, JSONL 落盘）────────────────

    def _persist(self, rec: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("probe history persist failed: %s", e)

    def _load_history(self) -> None:
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f.readlines()[-200:]:
                    line = line.strip()
                    if line:
                        try:
                            self._history.append(json.loads(line))
                        except Exception:
                            pass
            if self._history:
                self._last_run = self._history[-1]
        except Exception as e:
            logger.debug("probe history load failed: %s", e)

    # ── 白盒 ─────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "interval_s": self._interval,
                "startup_delay_s": self._startup_delay,
                "last_run": self._last_run,
                "next_due_ts": self._next_due,
                "next_due_in_s": round(
                    max(0.0, (self._next_due or now) - now), 1),
                "runs": len(self._history),
                "history": list(self._history[-10:]),
            }


_probe: Optional[ProactiveHealthProbe] = None


def get_probe(bus: Any = None) -> ProactiveHealthProbe:
    global _probe
    if _probe is None:
        interval = float(os.environ.get("DM_PROBE_INTERVAL", "1800"))
        delay = float(os.environ.get("DM_PROBE_STARTUP_DELAY", "120"))
        _probe = ProactiveHealthProbe(
            interval_s=interval, startup_delay_s=delay, bus=bus)
    if bus is not None and _probe._bus is None:
        _probe._bus = bus
    return _probe
