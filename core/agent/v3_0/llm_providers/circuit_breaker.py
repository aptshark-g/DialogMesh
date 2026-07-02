# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/circuit_breaker.py
──────────────────────────────────────────────
DialogMesh v3.0 熔断器模块。

用途：
- 为每个 LLM Provider 提供独立熔断保护，防止级联故障。
- 实现状态机（CLOSED → OPEN → HALF_OPEN → CLOSED）。
- 支持失败率阈值、慢调用阈值、最小调用次数等策略。
- 与 ProviderManager 集成，自动隔离异常 Provider。

设计参考：
  - 失败率阈值：当窗口内失败率超过 threshold 时触发熔断
  - 慢调用阈值：当 P95 延迟超过 slow_call_threshold_ms 时触发熔断
  - 半开请求数：HALF_OPEN 状态下最多允许 max_half_open_requests 个试探请求

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.agent.v3_0.llm_providers.models import CircuitState, ErrorCategory

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """熔断器配置参数。"""
    failure_rate_threshold: float = 0.5       # 失败率阈值 [0, 1]
    slow_call_rate_threshold: float = 0.8     # 慢调用率阈值 [0, 1]
    slow_call_threshold_ms: float = 5000.0    # 慢调用判定延迟（ms）
    min_calls_to_evaluate: int = 10           # 最小评估调用次数
    wait_duration_open_ms: float = 30000.0    # OPEN 状态持续时间（ms）
    max_half_open_requests: int = 3           # 半开状态最大试探请求数
    sliding_window_size: int = 100            # 滑动窗口大小


@dataclass
class _CallRecord:
    """单次调用记录（内部使用）。"""
    timestamp: float
    success: bool
    latency_ms: float


class CircuitBreaker:
    """
    Provider 级熔断器。

    状态机：
      CLOSED      → 正常，请求直接通过
      OPEN        → 熔断，请求被快速拒绝
      HALF_OPEN   → 半开，允许有限试探请求
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._state_changed_at = time.time()
        self._half_open_requests = 0
        self._records: List[_CallRecord] = []
        self._lock: Optional[asyncio.Lock] = None
        logger.info(f"CircuitBreaker initialized for {name}: state={self._state.value}")

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── 状态属性 ─────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    # ── 核心方法：请求前检查 ───────────────────────────────────────────

    async def allow_request(self) -> bool:
        """检查当前请求是否允许通过。"""
        async with self._ensure_lock():
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                # 检查是否已过等待期
                elapsed_ms = (time.time() - self._state_changed_at) * 1000
                if elapsed_ms >= self.config.wait_duration_open_ms:
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_requests = 0
                    return True
                return False
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.config.max_half_open_requests:
                    self._half_open_requests += 1
                    return True
                return False
            return True

    # ── 核心方法：请求后记录 ───────────────────────────────────────────

    async def record_success(self, latency_ms: float) -> None:
        """记录成功调用并评估状态转换。"""
        async with self._ensure_lock():
            self._add_record(True, latency_ms)
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_requests -= 1
                if self._half_open_requests <= 0:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"CircuitBreaker {self.name}: HALF_OPEN → CLOSED (recovered)")

    async def record_failure(self, latency_ms: float, error_category: Optional[ErrorCategory] = None) -> None:
        """记录失败调用并评估状态转换。"""
        async with self._ensure_lock():
            self._add_record(False, latency_ms)
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_requests -= 1
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"CircuitBreaker {self.name}: HALF_OPEN → OPEN (fail again, "
                    f"error={error_category.value if error_category else 'unknown'})"
                )
                return
            # 评估是否触发熔断
            if self._should_open():
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"CircuitBreaker {self.name}: CLOSED → OPEN (failure rate exceeded)")

    # ── 内部状态管理 ─────────────────────────────────────────────────────

    def _add_record(self, success: bool, latency_ms: float) -> None:
        """添加调用记录并维护滑动窗口。"""
        now = time.time()
        self._records.append(_CallRecord(timestamp=now, success=success, latency_ms=latency_ms))
        # 裁剪旧记录
        window_s = 60.0  # 60 秒窗口
        cutoff = now - window_s
        self._records = [r for r in self._records if r.timestamp >= cutoff]
        # 限制最大记录数
        if len(self._records) > self.config.sliding_window_size:
            self._records = self._records[-self.config.sliding_window_size:]

    def _should_open(self) -> bool:
        """评估是否应触发熔断。"""
        if len(self._records) < self.config.min_calls_to_evaluate:
            return False
        total = len(self._records)
        failures = sum(1 for r in self._records if not r.success)
        failure_rate = failures / total
        if failure_rate >= self.config.failure_rate_threshold:
            return True
        slow_calls = sum(1 for r in self._records if r.latency_ms >= self.config.slow_call_threshold_ms)
        slow_rate = slow_calls / total
        if slow_rate >= self.config.slow_call_rate_threshold:
            return True
        return False

    def _transition_to(self, new_state: CircuitState) -> None:
        """执行状态转换。"""
        old_state = self._state
        self._state = new_state
        self._state_changed_at = time.time()
        if new_state == CircuitState.OPEN:
            self._half_open_requests = 0

    # ── 状态查询 ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """返回当前统计信息。"""
        total = len(self._records)
        failures = sum(1 for r in self._records if not r.success)
        slow = sum(1 for r in self._records if r.latency_ms >= self.config.slow_call_threshold_ms)
        failure_rate = failures / total if total > 0 else 0.0
        slow_rate = slow / total if total > 0 else 0.0
        return {
            "state": self._state.value,
            "state_since": self._state_changed_at,
            "total_calls": total,
            "failures": failures,
            "failure_rate": failure_rate,
            "slow_calls": slow,
            "slow_rate": slow_rate,
            "half_open_requests": self._half_open_requests,
        }

    def get_state(self) -> Dict[str, Any]:
        """返回完整状态字典（用于健康检查）。"""
        return {
            "name": self.name,
            **self.get_stats(),
            "config": {
                "failure_rate_threshold": self.config.failure_rate_threshold,
                "slow_call_threshold_ms": self.config.slow_call_threshold_ms,
                "wait_duration_open_ms": self.config.wait_duration_open_ms,
                "max_half_open_requests": self.config.max_half_open_requests,
            },
        }

    async def reset(self) -> None:
        """手动重置熔断器到 CLOSED 状态。"""
        async with self._ensure_lock():
            self._state = CircuitState.CLOSED
            self._state_changed_at = time.time()
            self._half_open_requests = 0
            self._records.clear()
            logger.info(f"CircuitBreaker {self.name}: manually reset to CLOSED")

    # ── 装饰器模式 ───────────────────────────────────────────────────────

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        将 callable 包装为受熔断器保护的版本。
        适用于同步函数；异步函数请使用 ``wrap_async``。
        """
        def wrapper(*args, **kwargs):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                allowed = loop.run_until_complete(self.allow_request())
            except RuntimeError:
                allowed = asyncio.run(self.allow_request())
            if not allowed:
                raise CircuitBreakerOpenError(f"Circuit breaker OPEN for {self.name}")
            try:
                result = func(*args, **kwargs)
                loop.run_until_complete(self.record_success(0.0))
                return result
            except Exception as exc:
                loop.run_until_complete(self.record_failure(0.0))
                raise
        return wrapper

    def wrap_async(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """将异步 callable 包装为受熔断器保护的版本。"""
        async def wrapper(*args, **kwargs):
            allowed = await self.allow_request()
            if not allowed:
                raise CircuitBreakerOpenError(f"Circuit breaker OPEN for {self.name}")
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start) * 1000
                await self.record_success(latency_ms)
                return result
            except Exception as exc:
                latency_ms = (time.time() - start) * 1000
                await self.record_failure(latency_ms, self._classify_error(exc))
                raise
        return wrapper

    @staticmethod
    def _classify_error(exc: Exception) -> ErrorCategory:
        """简单错误分类。"""
        msg = str(exc).lower()
        if "timeout" in msg:
            return ErrorCategory.TIMEOUT
        if "rate" in msg:
            return ErrorCategory.RATE_LIMIT
        if "connection" in msg or "refused" in msg:
            return ErrorCategory.CONNECTION
        return ErrorCategory.UNKNOWN


