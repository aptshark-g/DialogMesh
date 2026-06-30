# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/hybrid_router.py
───────────────────────────────────────────
混合路由 Provider（v2.4 新增）。

根据任务特征、延迟预算、隐私要求、成本模型，
自动在多个 Provider 之间选择最优后端。

路由策略：
  - 延迟 < 50ms  → 本地 1.5B（Qwen2.5-1.5B）
  - 延迟 < 200ms → 本地 7B / vLLM
  - 延迟 > 200ms 或 本地不可用 → 云端 API
  - 隐私敏感（医疗/密码）→ 强制本地
  - 成本敏感 → 优先本地 / 缓存命中

配置项：
  - providers: 子 Provider 配置列表
  - default_strategy: "latency" | "cost" | "privacy" | "quality"
  - fallback_chain: 失败时的降级顺序
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.llm_providers.mock_provider import MockProvider

from core.agent.llm_providers.base import (
    LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics,
)
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.llm_providers.local_provider import LocalProvider


class HybridRouter(LLMProvider):
    """
    混合路由 Provider：维护多个子 Provider，按策略动态选择。
    """

    STRATEGIES = {"latency", "cost", "privacy", "quality"}

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.strategy = config.get("default_strategy", "latency")
        if self.strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {self.strategy}. Use {self.STRATEGIES}")
        self.fallback_chain: List[str] = config.get("fallback_chain", [])
        self._providers: Dict[str, LLMProvider] = {}
        self._build_providers(config.get("providers", []))

    def _build_providers(self, provider_configs: List[Dict[str, Any]]):
        """根据配置实例化子 Provider。"""
        for pc in provider_configs:
            pid = pc["id"]
            ptype = pc.get("type", "openai")
            if ptype == "openai":
                self._providers[pid] = OpenAIProvider(pid, pc)
            elif ptype == "local":
                self._providers[pid] = LocalProvider(pid, pc)
            elif ptype == "mock":
                self._providers[pid] = MockProvider(pid, pc)
            elif ptype == "hybrid":
                self._providers[pid] = HybridRouter(pid, pc)
            else:
                raise ValueError(f"Unknown provider type: {ptype}")

    def register_provider(self, pid: str, provider: LLMProvider) -> None:
        """运行时注册（用于测试或动态扩展）。"""
        self._providers[pid] = provider

    def generate(self, request: GenerateRequest) -> GenerateResult:
        """
        按策略选择 Provider，失败时按 fallback_chain 降级。
        """
        candidates = self._rank_providers(request)
        last_error = None

        for pid in candidates:
            provider = self._providers.get(pid)
            if provider is None:
                continue
            if not provider.health_check():
                continue

            result = provider.generate(request)
            # 合并 metrics（标记为通过 router 路由）
            result.metrics.provider_name = f"{self.name}/{pid}"
            self.record_metrics(result.metrics)

            if result.metrics.success:
                return result
            last_error = result.metrics.error_type

        # 全部失败：返回空结果 + 错误标记
        metrics = LLMCallMetrics(
            provider_name=self.name, latency_ms=0,
            success=False, error_type=last_error or "all_providers_failed",
        )
        self.record_metrics(metrics)
        return GenerateResult(text="", metrics=metrics)

    def health_check(self) -> bool:
        """只要有任一子 Provider 健康即返回 True。"""
        return any(p.health_check() for p in self._providers.values())

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """返回最优 Provider 的预估延迟。"""
        candidates = self._rank_providers(
            GenerateRequest(prompt="", timeout_ms=30000)
        )
        for pid in candidates:
            p = self._providers.get(pid)
            if p and p.health_check():
                return p.estimate_latency_ms(prompt_tokens, output_tokens)
        return 99999.0

    def _rank_providers(self, request: GenerateRequest) -> List[str]:
        """
        根据策略和请求特征排序 Provider。
        返回候选 ID 列表（按优先级降序）。
        """
        # 1. 根据请求元数据提取特征
        latency_budget = request.metadata.get("latency_budget_ms", 30000)
        privacy_required = request.metadata.get("privacy_sensitive", False)
        quality_required = request.metadata.get("high_quality", False)

        scored: List[Tuple[str, float]] = []

        for pid, provider in self._providers.items():
            score = 0.0
            stats = provider.get_recent_stats(window=10)
            est_latency = provider.estimate_latency_ms(256, 128)

            # 策略：latency —— 越低越好
            if self.strategy == "latency":
                if est_latency <= latency_budget:
                    score += 1000 - est_latency
                else:
                    score -= 5000

            # 策略：privacy —— 本地优先
            elif self.strategy == "privacy":
                is_local = isinstance(provider, LocalProvider)
                if privacy_required and not is_local:
                    score -= 10000
                if is_local:
                    score += 1000
                score += 500 - est_latency

            # 策略：cost —— 本地 > API 免费层 > API 付费
            elif self.strategy == "cost":
                is_local = isinstance(provider, LocalProvider)
                if is_local:
                    score += 2000
                else:
                    score += 500 - est_latency

            # 策略：quality —— 云端大模型优先，但本地 7B 也可
            elif self.strategy == "quality":
                if quality_required and isinstance(provider, OpenAIProvider):
                    score += 2000
                score += 1000 - est_latency

            # 健康度修正：近期成功率低的降级
            if stats["success_rate"] < 0.8:
                score -= 2000
            elif stats["success_rate"] < 0.5:
                score -= 5000

            # P95 延迟修正：如果近期 P95 超过预算，大幅降权
            if stats["p95_latency_ms"] > latency_budget * 1.5:
                score -= 3000

            scored.append((pid, score))

        # 按分数降序排列
        scored.sort(key=lambda x: x[1], reverse=True)
        return [pid for pid, _ in scored]

    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """返回所有子 Provider 的统计摘要。"""
        return {
            pid: {
                "health": p.health_check(),
                "stats": p.get_recent_stats(),
                "estimated_latency_256_128": p.estimate_latency_ms(256, 128),
            }
            for pid, p in self._providers.items()
        }
