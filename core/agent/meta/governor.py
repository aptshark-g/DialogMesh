# -*- coding: utf-8 -*-
"""ExecutionGovernor — 执行链路横切治理（元认知子模块, AOP 风格）。

设计: EXECUTION_GOVERNOR_DESIGN_20260816.md
  A10/P14 元认知治理落实: 执行链路（LLM 调用/工具执行/规划）的高可用
  不再是"各调用点各自超时重试", 而是横切治理切面:
    - 熔断: 按 scope（阶段/工具）失败统计 → OPEN 快速失败 → 半开试探
    - 降级: 熔断/预算耗尽时的显式降级信号（调用方回骨架/摘要）
    - 幂等: 同 (request_id, scope) 重入短路
    - 纠错: 错误类型 → 定向重试策略（收敛散落重试）
    - 复盘: 治理动作进 decision_bus + 统计（白盒 /v6/governor）

与 ExecutionMonitor 边界: Monitor=任务级裁决; Governor=链路级治理。
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BreakerState(Enum):
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 开断: 快速失败
    HALF_OPEN = "half_open"  # 冷却后试探


class ScopeBreaker:
    """单 scope 熔断器（连续失败 + 窗口失败率）。"""

    def __init__(self, scope: str, failure_threshold: int = 3,
                 window_failure_rate: float = 0.6,
                 min_calls: int = 5, cooldown_s: float = 30.0,
                 half_open_max: int = 1):
        self.scope = scope
        self.failure_threshold = failure_threshold
        self.window_failure_rate = window_failure_rate
        self.min_calls = min_calls
        self.cooldown_s = cooldown_s
        self.half_open_max = half_open_max
        self.state = BreakerState.CLOSED
        self.consecutive_failures = 0
        self.window: list = []          # [(ts, ok)]
        self.total_calls = 0
        self.total_failures = 0
        self.opened_at: Optional[float] = None
        self.half_open_used = 0

    def allow(self) -> bool:
        now = time.time()
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.HALF_OPEN:
            if self.half_open_used < self.half_open_max:
                self.half_open_used += 1
                return True
            return False
        # OPEN: 冷却期后转 HALF_OPEN 放行试探
        if self.opened_at and now - self.opened_at >= self.cooldown_s:
            self.state = BreakerState.HALF_OPEN
            self.half_open_used = 0
            return True
        return False

    def record(self, ok: bool) -> None:
        now = time.time()
        self.window.append((now, ok))
        self.window = [w for w in self.window if now - w[0] < 120.0]
        self.total_calls += 1
        if ok:
            self.total_failures += 0
            self.consecutive_failures = 0
            # 恢复: CLOSED / HALF_OPEN 试探成功 → CLOSED
            if self.state == BreakerState.HALF_OPEN:
                self._to_closed()
        else:
            self.total_failures += 1
            self.consecutive_failures += 1
            self._maybe_open(now)

    def _maybe_open(self, now: float) -> None:
        if self.state == BreakerState.HALF_OPEN:
            # 试探失败 → 回 OPEN 重启冷却
            self.state = BreakerState.OPEN
            self.opened_at = now
            return
        if self.state != BreakerState.CLOSED:
            return
        if self.consecutive_failures >= self.failure_threshold:
            self._open(now, "consecutive_failures")
            return
        recent = self.window[-self.min_calls:] if len(self.window) >= self.min_calls else self.window
        if len(recent) >= self.min_calls:
            fail = sum(1 for _, ok in recent if not ok)
            if fail / len(recent) >= self.window_failure_rate:
                self._open(now, "window_failure_rate")

    def _open(self, now: float, reason: str) -> None:
        self.state = BreakerState.OPEN
        self.opened_at = now
        logger.warning("governor: breaker OPEN scope=%s reason=%s",
                       self.scope, reason)

    def _to_closed(self) -> None:
        self.state = BreakerState.CLOSED
        self.consecutive_failures = 0
        self.opened_at = None
        logger.info("governor: breaker CLOSED scope=%s (recovered)",
                    self.scope)

    def stats(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "window_seconds": 120,
        }


# 错误类型 → (动作, 最大重试)
#   timeout: 降预算重试 1 次（剩余预算被调用方截断）
#   empty:   重试 2 次（deepseek 密集输出随机空, 已知模式）
#   connection: 快速重试 1 次（网关瞬时抖动）
#   parse:   不重试（返回骨架/降级）
#   unknown: 重试 1 次
RETRY_POLICY: Dict[str, tuple] = {
    "timeout": ("retry", 1),
    "empty": ("retry", 2),
    "connection": ("retry", 1),
    "parse": ("none", 0),
    "unknown": ("retry", 1),
}


def classify_error(error: str) -> str:
    e = (error or "").lower()
    if "timed out" in e or "timeout" in e:
        return "timeout"
    if "10061" in e or "10060" in e or "connection" in e or "refused" in e:
        return "connection"
    if "parse" in e or "json" in e or "not valid" in e:
        return "parse"
    if "empty" in e or "content" in e:
        return "empty"
    return "unknown"


class ExecutionGovernor:
    """链路治理入口（单例使用; 观察 + 判定 + 事件复盘）。"""

    def __init__(self, bus: Any = None):
        self._bus = bus
        self._lock = threading.Lock()
        self._breakers: Dict[str, ScopeBreaker] = {}
        self._in_flight: Dict[tuple, float] = {}
        self._actions: list = []
        self._max_actions = 200
        self._failure_counts: Dict[tuple, int] = {}
        self._diagnosis_triggered: Dict[str, float] = {}

    # ── 熔断 ─────────────────────────────────────────────

    def allow(self, scope: str) -> bool:
        """调用前检查: False = 熔断开断（调用方快速降级）。"""
        with self._lock:
            br = self._breakers.get(scope)
            if br is None:
                return True
            allowed = br.allow()
            if not allowed:
                self._log_action(
                    "breaker_reject", scope,
                    {"state": br.state.value,
                     "reason": "breaker open, fast fail"})
            return allowed

    def observe(self, scope: str, ok: bool,
                error: str = "") -> None:
        """调用后上报结果（成功/失败）。"""
        with self._lock:
            br = self._breakers.setdefault(
                scope, ScopeBreaker(scope))
            before = br.state
            br.record(ok)
            if br.state != before:
                self._log_action(
                    "breaker_transition", scope,
                    {"from": before.value, "to": br.state.value,
                     "error": str(error)[:120]})
                if br.state == BreakerState.OPEN:
                    self._maybe_trigger_diagnosis_locked(
                        scope, "breaker_open")
            if not ok:
                self._note_failure_locked(scope, error)

    def _note_failure_locked(self, scope: str, error: str) -> None:
        """重复失败计数 → 达阈值触发异步诊断（大环, A10）。

        阈值: connection 类（基础设施故障, 如网关挂）= 1 次立即诊断;
        其余类型（预算耗尽/空返回/超时）= 3 次。频率门控由诊断器
        min_interval 兜底。
        """
        key = (scope, classify_error(error))
        threshold = 1 if key[1] == "connection" else 3
        count = self._failure_counts.get(key, 0) + 1
        self._failure_counts[key] = count
        if count >= threshold:
            self._failure_counts[key] = 0
            self._maybe_trigger_diagnosis_locked(
                scope, f"repeated_failure:{key[1]} x{count}")

    def _maybe_trigger_diagnosis_locked(self, scope: str,
                                        reason: str) -> None:
        now = time.time()
        if now - self._diagnosis_triggered.get(scope, 0.0) < 60.0:
            return  # 大环冷却: 同 scope 60s 内最多触发一次
        self._diagnosis_triggered[scope] = now
        try:
            from core.agent.meta.diagnosis import get_diagnoser
            get_diagnoser().trigger(
                scope, reason,
                {"breaker": self._breakers.get(scope).stats()
                 if scope in self._breakers else {},
                 "recent_actions": self._actions[-5:]})
        except Exception as e:
            logger.debug("diagnosis trigger failed: %s", e)

    # ── 幂等 ─────────────────────────────────────────────

    def begin(self, request_id: str, scope: str) -> bool:
        """同 (request_id, scope) 处理中 → False 短路（不重复调用）。"""
        key = (request_id or "", scope)
        with self._lock:
            if key in self._in_flight:
                self._log_action(
                    "idempotent_shortcut", scope,
                    {"request_id": request_id, "reason": "in_flight"})
                return False
            self._in_flight[key] = time.time()
            return True

    def end(self, request_id: str, scope: str) -> None:
        with self._lock:
            self._in_flight.pop((request_id or "", scope), None)

    # ── 纠错（重试策略）──────────────────────────────────

    def retry_policy_for(self, error: str) -> tuple:
        kind = classify_error(error)
        return RETRY_POLICY.get(kind, RETRY_POLICY["unknown"])

    # ── 自调节（AsyncDiagnosis 建议 apply, A10 大环）────────────

    def adjust(self, scope: str, **params: Any) -> dict:
        """调熔断器参数（诊断建议自动应用, 低风险）。"""
        _int_keys = {"failure_threshold", "min_calls", "half_open_max"}
        _float_keys = {"window_failure_rate", "cooldown_s"}
        applied = {}
        with self._lock:
            br = self._breakers.setdefault(scope, ScopeBreaker(scope))
            for k, v in params.items():
                if not hasattr(br, k) or k == "scope":
                    continue
                try:
                    if k in _int_keys:
                        v = max(1, int(v))
                    elif k in _float_keys:
                        v = float(v)
                    setattr(br, k, v)
                    applied[k] = v
                except Exception:
                    continue
        if applied:
            self._log_action(
                "self_tune", scope, {"params": applied,
                                    "reason": "diagnosis applied"})
        return applied

    def adjust_retry(self, kind: str, max_retries: int) -> dict:
        """调重试策略（诊断建议自动应用）。"""
        if kind not in RETRY_POLICY:
            return {}
        action, _ = RETRY_POLICY[kind]
        RETRY_POLICY[kind] = (action, max(0, int(max_retries)))
        self._log_action(
            "self_tune_retry", kind,
            {"max_retries": RETRY_POLICY[kind][1],
             "reason": "diagnosis applied"})
        return {"kind": kind, "max_retries": RETRY_POLICY[kind][1]}

    # ── 复盘 ─────────────────────────────────────────────

    def _log_action(self, kind: str, scope: str, detail: Dict) -> None:
        entry = {
            "ts": time.time(), "kind": kind, "scope": scope,
            "detail": {k: str(v)[:200] for k, v in detail.items()},
        }
        self._actions.append(entry)
        if len(self._actions) > self._max_actions:
            self._actions = self._actions[-self._max_actions:]
        bus = self._bus
        if bus is not None and hasattr(bus, "log"):
            try:
                bus.log(
                    kind="governor_action", dimension=f"governor.{scope}",
                    before=None,
                    after={"action": kind, **detail},
                    reason=detail.get("reason", ""),
                    actor="meta", attribution="tool")
            except Exception as e:
                logger.debug("governor bus log failed: %s", e)

    # ── 白盒 ─────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            breakers = [b.stats() for b in self._breakers.values()]
            actions = list(self._actions[-50:])
            in_flight = len(self._in_flight)
        return {
            "breakers": breakers,
            "in_flight": in_flight,
            "recent_actions": actions,
        }


_governor: Optional[ExecutionGovernor] = None


def get_governor(bus: Any = None) -> ExecutionGovernor:
    global _governor
    if _governor is None:
        _governor = ExecutionGovernor(bus=bus)
    if bus is not None and _governor._bus is None:
        _governor._bus = bus
    return _governor
