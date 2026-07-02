# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/base.py
──────────────────────────────────────
DialogMesh v3.0 LLM Provider 抽象基类与通用接口。

设计原则：
  - 统一接口：所有 Provider 实现相同的原生异步 ``generate_async()`` 签名
  - Pydantic 模型：请求/响应使用 Pydantic v2 严格校验
  - 延迟预算：调用方传入 timeout_ms，Provider 自行超时/降级
  - 结构化输出：支持 JSON Schema 约束，防止 LLM 自由发散
  - 流式支持：原生 async generator 流式返回，适配 SSE/WebSocket
  - 可观测：每次调用记录 latency、token_usage、error_type，供 Router 学习

与 v2.x 的兼容：
  - 保留 ``generate()`` 同步方法（线程池包装），兼容旧代码
  - 通过 ``to_v2_result()`` / ``from_v2_request()`` 实现与 v2.x 的互转

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.agent.v3_0.llm_providers.models import (
    CallStatistics,
    ErrorCategory,
    ProviderCapabilities,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthReport,
    ProviderResult,
    StreamingChunk,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 自定义异常（用于重试分类）
# ═══════════════════════════════════════════════════════════════════════════════

class LLMTimeoutError(Exception):
    """LLM 调用超时异常——触发指数退避重试。"""


class LLMRateLimitError(Exception):
    """LLM 速率限制异常——触发指数退避重试。"""


class LLMConnectionError(Exception):
    """LLM 连接异常——触发指数退避重试。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型（请求/响应）
# ═══════════════════════════════════════════════════════════════════════════════

class GenerateRequest_v3(BaseModel):
    """v3.0 标准化生成请求——Pydantic 校验的替代 v2.x GenerateRequest。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    prompt: str = ""
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None
    max_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    timeout_ms: int = Field(default=30000, ge=100)
    response_format: Optional[str] = None  # "json" | "text" | "json_schema"
    json_schema: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = False  # 是否请求流式响应

    def to_messages(self) -> List[Dict[str, str]]:
        """构建标准 messages 列表（兼容 OpenAI Chat 格式）。"""
        if self.messages:
            return self.messages.copy()
        msgs: List[Dict[str, str]] = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.append({"role": "user", "content": self.prompt})
        return msgs


class GenerateResult_v3(BaseModel):
    """v3.0 标准化生成结果——Pydantic 校验的替代 v2.x GenerateResult。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    text: str = ""
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error_type: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    status_code: Optional[int] = None
    model_id: Optional[str] = None
    provider_name: str = ""
    raw_response: Optional[Any] = None
    structured: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（兼容旧版调用）。"""
        return self.model_dump(exclude_none=False)


class LLMProvider_v3(ABC):
    """
    v3.0 LLM Provider 抽象基类。

    所有具体实现必须提供：
      - generate_async(request) -> GenerateResult_v3
      - health_check_async() -> bool
      - estimate_latency_ms(prompt_tokens, output_tokens) -> float
      - stream_generate(request) -> AsyncIterator[StreamingChunk]
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
        self._stats = CallStatistics()
        self._capabilities = config.capabilities
        logger.info(f"LLMProvider_v3 initialized: {self.name} (backend={config.backend.value})")

    # ── 抽象方法 ────────────────────────────────────────────────────────

    async def generate_async(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """带指数退避重试的异步生成包装器。

        实现 MLLM-S-01 要求：
          - 捕获 ``LLMTimeoutError``、``LLMRateLimitError``、``LLMConnectionError``
            以及子类实现返回的可重试错误（``TIMEOUT``/``RATE_LIMIT``/``CONNECTION``）。
          - 指数退避：base 1s，backoff 2x，最多重试 3 次（共 4 次尝试）。
          - 全部失败后返回 ``GenerateResult_v3(text="", success=False, error_type=...)``。

        子类应实现 ``_generate_async_impl()`` 放置核心调用逻辑，
        而不是覆盖本方法。
        """
        max_retries: int = 3
        base_delay_s: float = 1.0
        backoff: float = 2.0

        last_error: Optional[str] = None
        last_error_category: Optional[ErrorCategory] = None

        for attempt in range(max_retries + 1):
            try:
                result = await self._generate_async_impl(request)
                # 子类内部返回了可重试错误 → 同样触发重试
                if (
                    not result.success
                    and result.error_category
                    and result.error_category in (
                        ErrorCategory.TIMEOUT,
                        ErrorCategory.RATE_LIMIT,
                        ErrorCategory.CONNECTION,
                    )
                ):
                    if attempt < max_retries:
                        last_error = result.error_type or result.error_category.value
                        last_error_category = result.error_category
                        delay = base_delay_s * (backoff ** attempt)
                        logger.warning(
                            "[%s] generate attempt %d failed with %s, retrying in %.1fs",
                            self.name,
                            attempt + 1,
                            last_error_category.value,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                return result

            except (LLMTimeoutError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                last_error_category = ErrorCategory.TIMEOUT
            except LLMRateLimitError as exc:
                last_error = str(exc)
                last_error_category = ErrorCategory.RATE_LIMIT
            except LLMConnectionError as exc:
                last_error = str(exc)
                last_error_category = ErrorCategory.CONNECTION
            except Exception as exc:
                # 不可重试的异常，直接返回失败结果（不再重试）
                logger.error(
                    "[%s] unrecoverable error in generate_async: %s",
                    self.name,
                    exc,
                )
                return GenerateResult_v3(
                    text="",
                    success=False,
                    error_type=str(exc),
                    error_category=self._classify_error(exc),
                    provider_name=self.name,
                )

            # 还有重试次数
            if attempt < max_retries:
                delay = base_delay_s * (backoff ** attempt)
                logger.warning(
                    "[%s] generate attempt %d failed with %s, retrying in %.1fs",
                    self.name,
                    attempt + 1,
                    last_error_category.value if last_error_category else "unknown",
                    delay,
                )
                await asyncio.sleep(delay)

        # 全部重试失败
        logger.error(
            "[%s] all %d generate attempts failed, last_error=%s",
            self.name,
            max_retries + 1,
            last_error,
        )
        return GenerateResult_v3(
            text="",
            success=False,
            error_type=last_error or "max_retries_exceeded",
            error_category=last_error_category or ErrorCategory.UNKNOWN,
            provider_name=self.name,
        )

    @abstractmethod
    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """子类必须实现的核心异步生成逻辑。

        本方法**不应**实现重试逻辑——重试由 ``generate_async`` 统一处理。
        遇到可重试错误时，建议抛出 ``LLMTimeoutError`` / ``LLMRateLimitError`` /
        ``LLMConnectionError``，或返回 ``success=False`` 且 ``error_category`` 为
        ``TIMEOUT`` / ``RATE_LIMIT`` / ``CONNECTION`` 的 ``GenerateResult_v3``。
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check_async(self) -> bool:
        """快速异步健康检查（< 1000ms）。返回 True/False，不抛异常。"""
        raise NotImplementedError

    @abstractmethod
    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """基于 prompt 长度预估延迟（ms），用于 Router 预筛选。"""
        raise NotImplementedError

    @abstractmethod
    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """原生异步流式生成。返回 AsyncIterator[StreamingChunk]。"""
        raise NotImplementedError

    # ── 同步兼容方法（线程池包装）───────────────────────────────────────

    def generate(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """同步入口：在线程池中运行 async 方法。兼容旧代码。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中（如 Jupyter），使用 run_coroutine_threadsafe
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.generate_async(request))
                    return future.result(timeout=request.timeout_ms / 1000.0 + 5.0)
            else:
                return asyncio.run(self.generate_async(request))
        except Exception as exc:
            logger.error(f"generate() sync wrapper failed for {self.name}: {exc}")
            return GenerateResult_v3(
                text="",
                success=False,
                error_type="sync_wrapper_error",
                error_category=ErrorCategory.UNKNOWN,
                provider_name=self.name,
            )

    def health_check(self) -> bool:
        """同步健康检查（线程池包装）。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.health_check_async())
                    return future.result(timeout=5.0)
            return asyncio.run(self.health_check_async())
        except Exception as exc:
            logger.error(f"health_check() sync wrapper failed for {self.name}: {exc}")
            return False

    # ── 统计与指标 ───────────────────────────────────────────────────────

    def record_success(self, latency_ms: float, input_tokens: int, output_tokens: int, cost: float = 0.0) -> None:
        """记录成功调用。"""
        self._stats.record_success(latency_ms, input_tokens, output_tokens, cost)

    def record_failure(self, latency_ms: float, error_category: ErrorCategory) -> None:
        """记录失败调用。"""
        self._stats.record_failure(latency_ms, error_category)

    def get_stats(self) -> CallStatistics:
        """获取当前统计。"""
        return self._stats.model_copy()

    def get_health_report(self) -> ProviderHealthReport:
        """生成健康报告。"""
        health = ProviderHealth.HEALTHY if self._stats.success_rate > 0.8 else (
            ProviderHealth.DEGRADED if self._stats.success_rate > 0.3 else ProviderHealth.UNHEALTHY
        )
        from core.agent.v3_0.data_models import ComponentHealth, ComponentType
        return ProviderHealthReport(
            provider_name=self.name,
            health=health,
            component=ComponentHealth(
                component=ComponentType.LLM_PROVIDER,
                status="ok" if health == ProviderHealth.HEALTHY else (
                    "warn" if health == ProviderHealth.DEGRADED else "error"
                ),
                latency_ms=self._stats.avg_latency_ms,
                message=f"success_rate={self._stats.success_rate:.2f}",
            ),
            stats=self._stats.model_copy(),
            last_check_at=__import__("datetime").datetime.utcnow(),
        )

    # ── 能力查询 ─────────────────────────────────────────────────────────

    def get_capabilities(self) -> ProviderCapabilities:
        """返回 Provider 能力声明。"""
        return self._capabilities

    # ── 工具函数 ─────────────────────────────────────────────────────────

    def _classify_error(self, exc: Exception) -> ErrorCategory:
        """根据异常类型自动分类错误。"""
        msg = str(exc).lower()
        if isinstance(exc, asyncio.TimeoutError) or "timeout" in msg:
            return ErrorCategory.TIMEOUT
        if "rate" in msg or "429" in msg or "too many" in msg:
            return ErrorCategory.RATE_LIMIT
        if "auth" in msg or "api key" in msg or "401" in msg or "403" in msg:
            return ErrorCategory.AUTHENTICATION
        if "content" in msg or "moderation" in msg or "filter" in msg:
            return ErrorCategory.CONTENT_FILTER
        if "balance" in msg or "credit" in msg or "insufficient" in msg or "402" in msg:
            return ErrorCategory.INSUFFICIENT_FUNDS
        if "connection" in msg or "network" in msg or "dns" in msg or "refused" in msg:
            return ErrorCategory.CONNECTION
        if "json" in msg or "schema" in msg or "validation" in msg:
            return ErrorCategory.VALIDATION
        return ErrorCategory.UNKNOWN

    def _safe_json_parse(self, text: str) -> Optional[Dict[str, Any]]:
        """安全解析 JSON，支持 Markdown 代码块提取。"""
        import json
        import re
        # 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 提取 ```json ... ``` 代码块
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 提取最外层 { ... }
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    async def _with_timeout(self, coro, timeout_ms: int) -> Any:
        """内部辅助：为协程添加超时。"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            raise

    # ── v2.x 兼容转换 ───────────────────────────────────────────────────

    def from_v2_request(self, v2_request) -> GenerateRequest_v3:
        """从 v2.x GenerateRequest 转换为 v3 请求。"""
        from core.agent.llm_providers.base import GenerateRequest
        if isinstance(v2_request, GenerateRequest):
            return GenerateRequest_v3(
                prompt=v2_request.prompt,
                system_prompt=v2_request.system_prompt,
                messages=v2_request.messages,
                max_tokens=v2_request.max_tokens,
                temperature=v2_request.temperature,
                timeout_ms=v2_request.timeout_ms,
                response_format=v2_request.response_format,
                json_schema=v2_request.json_schema,
                metadata=v2_request.metadata,
            )
        # 已经是 v3 请求
        if isinstance(v2_request, GenerateRequest_v3):
            return v2_request
        # 字典兼容
        if isinstance(v2_request, dict):
            return GenerateRequest_v3(**v2_request)
        raise TypeError(f"Cannot convert {type(v2_request)} to GenerateRequest_v3")

    def to_v2_result(self, v3_result: GenerateResult_v3) -> Any:
        """从 v3 结果转换为 v2.x GenerateResult。"""
        from core.agent.llm_providers.base import GenerateResult, LLMCallMetrics
        metrics = LLMCallMetrics(
            provider_name=v3_result.provider_name or self.name,
            latency_ms=v3_result.latency_ms,
            input_tokens=v3_result.input_tokens,
            output_tokens=v3_result.output_tokens,
            success=v3_result.success,
            error_type=v3_result.error_type,
            status_code=v3_result.status_code,
            model_id=v3_result.model_id,
        )
        return GenerateResult(
            text=v3_result.text,
            metrics=metrics,
            raw_response=v3_result.raw_response,
            structured=v3_result.structured,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, backend={self.config.backend.value})"
