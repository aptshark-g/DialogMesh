# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/failover_provider.py
────────────────────────────────────────────
LLM 降级策略 (P1-1): FailoverProvider — 主备自动切换。

当主 Provider 失败（超时、连接错误、空响应）时，自动降级到备用 Provider。
记录降级事件和恢复状态，供外部监控。
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional
from core.agent.llm_providers.base import (
    LLMProvider,
    GenerateRequest,
    GenerateResult,
    LLMCallMetrics,
)


class FailoverProvider(LLMProvider):
    """
    主备降级包装器。

    Usage:
        primary = ProviderFactory.create({...})
        fallback = ProviderFactory.create({...})  # 不同 endpoint / 轻量模型
        provider = FailoverProvider("failover", {}, primary, fallback)
        result = provider.generate(request)
    """

    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        primary: LLMProvider,
        fallback: LLMProvider,
        failover_cooldown_s: float = 60.0,
    ):
        super().__init__(name, config)
        self.primary = primary
        self.fallback = fallback
        self._failover_cooldown_s = failover_cooldown_s
        self._last_failover_time: Optional[float] = None
        self._is_degraded = False
        self._degraded_reason: Optional[str] = None

    # ───────────────────────────────────────────────────────────────────────────
    # Core generate with failover
    # ───────────────────────────────────────────────────────────────────────────

    def generate(self, request: GenerateRequest) -> GenerateResult:
        t0 = time.time()
        primary_alive = self.primary.health_check()

        # 如果主节点健康，优先使用
        if primary_alive and not self._is_degraded:
            try:
                result = self.primary.generate(request)
                if result.text and result.text.strip():
                    # 成功 — 如果之前降级了，标记恢复
                    if self._is_degraded:
                        self._is_degraded = False
                        self._degraded_reason = None
                    self.record_metrics(result.metrics)
                    return result
                # 空响应视为失败
                raise ValueError("Empty response from primary")
            except Exception as e:
                self._mark_degraded("primary_failed", str(e))
                # fallthrough to fallback

        # 降级到备用
        try:
            result = self.fallback.generate(request)
            # 标记降级状态
            result.metrics.error_type = "degraded_to_fallback"
            self.record_metrics(result.metrics)
            return result
        except Exception as e:
            # 备用也失败 — 记录并返回空结果
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=(time.time() - t0) * 1000,
                success=False,
                error_type="both_failed",
                model_id=self.fallback.config.get("model", "unknown"),
            )
            self.record_metrics(metrics)
            return GenerateResult(
                text="[System Error: LLM service unavailable]",
                metrics=metrics,
            )

    # ───────────────────────────────────────────────────────────────────────────
    # Health & status
    # ───────────────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """只要有一个存活即健康。"""
        return self.primary.health_check() or self.fallback.health_check()

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """预估延迟 — 使用当前活跃 provider 的估算。"""
        if self._is_degraded:
            return self.fallback.estimate_latency_ms(prompt_tokens, output_tokens)
        return self.primary.estimate_latency_ms(prompt_tokens, output_tokens)

    # ───────────────────────────────────────────────────────────────────────────
    # Status introspection
    # ───────────────────────────────────────────────────────────────────────────

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
            "failover_cooldown_s": self._failover_cooldown_s,
            "last_failover_time": self._last_failover_time,
        }

    # ───────────────────────────────────────────────────────────────────────────
    # Internal
    # ───────────────────────────────────────────────────────────────────────────

    def _mark_degraded(self, reason: str, detail: str) -> None:
        now = time.time()
        self._is_degraded = True
        self._degraded_reason = f"{reason}: {detail}"
        self._last_failover_time = now
