# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/__init__.py
──────────────────────────────────────────
DialogMesh v3.0 LLM Provider 包入口。

导出的所有符号按功能分组：
  - 数据模型（models）
  - 抽象基类（base）
  - 流式支持（streaming）
  - 熔断器（circuit_breaker）
  - 具体 Provider（openai, local, mock）
  - 高阶 Provider（failover, hybrid, provider_manager）

版本：3.0.0
"""

from __future__ import annotations

from core.agent.v3_0.llm_providers.models import (
    BatchGenerateRequest,
    BatchGenerateResult,
    CallStatistics,
    CircuitState,
    ErrorCategory,
    ProviderBackend,
    ProviderCapabilities,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthReport,
    ProviderResult,
    RoutingDecision,
    RoutingStrategy,
    StreamingChunk,
    TokenPricing,
)
from core.agent.v3_0.llm_providers.base import (
    GenerateRequest_v3,
    GenerateResult_v3,
    LLMConnectionError,
    LLMProvider_v3,
    LLMRateLimitError,
    LLMTimeoutError,
)
from core.agent.v3_0.llm_providers.streaming import (
    ProgressiveJSONParser,
    SSEFormatter,
    StreamingAggregator,
    WebSocketFormatter,
)
from core.agent.v3_0.llm_providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
)
from core.agent.v3_0.llm_providers.openai_provider import OpenAIProvider_v3
from core.agent.v3_0.llm_providers.local_provider import LocalProvider_v3
from core.agent.v3_0.llm_providers.mock_provider import MockProvider_v3
from core.agent.v3_0.llm_providers.failover_provider import FailoverProvider_v3
from core.agent.v3_0.llm_providers.hybrid_router import HybridRouter_v3
from core.agent.v3_0.llm_providers.provider_manager import (
    ProviderManager,
    ProviderManagerConfig,
)

__version__ = "3.0.0"

__all__ = [
    # 数据模型
    "BatchGenerateRequest",
    "BatchGenerateResult",
    "CallStatistics",
    "CircuitState",
    "ErrorCategory",
    "ProviderBackend",
    "ProviderCapabilities",
    "ProviderConfig",
    "ProviderHealth",
    "ProviderHealthReport",
    "ProviderResult",
    "RoutingDecision",
    "RoutingStrategy",
    "StreamingChunk",
    "TokenPricing",
    # 基类
    "GenerateRequest_v3",
    "GenerateResult_v3",
    "LLMProvider_v3",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMConnectionError",
    # 流式
    "ProgressiveJSONParser",
    "SSEFormatter",
    "StreamingAggregator",
    "WebSocketFormatter",
    # 熔断器
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitBreakerRegistry",
    # Provider 实现
    "OpenAIProvider_v3",
    "LocalProvider_v3",
    "MockProvider_v3",
    "FailoverProvider_v3",
    "HybridRouter_v3",
    # 管理器
    "ProviderManager",
    "ProviderManagerConfig",
]
