# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/failover_provider.py
──────────────────────────────────────────────────
DialogMesh v3.0 Failover Provider — 主备自动切换。

当主 Provider 失败（超时、连接错误、空响应）时，自动降级到备用 Provider。
记录降级事件和恢复状态，供外部监控。

与 v2.x 的改进：
  - 原生异步，支持 async health_check 与 generate
  - 使用 Pydantic 模型（ProviderConfig, GenerateResult_v3）
  - 集成熔断器逻辑（CircuitBreaker）
  - 支持自动恢复探测（半开状态）

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional

from core.agent.v3_0.llm_providers.base import (
    GenerateRequest_v3,
    GenerateResult_v3,
    LLMProvider_v3,
)
from core.agent.v3_0.llm_providers.models import (
    ErrorCategory,
    ProviderCapabilities,
    ProviderConfig,
    StreamingChunk,
)
from core.agent.v3_0.llm_providers.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)


class FailoverProvider_v3(LLMProvider_v3):
    """
    v3.0 主备降级包装器。

    Usage:
        primary = OpenAIProvider_v3(config1)
        fallback = OpenAIProvider_v3(config2)
        provider = FailoverProvider_v3(
            ProviderConfig(name="failover"),
            primary=primary,
            fallback=fallback,
        )
        result = await provider.generate_async(request)
    """

    def __init__(
        self,
        config: ProviderConfig,
        primary: LLMProvider_v3,
        fallback: LLMProvider_v3,
        failover_cooldown_s: float = 60.0,
    ):
        super().__init__(config)
        self.primary = primary
        self.fallback = fallback
        self.failover_cooldown_s = failover_cooldown_s
        self._last_failover_time: Optional[float] = None
        self._is_degraded = False
        self._degraded_reason: Optional[str] = None

        # 熔断器（保护主 Provider）
        self._circuit_breaker = CircuitBreaker(
            f"failover_{primary.name}",
            CircuitBreakerConfig(
                failure_rate_threshold=0.5,
                min_calls_to_evaluate=5,
                wait_duration_open_ms=failover_cooldown_s * 1000,
            ),
        )

        self._capabilities = ProviderCapabilities(
            supports_streaming=primary.get_capabilities().supports_streaming or fallback.get_capabilities().supports_streaming,
            supports_json_mode=primary.get_capabilities().supports_json_mode or fallback.get_capabilities().supports_json_mode,
        )

        logger.info(f"FailoverProvider_v3 initialized: primary={primary.name}, fallback={fallback.name}")

    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """异步生成，带主备降级（核心实现，重试由基类 ``generate_async`` 统一处理）。"""
        t0 = time.time()
        primary_healthy = await self.primary.health_check_async()

        # 检查熔断器是否允许请求主 Provider
        circuit_allows = await self._circuit_breaker.allow_request()

        if primary_healthy and circuit_allows and not self._is_degraded:
            try:
                result = await self.primary.generate_async(request)
                if result.success and result.text.strip():
                    if self._is_degraded:
                        self._is_degraded = False
                        self._degraded_reason = None
                        logger.info(f"FailoverProvider_v3: primary recovered")
                    await self._circuit_breaker.record_success(result.latency_ms)
                    self.record_success(result.latency_ms, result.input_tokens, result.output_tokens)
                    return result
                # 空响应视为失败
                raise ValueError("Empty response from primary")
            except Exception as e:
                latency_ms = (time.time() - t0) * 1000
                await self._circuit_breaker.record_failure(latency_ms, self._classify_error(e))
                self._mark_degraded("primary_failed", str(e))
                logger.warning(f"FailoverProvider_v3 primary failed: {e}")

        # 降级到备用
        try:
            result = await self.fallback.generate_async(request)
            if not result.success:
                raise RuntimeError("Fallback also failed")
            result.error_type = "degraded_to_fallback"
            self.record_success(result.latency_ms, result.input_tokens, result.output_tokens)
            logger.info(f"FailoverProvider_v3: degraded to fallback {self.fallback.name}")
            return result
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000
            metrics = self.record_failure(latency_ms, ErrorCategory.CONNECTION)
            logger.error(f"FailoverProvider_v3 both failed: {e}")
            return GenerateResult_v3(
                text="[System Error: LLM service unavailable]",
                latency_ms=latency_ms,
                success=False,
                error_type="both_failed",
                error_category=ErrorCategory.CONNECTION,
                provider_name=self.name,
            )

    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """流式生成，带主备降级。"""
        primary_healthy = await self.primary.health_check_async()
        circuit_allows = await self._circuit_breaker.allow_request()

        if primary_healthy and circuit_allows and not self._is_degraded:
            try:
                async for chunk in self.primary.stream_generate(request):
                    yield chunk
                return
            except Exception as e:
                await self._circuit_breaker.record_failure(0.0, self._classify_error(e))
                self._mark_degraded("primary_stream_failed", str(e))
                logger.warning(f"FailoverProvider_v3 primary stream failed: {e}")

        # 降级到备用流式
        try:
            async for chunk in self.fallback.stream_generate(request):
                yield chunk
        except Exception as e:
            logger.error(f"FailoverProvider_v3 fallback stream failed: {e}")
            yield StreamingChunk(
                index=0, text="", finish_reason="error",
                provider_name=self.name, model_id="failover",
            )

    async def health_check_async(self) -> bool:
        """只要有一个存活即健康。"""
        primary_ok = await self.primary.health_check_async()
        fallback_ok = await self.fallback.health_check_async()
        return primary_ok or fallback_ok

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """预估延迟 — 使用当前活跃 provider 的估算。"""
        if self._is_degraded:
            return self.fallback.estimate_latency_ms(prompt_tokens, output_tokens)
        return self.primary.estimate_latency_ms(prompt_tokens, output_tokens)

    def is_degraded(self) -> bool:
        return self._is_degraded

    def degraded_reason(self) -> Optional[str]:
        return self._degraded_reason

    def status(self) -> Dict[str, Any]:
        return {
            "is_degraded": self._is_degraded,
            "degraded_reason": self._degraded_reason,
            "primary_healthy": self.primary.health_check(),
            "fallback_healthy": self.fallback.health_check(),
            "failover_cooldown_s": self.failover_cooldown_s,
            "last_failover_time": self._last_failover_time,
            "circuit_breaker": self._circuit_breaker.get_state(),
        }

    def _mark_degraded(self, reason: str, detail: str) -> None:
        now = time.time()
        self._is_degraded = True
        self._degraded_reason = f"{reason}: {detail}"
        self._last_failover_time = now

    @staticmethod
    def _classify_error(exc: Exception) -> ErrorCategory:
        msg = str(exc).lower()
        if "timeout" in msg:
            return ErrorCategory.TIMEOUT
        if "connection" in msg or "refused" in msg:
            return ErrorCategory.CONNECTION
        return ErrorCategory.UNKNOWN
