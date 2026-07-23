# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/models.py
─────────────────────────────────────
DialogMesh v3.0 LLM Provider 数据模型。

用途：
- 定义 v3.0 LLM Provider 层的 Pydantic v2 数据模型。
- 提供流式块、Provider 配置、调用统计、Token 计价的结构化模型。
- 与 ``core.agent.v3_0.data_models`` 风格一致，使用 Pydantic v2 严格校验。

版本：3.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Set, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.agent.v3_0.data_models import (
    ComponentHealth,
    ComponentType,
    TimestampedModel,
    VersionedModel,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderBackend(str, Enum):
    """LLM Provider 后端类型——标识底层推理引擎。"""
    OPENAI = "openai"
    AZURE = "azure"
    KIMI = "kimi"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMACPP = "llamacpp"
    TRANSFORMERS = "transformers"
    MOCK = "mock"
    HYBRID = "hybrid"
    FAILOVER = "failover"


class RoutingStrategy(str, Enum):
    """混合路由策略——用于 HybridRouter 的调度决策。"""
    LATENCY = "latency"
    COST = "cost"
    PRIVACY = "privacy"
    QUALITY = "quality"
    BALANCED = "balanced"
    ADAPTIVE = "adaptive"


class ProviderHealth(str, Enum):
    """Provider 健康状态。"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitState(str, Enum):
    """熔断器状态——基于状态机实现。"""
    CLOSED = "closed"       # 正常，允许请求
    OPEN = "open"           # 熔断，拒绝请求
    HALF_OPEN = "half_open" # 半开，试探请求


class ErrorCategory(str, Enum):
    """错误分类——用于统计分析和告警策略。"""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    CONTENT_FILTER = "content_filter"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 基础模型
# ═══════════════════════════════════════════════════════════════════════════════

class TokenPricing(BaseModel):
    """Token 计价模型——支持按输入/输出分别定价。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    input_price_per_1k: float = Field(default=0.0, ge=0.0)
    output_price_per_1k: float = Field(default=0.0, ge=0.0)
    currency: str = "USD"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """估算本次调用的费用。"""
        input_cost = (input_tokens / 1000.0) * self.input_price_per_1k
        output_cost = (output_tokens / 1000.0) * self.output_price_per_1k
        return input_cost + output_cost


class ProviderCapabilities(BaseModel):
    """Provider 能力声明——描述后端支持的特性。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    supports_json_mode: bool = False
    supports_json_schema: bool = False
    supports_streaming: bool = False
    supports_system_prompt: bool = True
    supports_multi_turn: bool = True
    max_context_tokens: int = 8192
    max_output_tokens: int = 4096
    supported_models: List[str] = Field(default_factory=list)
    quantization_options: List[str] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    """Provider 配置模型——Pydantic 校验的 Provider 运行时参数。

    对应现有 v2.x 的 dict 配置，但提供严格的类型校验与默认值。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    name: str = Field(..., min_length=1)
    backend: ProviderBackend = ProviderBackend.OPENAI
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0)
    max_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    device: str = "auto"  # 仅本地后端使用
    quantization: Optional[str] = None
    backend_path: Optional[str] = None  # 本地模型路径或 Ollama 模型名

    # 路由与定价
    routing_weight: float = Field(default=1.0, ge=0.0)
    pricing: Optional[TokenPricing] = None
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)

    # 元数据
    tags: Set[str] = Field(default_factory=set)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("temperature", mode="before")
    @classmethod
    def _clamp_temperature(cls, v: Union[float, int]) -> float:
        """将 temperature 裁剪到合法范围。"""
        try:
            return float(max(0.0, min(2.0, v)))
        except Exception as exc:
            logger.warning(f"Temperature validation error ({exc}), defaulting to 0.3")
            return 0.3


class StreamingChunk(BaseModel):
    """流式响应块——SSE / WebSocket 流式推送的标准单元。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    chunk_id: str = Field(default_factory=lambda: f"chk-{Field(default_factory=lambda: str(__import__('uuid').uuid4())[:6])}")
    index: int = 0
    text: str = ""
    finish_reason: Optional[str] = None
    provider_name: str = ""
    model_id: Optional[str] = None
    latency_ms: float = 0.0
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": ..., "completion_tokens": ...}
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data):
        # 处理 chunk_id 的延迟默认
        if "chunk_id" not in data:
            import uuid
            data["chunk_id"] = f"chk-{str(uuid.uuid4())[:6]}"
        super().__init__(**data)

    def is_finished(self) -> bool:
        """判断是否为流式传输的终止块。"""
        return self.finish_reason is not None


class CallStatistics(BaseModel):
    """Provider 调用统计——用于自适应路由与监控。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    success_rate: float = 1.0
    last_error: Optional[str] = None
    last_error_category: Optional[ErrorCategory] = None
    last_called_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def record_success(self, latency_ms: float, tokens_in: int, tokens_out: int, cost: float = 0.0) -> None:
        """记录一次成功调用并更新统计量。"""
        self.total_calls += 1
        self.successful_calls += 1
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.total_cost += cost
        self.avg_latency_ms = (
            (self.avg_latency_ms * (self.total_calls - 1)) + latency_ms
        ) / self.total_calls
        self.success_rate = self.successful_calls / self.total_calls
        self.last_called_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def record_failure(self, latency_ms: float, error_category: ErrorCategory) -> None:
        """记录一次失败调用并更新统计量。"""
        self.total_calls += 1
        self.failed_calls += 1
        self.success_rate = self.successful_calls / self.total_calls
        self.last_error = error_category.value
        self.last_error_category = error_category
        self.last_called_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class RoutingDecision(BaseModel):
    """路由决策记录——用于审计与调试。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    request_id: str = Field(default_factory=lambda: f"req-{__import__('uuid').uuid4().hex[:8]}")
    strategy: RoutingStrategy = RoutingStrategy.BALANCED
    selected_provider: str = ""
    candidates: List[str] = Field(default_factory=list)
    scores: Dict[str, float] = Field(default_factory=dict)
    latency_budget_ms: float = 30000.0
    privacy_required: bool = False
    quality_required: bool = False
    reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProviderHealthReport(BaseModel):
    """Provider 健康报告——用于 /health 端点扩展。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    provider_name: str = ""
    health: ProviderHealth = ProviderHealth.UNKNOWN
    component: ComponentHealth = Field(
        default_factory=lambda: ComponentHealth(
            component=ComponentType.LLM_PROVIDER, status="unknown"
        )
    )
    stats: Optional[CallStatistics] = None
    circuit_state: Optional[CircuitState] = None
    last_check_at: Optional[datetime] = None
    message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 通用响应包装
