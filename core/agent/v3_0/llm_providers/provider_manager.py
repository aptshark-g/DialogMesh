# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/provider_manager.py
────────────────────────────────────────────────
DialogMesh v3.0 Provider Manager — 全局 Provider 生命周期管理。

用途：
- 从 YAML/JSON 配置动态加载 Provider 实例
- 管理 Provider 注册、注销、热更新
- 提供统一入口：generate / stream / health
- 集成熔断器、健康检查、自动恢复
- 支持 Provider 依赖注入（如 FailoverProvider 的构造）

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.agent.v3_0.llm_providers.base import (
    GenerateRequest_v3,
    GenerateResult_v3,
    LLMProvider_v3,
)
from core.agent.v3_0.llm_providers.models import (
    ErrorCategory,
    ProviderBackend,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthReport,
    ProviderResult,
    RoutingStrategy,
    StreamingChunk,
)
from core.agent.v3_0.llm_providers.circuit_breaker import CircuitBreakerRegistry
from core.agent.v3_0.llm_providers.openai_provider import OpenAIProvider_v3
from core.agent.v3_0.llm_providers.local_provider import LocalProvider_v3
from core.agent.v3_0.llm_providers.mock_provider import MockProvider_v3
from core.agent.v3_0.llm_providers.failover_provider import FailoverProvider_v3
from core.agent.v3_0.llm_providers.hybrid_router import HybridRouter_v3

logger = logging.getLogger(__name__)


