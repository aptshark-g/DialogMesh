# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/hybrid_router.py
────────────────────────────────────────────
DialogMesh v3.0 Hybrid Router — 混合路由 Provider。

根据任务特征、延迟预算、隐私要求、成本模型、质量需求，
自动在多个 Provider 之间选择最优后端。

路由策略：
  - latency: 延迟优先（本地小模型 > 本地大模型 > 云端）
  - cost: 成本优先（本地 > 低价 API > 高价 API）
  - privacy: 隐私优先（强制本地）
  - quality: 质量优先（云端大模型 > 本地大模型）
  - balanced: 均衡（默认，加权评分）
  - adaptive: 自适应（基于历史成功率与延迟动态调整）

与 v2.x 的改进：
  - 原生异步，支持 stream_generate
  - 使用 Pydantic 模型（ProviderConfig, RoutingDecision）
  - 集成熔断器（CircuitBreakerRegistry）
  - 支持批量并行调用（batch_generate）
  - 详细的决策审计日志

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from core.agent.v3_0.llm_providers.base import (
    GenerateRequest_v3,
    GenerateResult_v3,
    LLMProvider_v3,
)
from core.agent.v3_0.llm_providers.models import (
    ErrorCategory,
    ProviderCapabilities,
    ProviderConfig,
    ProviderBackend,
    RoutingDecision,
    RoutingStrategy,
    StreamingChunk,
)
from core.agent.v3_0.llm_providers.circuit_breaker import CircuitBreakerRegistry
from core.agent.v3_0.llm_providers.streaming import StreamingAggregator

logger = logging.getLogger(__name__)