# ═══════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


class ProviderResult(BaseModel, Generic[T]):
    """Provider 通用结果包装——统一成功/失败的数据结构。

    使用泛型 ``T`` 指定 ``data`` 字段类型，便于类型推导。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    success: bool = True
    data: Optional[T] = None
    error: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    latency_ms: float = 0.0
    request_id: str = Field(default_factory=lambda: f"req-{__import__('uuid').uuid4().hex[:8]}")
    provider_name: str = ""
    model_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls, data: T, **kwargs) -> "ProviderResult[T]":
        """构造成功结果。"""
        return cls(success=True, data=data, **kwargs)

    @classmethod
    def fail(cls, error: str, error_category: ErrorCategory = ErrorCategory.UNKNOWN, **kwargs) -> "ProviderResult[T]":
        """构造失败结果。"""
        return cls(success=False, error=error, error_category=error_category, **kwargs)


class BatchGenerateRequest(BaseModel):
    """批量生成请求——用于并行调用多个 Provider。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    requests: List["GenerateRequest_v3"] = Field(default_factory=list)
    strategy: RoutingStrategy = RoutingStrategy.BALANCED
    fallback_on_error: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.requests)


class BatchGenerateResult(BaseModel):
    """批量生成结果——聚合多 Provider 响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    results: Dict[str, "GenerateResult_v3"] = Field(default_factory=dict)
    errors: Dict[str, str] = Field(default_factory=dict)
    overall_latency_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_all_success(self) -> bool:
        """检查是否全部成功。"""
        return len(self.errors) == 0 and len(self.results) > 0

    def get_best_result(self) -> Optional["GenerateResult_v3"]:
        """按成功率与延迟综合排序，返回最优结果。"""
        if not self.results:
            return None
        best = None
        best_score = -999999.0
        for res in self.results.values():
            if not res.success:
                continue
            score = 1000.0 - res.latency_ms
            if score > best_score:
                best_score = score
                best = res
        return best


# ═══════════════════════════════════════════════════════════════════════════════
# 前向引用解析（延迟到运行时，避免循环导入）
# ═══════════════════════════════════════════════════════════════════════════════
# BatchGenerateRequest / BatchGenerateResult 引用 GenerateRequest_v3 与 GenerateResult_v3，
# 这两个类定义在 base.py 中。为避免循环导入，此处不强制 rebuild，
# 首次使用时由 Pydantic 自动解析。


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 llm_providers/models self-test ===")

        # 1. ProviderConfig
        cfg = ProviderConfig(name="test", backend=ProviderBackend.OPENAI, temperature=3.0)
        assert cfg.temperature == 2.0, "Temperature should be clamped to 2.0"
        print(f"[PASS] ProviderConfig: {cfg.name}, temp={cfg.temperature}")

        # 2. TokenPricing
        pricing = TokenPricing(input_price_per_1k=0.1, output_price_per_1k=0.3)
        cost = pricing.estimate_cost(1000, 500)
        assert cost == 0.25, f"Expected 0.25, got {cost}"
        print(f"[PASS] TokenPricing: cost={cost}")

        # 3. StreamingChunk
        chunk = StreamingChunk(index=0, text="hello", provider_name="openai")
        assert not chunk.is_finished()
        chunk_finish = StreamingChunk(index=1, text="", finish_reason="stop")
        assert chunk_finish.is_finished()
        print(f"[PASS] StreamingChunk")

        # 4. CallStatistics
        stats = CallStatistics()
        stats.record_success(120.0, 100, 50, 0.05)
        stats.record_failure(300.0, ErrorCategory.TIMEOUT)
        assert stats.success_rate == 0.5
        print(f"[PASS] CallStatistics: rate={stats.success_rate}")

        # 5. RoutingDecision
        decision = RoutingDecision(
            strategy=RoutingStrategy.LATENCY,
            selected_provider="local-1.5b",
            candidates=["local-1.5b", "cloud-api"],
            scores={"local-1.5b": 950.0, "cloud-api": 700.0},
            reason="latency budget < 50ms",
        )
        assert decision.selected_provider == "local-1.5b"
        print(f"[PASS] RoutingDecision")

        # 6. ProviderResult
        result_ok = ProviderResult[str].ok(data="hello", provider_name="test")
        result_fail = ProviderResult[str].fail(error="timeout", error_category=ErrorCategory.TIMEOUT)
        assert result_ok.success is True
        assert result_fail.success is False
        print(f"[PASS] ProviderResult")

        # 7. ProviderHealthReport
        report = ProviderHealthReport(
            provider_name="openai", health=ProviderHealth.HEALTHY, circuit_state=CircuitState.CLOSED
        )
        assert report.health == ProviderHealth.HEALTHY
        print(f"[PASS] ProviderHealthReport")

        logger.info("=== All v3.0 llm_providers/models self-tests passed ===")

    asyncio.run(_self_test())