class ProviderManagerConfig(BaseModel):
    """Provider Manager 配置。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    providers: List[ProviderConfig] = Field(default_factory=list)
    routing_strategy: RoutingStrategy = RoutingStrategy.BALANCED
    fallback_chain: List[str] = Field(default_factory=list)
    enable_circuit_breaker: bool = True
    health_check_interval_s: float = 30.0
    auto_recovery: bool = True
    default_timeout_ms: int = 30000


class ProviderManager:
    """
    v3.0 Provider 管理器。

    作为全局单例使用，管理所有 LLM Provider 的生命周期。
    """

    def __init__(self, config: Optional[ProviderManagerConfig] = None):
        self.config = config or ProviderManagerConfig()
        self._providers: Dict[str, LLMProvider_v3] = {}
        self._circuit_registry = CircuitBreakerRegistry()
        self._health_reports: Dict[str, ProviderHealthReport] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._closed = False

        logger.info(f"ProviderManager initialized: strategy={self.config.routing_strategy.value}")

    # ── Provider 注册与构造 ─────────────────────────────────────────────

    def register(self, config: ProviderConfig) -> LLMProvider_v3:
        """根据配置注册并构造 Provider。"""
        provider = self._build_provider(config)
        self._providers[config.name] = provider
        if self.config.enable_circuit_breaker:
            self._circuit_registry.register(config.name)
        logger.info(f"ProviderManager registered: {config.name} ({config.backend.value})")
        return provider

    def unregister(self, name: str) -> bool:
        """注销 Provider。"""
        if name not in self._providers:
            return False
        del self._providers[name]
        self._circuit_registry.unregister(name)
        self._health_reports.pop(name, None)
        logger.info(f"ProviderManager unregistered: {name}")
        return True

    def get(self, name: str) -> Optional[LLMProvider_v3]:
        """获取指定 Provider。"""
        return self._providers.get(name)

    def get_all(self) -> Dict[str, LLMProvider_v3]:
        """获取所有 Provider。"""
        return self._providers.copy()

    def _build_provider(self, config: ProviderConfig) -> LLMProvider_v3:
        """根据 backend 类型构造 Provider 实例。"""
        if config.backend == ProviderBackend.OPENAI:
            return OpenAIProvider_v3(config)
        if config.backend == ProviderBackend.KIMI:
            return OpenAIProvider_v3(config)
        if config.backend == ProviderBackend.DEEPSEEK:
            return OpenAIProvider_v3(config)
        if config.backend == ProviderBackend.AZURE:
            return OpenAIProvider_v3(config)
        if config.backend in (ProviderBackend.OLLAMA, ProviderBackend.VLLM, ProviderBackend.LLAMACPP, ProviderBackend.TRANSFORMERS):
            return LocalProvider_v3(config)
        if config.backend == ProviderBackend.MOCK:
            return MockProvider_v3(config)
        if config.backend == ProviderBackend.HYBRID:
            return HybridRouter_v3(config)
        if config.backend == ProviderBackend.FAILOVER:
            return self._build_failover(config)
        raise ValueError(f"Unknown provider backend: {config.backend.value}")

    def _build_failover(self, config: ProviderConfig) -> FailoverProvider_v3:
        """构造 FailoverProvider（解析 metadata 中的 primary/fallback 引用）。"""
        meta = config.metadata
        primary_name = meta.get("primary")
        fallback_name = meta.get("fallback")
        if not primary_name or not fallback_name:
            raise ValueError("FailoverProvider requires 'primary' and 'fallback' in metadata")
        primary = self._providers.get(primary_name)
        fallback = self._providers.get(fallback_name)
        if not primary or not fallback:
            raise ValueError(f"Failover references unknown providers: {primary_name}, {fallback_name}")
        return FailoverProvider_v3(
            config=config,
            primary=primary,
            fallback=fallback,
            failover_cooldown_s=meta.get("failover_cooldown_s", 60.0),
        )

    # ── 统一入口 ───────────────────────────────────────────────────────

    async def generate_async(self, request: GenerateRequest_v3, provider_name: Optional[str] = None) -> GenerateResult_v3:
        """异步生成入口——代理到 generate 方法。"""
        return await self.generate(request, provider_name)

    async def generate(self, request: GenerateRequest_v3, provider_name: Optional[str] = None) -> GenerateResult_v3:
        """统一生成入口。若指定 provider_name，则直接路由到该 Provider；否则使用策略路由。"""
        if self._closed:
            return GenerateResult_v3(
                text="", success=False, error_type="manager_closed",
                error_category=ErrorCategory.UNKNOWN,
                provider_name="provider_manager",
            )

        if provider_name:
            provider = self._providers.get(provider_name)
            if not provider:
                return GenerateResult_v3(
                    text="", success=False, error_type="provider_not_found",
                    error_category=ErrorCategory.VALIDATION,
                    provider_name=provider_name,
                )
            return await provider.generate_async(request)

        # 使用 HybridRouter 策略路由
        router = self._get_or_create_router()
        return await router.generate_async(request)

    async def stream(self, request: GenerateRequest_v3, provider_name: Optional[str] = None) -> AsyncIterator[StreamingChunk]:
        """统一流式入口。"""
        if self._closed:
            yield StreamingChunk(index=0, text="", finish_reason="manager_closed", provider_name="provider_manager")
            return

        if provider_name:
            provider = self._providers.get(provider_name)
            if provider:
                async for chunk in provider.stream_generate(request):
                    yield chunk
            return

        router = self._get_or_create_router()
        async for chunk in router.stream_generate(request):
            yield chunk

    # ── 健康检查 ───────────────────────────────────────────────────────

    async def health_check(self, provider_name: Optional[str] = None) -> ProviderResult[Dict[str, Any]]:
        """执行健康检查。"""
        if provider_name:
            provider = self._providers.get(provider_name)
            if not provider:
                return ProviderResult.fail(f"Provider {provider_name} not found", ErrorCategory.VALIDATION)
            healthy = await provider.health_check_async()
            return ProviderResult.ok({"provider": provider_name, "healthy": healthy})

        results = {}
        for name, provider in self._providers.items():
            try:
                healthy = await provider.health_check_async()
                results[name] = {"healthy": healthy}
            except Exception as exc:
                results[name] = {"healthy": False, "error": str(exc)}
        return ProviderResult.ok(results)

    async def start_health_monitor(self) -> None:
        """启动后台健康监控任务。"""
        if self._health_check_task is not None:
            return
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("ProviderManager health monitor started")

    async def stop_health_monitor(self) -> None:
        """停止后台健康监控任务。"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("ProviderManager health monitor stopped")

    async def _health_monitor_loop(self) -> None:
        """健康监控循环。"""
        while not self._closed:
            try:
                await self._run_health_checks()
                await asyncio.sleep(self.config.health_check_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Health monitor loop error: {exc}")
                await asyncio.sleep(5.0)

    async def _run_health_checks(self) -> None:
        """执行一轮健康检查。"""
        for name, provider in self._providers.items():
            try:
                healthy = await provider.health_check_async()
                report = provider.get_health_report()
                self._health_reports[name] = report
                if not healthy and self.config.auto_recovery:
                    logger.warning(f"ProviderManager: {name} unhealthy, attempting recovery")
            except Exception as exc:
                logger.error(f"Health check failed for {name}: {exc}")
                self._health_reports[name] = ProviderHealthReport(
                    provider_name=name,
                    health=ProviderHealth.UNHEALTHY,
                    message=str(exc),
                )

    def get_health_reports(self) -> Dict[str, ProviderHealthReport]:
        """获取所有健康报告。"""
        return self._health_reports.copy()

    # ── 配置加载 ───────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> "ProviderManager":
        """从 YAML 配置加载 ProviderManager。"""
        import yaml
        path = path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "llm_providers_v3.yaml"
        )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderManager":
        """从字典配置加载 ProviderManager。"""
        manager_config = ProviderManagerConfig(**data.get("manager", {}))
        manager = cls(manager_config)
        for provider_data in data.get("providers", []):
            cfg = ProviderConfig(**provider_data)
            manager.register(cfg)
        return manager

    # ── 内部工具 ───────────────────────────────────────────────────────

    def _get_or_create_router(self) -> HybridRouter_v3:
        """获取或创建 HybridRouter。"""
        router_name = "__internal_router__"
        if router_name in self._providers and isinstance(self._providers[router_name], HybridRouter_v3):
            return self._providers[router_name]  # type: ignore

        router_config = ProviderConfig(
            name=router_name,
            backend=ProviderBackend.HYBRID,
            metadata={
                "strategy": self.config.routing_strategy.value,
                "fallback_chain": self.config.fallback_chain,
            },
        )
        router = HybridRouter_v3(router_config)
        for name, provider in self._providers.items():
            if name != router_name:
                router.register_provider(name, provider)
        self._providers[router_name] = router
        return router

    # ── 生命周期 ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """关闭所有 Provider 并释放资源。"""
        self._closed = True
        await self.stop_health_monitor()
        for provider in self._providers.values():
            if hasattr(provider, "close") and callable(provider.close):
                try:
                    await provider.close()
                except Exception as exc:
                    logger.warning(f"Error closing provider: {exc}")
        self._providers.clear()
        logger.info("ProviderManager closed")