class HybridRouter_v3(LLMProvider_v3):
    """
    v3.0 混合路由 Provider：维护多个子 Provider，按策略动态选择。
    """

    STRATEGIES = {s.value for s in RoutingStrategy}

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.strategy = RoutingStrategy(config.metadata.get("strategy", "balanced"))
        if self.strategy.value not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {self.strategy}. Use {self.STRATEGIES}")
        self.fallback_chain: List[str] = config.metadata.get("fallback_chain", [])
        self._providers: Dict[str, LLMProvider_v3] = {}
        self._circuit_registry = CircuitBreakerRegistry()
        self._provider_configs: Dict[str, ProviderConfig] = {}

        logger.info(f"HybridRouter_v3 initialized: {self.name}, strategy={self.strategy.value}")

    def register_provider(self, pid: str, provider: LLMProvider_v3, config: Optional[ProviderConfig] = None) -> None:
        """运行时注册 Provider（支持动态扩展）。"""
        self._providers[pid] = provider
        self._provider_configs[pid] = config or provider.config
        self._circuit_registry.register(pid)
        logger.info(f"HybridRouter_v3 registered provider: {pid}")

    def unregister_provider(self, pid: str) -> bool:
        """注销 Provider。"""
        if pid in self._providers:
            del self._providers[pid]
            self._provider_configs.pop(pid, None)
            self._circuit_registry.unregister(pid)
            logger.info(f"HybridRouter_v3 unregistered provider: {pid}")
            return True
        return False

    def get_provider_ids(self) -> List[str]:
        """获取所有已注册 Provider ID。"""
        return list(self._providers.keys())

    # ── 核心路由生成 ─────────────────────────────────────────────────────

    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """按策略选择 Provider，失败时按 fallback_chain 降级（核心实现）。

        重试由基类 ``generate_async`` 统一处理；本方法负责多 Provider 候选遍历。
        """
        start_ms = time.time() * 1000
        decision = await self._make_decision(request)
        candidates = decision.candidates
        last_error = None

        # MLLM-S-01: fallback_chain 优先于自动排序的候选列表
        if self.fallback_chain:
            ordered_candidates: List[str] = []
            for pid in self.fallback_chain:
                if pid in self._providers and pid not in ordered_candidates:
                    ordered_candidates.append(pid)
            for pid in candidates:
                if pid not in ordered_candidates:
                    ordered_candidates.append(pid)
            candidates = ordered_candidates
            logger.debug(
                "HybridRouter_v3 using fallback_chain: ordered_candidates=%s",
                candidates,
            )

        logger.debug(
            "HybridRouter_v3 routing: strategy=%s, candidates=%s",
            decision.strategy.value,
            candidates,
        )

        for pid in candidates:
            provider = self._providers.get(pid)
            if provider is None:
                continue

            # 检查熔断器
            cb = self._circuit_registry.get(pid)
            if cb and not await cb.allow_request():
                logger.warning("HybridRouter_v3: circuit breaker OPEN for %s", pid)
                continue

            # 健康检查
            healthy = await provider.health_check_async()
            if not healthy:
                logger.warning("HybridRouter_v3: %s unhealthy", pid)
                continue

            try:
                result = await provider.generate_async(request)
                # 合并 metrics（标记为通过 router 路由）
                result.provider_name = f"{self.name}/{pid}"
                self.record_success(result.latency_ms, result.input_tokens, result.output_tokens)

                if cb:
                    if result.success:
                        await cb.record_success(result.latency_ms)
                    else:
                        await cb.record_failure(result.latency_ms, result.error_category or ErrorCategory.UNKNOWN)

                if result.success:
                    logger.info(
                        "HybridRouter_v3: routed to %s, latency=%.1fms",
                        pid,
                        result.latency_ms,
                    )
                    return result
                # 记录失败原因，继续下一个候选 Provider（fallback）
                last_error = result.error_type
                logger.warning(
                    "HybridRouter_v3: %s returned error=%s, trying next fallback",
                    pid,
                    last_error,
                )
            except Exception as e:
                logger.warning("HybridRouter_v3: %s generate error: %s", pid, e)
                last_error = str(e)
                if cb:
                    await cb.record_failure(0.0, ErrorCategory.UNKNOWN)

        # 全部失败
        latency_ms = (time.time() * 1000) - start_ms
        self.record_failure(latency_ms, ErrorCategory.CONNECTION)
        logger.error(
            "HybridRouter_v3: all providers failed, last_error=%s",
            last_error,
        )
        return GenerateResult_v3(
            text="",
            latency_ms=latency_ms,
            success=False,
            error_type=last_error or "all_providers_failed",
            error_category=ErrorCategory.CONNECTION,
            provider_name=self.name,
        )

    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """流式生成，按策略选择 Provider。"""
        decision = await self._make_decision(request)
        for pid in decision.candidates:
            provider = self._providers.get(pid)
            if provider is None:
                continue
            cb = self._circuit_registry.get(pid)
            if cb and not await cb.allow_request():
                continue
            healthy = await provider.health_check_async()
            if not healthy:
                continue
            try:
                async for chunk in provider.stream_generate(request):
                    chunk.provider_name = f"{self.name}/{pid}"
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"HybridRouter_v3 stream: {pid} failed: {e}")
                if cb:
                    await cb.record_failure(0.0, ErrorCategory.UNKNOWN)

        yield StreamingChunk(
            index=0, text="", finish_reason="all_providers_failed",
            provider_name=self.name, model_id="hybrid",
        )

    # ── 批量并行调用 ─────────────────────────────────────────────────────

    async def batch_generate(self, requests: List[GenerateRequest_v3], provider_ids: Optional[List[str]] = None) -> Dict[str, List[GenerateResult_v3]]:
        """并行向多个 Provider 发送请求，返回聚合结果。"""
        pids = provider_ids or list(self._providers.keys())
        results: Dict[str, List[GenerateResult_v3]] = {pid: [] for pid in pids}

        async def _call(pid: str, req: GenerateRequest_v3) -> None:
            provider = self._providers.get(pid)
            if not provider:
                return
            try:
                res = await provider.generate_async(req)
                results[pid].append(res)
            except Exception as e:
                logger.warning(f"HybridRouter_v3 batch: {pid} failed: {e}")

        tasks = []
        for pid in pids:
            for req in requests:
                tasks.append(_call(pid, req))
        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    # ── 健康检查 ───────────────────────────────────────────────────────

    async def health_check_async(self) -> bool:
        """只要有任一子 Provider 健康即返回 True。"""
        if not self._providers:
            return False
        checks = [p.health_check_async() for p in self._providers.values()]
        results = await asyncio.gather(*checks, return_exceptions=True)
        return any(r is True for r in results)

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """返回最优 Provider 的预估延迟。"""
        candidates = self._rank_providers(
            GenerateRequest_v3(prompt="", timeout_ms=30000)
        )
        for pid in candidates:
            p = self._providers.get(pid)
            if p:
                return p.estimate_latency_ms(prompt_tokens, output_tokens)
        return 99999.0

    # ── 路由决策 ───────────────────────────────────────────────────────

    async def _make_decision(self, request: GenerateRequest_v3) -> RoutingDecision:
        """生成路由决策（包含审计信息）。"""
        candidates = self._rank_providers(request)
        scores = self._score_candidates(request, candidates)
        selected = candidates[0] if candidates else ""
        reason = self._explain_decision(selected, request)
        return RoutingDecision(
            strategy=self.strategy,
            selected_provider=selected,
            candidates=candidates,
            scores=scores,
            latency_budget_ms=request.timeout_ms,
            privacy_required=request.metadata.get("privacy_sensitive", False),
            quality_required=request.metadata.get("high_quality", False),
            reason=reason,
        )

    def _rank_providers(self, request: GenerateRequest_v3) -> List[str]:
        """根据策略和请求特征排序 Provider。"""
        latency_budget = request.metadata.get("latency_budget_ms", request.timeout_ms)
        privacy_required = request.metadata.get("privacy_sensitive", False)
        quality_required = request.metadata.get("high_quality", False)
        cost_sensitive = request.metadata.get("cost_sensitive", False)

        scored: List[Tuple[str, float]] = []

        for pid, provider in self._providers.items():
            score = 0.0
            stats = provider.get_stats()
            est_latency = provider.estimate_latency_ms(256, 128)
            cfg = self._provider_configs.get(pid)
            is_local = cfg.backend in (ProviderBackend.OLLAMA, ProviderBackend.VLLM, ProviderBackend.LLAMACPP, ProviderBackend.TRANSFORMERS) if cfg else False
            pricing = cfg.pricing if cfg else None

            # latency 策略
            if self.strategy == RoutingStrategy.LATENCY:
                if est_latency <= latency_budget:
                    score += 1000 - est_latency
                else:
                    score -= 5000

            # privacy 策略
            elif self.strategy == RoutingStrategy.PRIVACY:
                if privacy_required and not is_local:
                    score -= 10000
                if is_local:
                    score += 1000
                score += 500 - est_latency

            # cost 策略
            elif self.strategy == RoutingStrategy.COST:
                if is_local:
                    score += 2000
                elif pricing:
                    # 估算成本（256 input, 128 output）
                    cost = pricing.estimate_cost(256, 128)
                    score += 1000 - cost * 1000
                else:
                    score += 500 - est_latency

            # quality 策略
            elif self.strategy == RoutingStrategy.QUALITY:
                if quality_required and not is_local:
                    score += 2000
                score += 1000 - est_latency

            # balanced 策略：综合加权
            elif self.strategy == RoutingStrategy.BALANCED:
                latency_score = max(0, 1000 - est_latency) if est_latency <= latency_budget else -5000
                cost_score = 2000 if is_local else (1000 - (pricing.estimate_cost(256, 128) * 1000 if pricing else 0))
                quality_score = 2000 if not is_local else 500
                privacy_score = 2000 if is_local else 0
                score = latency_score * 0.3 + cost_score * 0.2 + quality_score * 0.3 + privacy_score * 0.2

            # adaptive 策略：基于历史成功率动态调整
            elif self.strategy == RoutingStrategy.ADAPTIVE:
                base_score = 1000 - est_latency
                success_bonus = stats.success_rate * 2000
                latency_penalty = (stats.p95_latency_ms - latency_budget) * 2 if stats.p95_latency_ms > latency_budget else 0
                score = base_score + success_bonus - latency_penalty

            # 健康度修正
            if stats.success_rate < 0.5:
                score -= 5000
            elif stats.success_rate < 0.8:
                score -= 2000

            # P95 延迟修正
            if stats.p95_latency_ms > latency_budget * 1.5:
                score -= 3000

            # 熔断器修正
            cb = self._circuit_registry.get(pid)
            if cb and cb.is_open():
                score -= 10000

            scored.append((pid, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [pid for pid, _ in scored]

    def _score_candidates(self, request: GenerateRequest_v3, candidates: List[str]) -> Dict[str, float]:
        """计算每个候选 Provider 的评分（用于审计）。"""
        scores = {}
        latency_budget = request.metadata.get("latency_budget_ms", request.timeout_ms)
        for pid in candidates:
            provider = self._providers.get(pid)
            if not provider:
                continue
            est_latency = provider.estimate_latency_ms(256, 128)
            scores[pid] = max(0, 1000 - est_latency) if est_latency <= latency_budget else -5000
        return scores

    def _explain_decision(self, selected: str, request: GenerateRequest_v3) -> str:
        """生成决策原因说明。"""
        if not selected:
            return "No provider available"
        provider = self._providers.get(selected)
        if not provider:
            return f"Provider {selected} not found"
        latency = provider.estimate_latency_ms(256, 128)
        return f"Selected {selected} based on {self.strategy.value} strategy, estimated latency={latency:.1f}ms"

    # ── 状态查询 ───────────────────────────────────────────────────────

    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """返回所有子 Provider 的统计摘要。"""
        return {
            pid: {
                "health": provider.health_check(),
                "stats": provider.get_stats().model_dump(),
                "estimated_latency_256_128": provider.estimate_latency_ms(256, 128),
                "circuit_breaker": self._circuit_registry.get(pid).get_state() if self._circuit_registry.get(pid) else None,
            }
            for pid, provider in self._providers.items()
        }

    def get_circuit_states(self) -> Dict[str, Any]:
        """返回所有熔断器状态。"""
        return self._circuit_registry.get_all_states()