class CircuitBreakerOpenError(Exception):
    """熔断器开启时抛出的异常。"""
    pass


class CircuitBreakerRegistry:
    """
    熔断器注册表——为多个 Provider 管理独立的熔断器实例。
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._default_config = CircuitBreakerConfig()

    def register(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """注册或更新 Provider 的熔断器。"""
        cfg = config or self._default_config
        breaker = CircuitBreaker(name, cfg)
        self._breakers[name] = breaker
        return breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """获取指定 Provider 的熔断器。"""
        return self._breakers.get(name)

    def unregister(self, name: str) -> bool:
        """注销 Provider 的熔断器。"""
        if name in self._breakers:
            del self._breakers[name]
            return True
        return False

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器状态。"""
        return {name: breaker.get_state() for name, breaker in self._breakers.items()}

    async def reset_all(self) -> None:
        """重置所有熔断器。"""
        for breaker in self._breakers.values():
            await breaker.reset()

    def set_default_config(self, config: CircuitBreakerConfig) -> None:
        """设置默认配置（影响后续新注册）。"""
        self._default_config = config


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 circuit_breaker self-test ===")

        # 1. 基本状态机
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_rate_threshold=0.5,
            min_calls_to_evaluate=5,
            wait_duration_open_ms=100.0,
        ))
        assert cb.is_closed()
        print(f"[PASS] CircuitBreaker initialized: {cb.state.value}")

        # 2. 记录失败触发熔断
        for _ in range(5):
            await cb.record_failure(10.0, ErrorCategory.TIMEOUT)
        assert cb.is_open()
        print(f"[PASS] CircuitBreaker OPEN after 5 failures")

        # 3. 等待恢复（半开）
        await asyncio.sleep(0.15)
        allowed = await cb.allow_request()
        assert allowed and cb.is_half_open()
        print(f"[PASS] CircuitBreaker HALF_OPEN after wait")

        # 4. 成功恢复关闭
        await cb.record_success(10.0)
        assert cb.is_closed()
        print(f"[PASS] CircuitBreaker CLOSED after recovery")

        # 5. 注册表
        registry = CircuitBreakerRegistry()
        registry.register("p1")
        registry.register("p2", CircuitBreakerConfig(failure_rate_threshold=0.3))
        assert len(registry.get_all_states()) == 2
        print(f"[PASS] CircuitBreakerRegistry")

        # 6. OPEN 时拒绝请求
        cb2 = CircuitBreaker("test2", CircuitBreakerConfig(
            failure_rate_threshold=0.1,
            min_calls_to_evaluate=1,
            wait_duration_open_ms=10000.0,
        ))
        await cb2.record_failure(10.0)
        assert await cb2.allow_request() is False
        print(f"[PASS] CircuitBreaker OPEN blocks requests")

        logger.info("=== All v3.0 circuit_breaker self-tests passed ===")

    asyncio.run(_self_test())
