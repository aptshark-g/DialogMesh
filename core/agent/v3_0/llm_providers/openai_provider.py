# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/openai_provider.py
──────────────────────────────────────────────
DialogMesh v3.0 OpenAI / 兼容 API Provider。

支持：OpenAI、Kimi（Moonshot）、DeepSeek、Qwen API、Azure OpenAI 等
兼容 OpenAI SDK 的云端服务。

特性：
  - 原生异步生成（openai.AsyncOpenAI）
  - 流式响应（AsyncIterator[StreamingChunk]）
  - 结构化输出（JSON mode / JSON Schema）
  - 自动重试与降级（response_format 不支持时自动回退）
  - 完整的错误分类与遥测

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
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
    ProviderBackend,
    ProviderCapabilities,
    ProviderConfig,
    ProviderHealth,
    StreamingChunk,
    TokenPricing,
)
from core.agent.v3_0.llm_providers.streaming import StreamingAggregator

logger = logging.getLogger(__name__)


class OpenAIProvider_v3(LLMProvider_v3):
    """
    v3.0 OpenAI API 兼容 Provider。
    使用 openai 库（可选安装：pip install openai>=1.0.0）。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._async_client: Optional[Any] = None
        self._sync_client: Optional[Any] = None

        # 自动探测后端类型（基于 base_url）
        backend = self._detect_backend(config)
        if config.backend != backend:
            config.backend = backend
            logger.info(f"OpenAIProvider_v3 auto-detected backend: {backend.value}")

        # 设置默认能力
        self._capabilities = config.capabilities or ProviderCapabilities(
            supports_json_mode=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_multi_turn=True,
            max_context_tokens=128000,
            max_output_tokens=4096,
            supported_models=[config.model],
        )

        # 设置默认定价（按需扩展）
        if not config.pricing:
            config.pricing = self._default_pricing(config.backend, config.model)

        logger.info(
            f"OpenAIProvider_v3 ready: {config.name}, model={config.model}, "
            f"backend={config.backend.value}"
        )

    def _detect_backend(self, config: ProviderConfig) -> ProviderBackend:
        """基于 base_url 自动探测后端类型。"""
        url = (config.base_url or "").lower()
        if "moonshot" in url or "kimi" in url:
            return ProviderBackend.KIMI
        if "deepseek" in url:
            return ProviderBackend.DEEPSEEK
        if "azure" in url or "openai.azure" in url:
            return ProviderBackend.AZURE
        return ProviderBackend.OPENAI

    def _default_pricing(self, backend: ProviderBackend, model: str) -> TokenPricing:
        """返回默认定价模型。"""
        if backend == ProviderBackend.OPENAI:
            if "gpt-4o-mini" in model:
                return TokenPricing(input_price_per_1k=0.15, output_price_per_1k=0.60)
            if "gpt-4o" in model:
                return TokenPricing(input_price_per_1k=2.50, output_price_per_1k=10.00)
        if backend == ProviderBackend.KIMI:
            return TokenPricing(input_price_per_1k=0.10, output_price_per_1k=0.30)
        if backend == ProviderBackend.DEEPSEEK:
            return TokenPricing(input_price_per_1k=0.07, output_price_per_1k=0.30)
        return TokenPricing(input_price_per_1k=0.0, output_price_per_1k=0.0)

    def _get_async_client(self) -> Any:
        """延迟初始化异步 OpenAI client。"""
        if self._async_client is None:
            try:
                import openai
                kwargs: Dict[str, Any] = {
                    "api_key": self.config.api_key or "",
                    "base_url": self.config.base_url,
                    "max_retries": self.config.max_retries,
                    "timeout": self.config.timeout_seconds,
                }
                if self.config.backend == ProviderBackend.AZURE:
                    kwargs["api_version"] = self.config.metadata.get("api_version", "2024-02-01")
                self._async_client = openai.AsyncOpenAI(**kwargs)
            except ImportError:
                raise RuntimeError(
                    "openai library not installed. "
                    "Install with: pip install openai>=1.0.0"
                )
        return self._async_client

    def _get_sync_client(self) -> Any:
        """延迟初始化同步 OpenAI client（降级用）。"""
        if self._sync_client is None:
            try:
                import openai
                kwargs: Dict[str, Any] = {
                    "api_key": self.config.api_key or "",
                    "base_url": self.config.base_url,
                    "max_retries": self.config.max_retries,
                    "timeout": self.config.timeout_seconds,
                }
                if self.config.backend == ProviderBackend.AZURE:
                    kwargs["api_version"] = self.config.metadata.get("api_version", "2024-02-01")
                self._sync_client = openai.OpenAI(**kwargs)
            except ImportError:
                raise RuntimeError(
                    "openai library not installed. "
                    "Install with: pip install openai>=1.0.0"
                )
        return self._sync_client

    def _extract_text(self, message: Any) -> str:
        """从 OpenAI 消息对象中提取文本，兼容 reasoning 模型。"""
        text = getattr(message, "content", None) or ""
        reasoning = getattr(message, "reasoning_content", "")

        if text:
            return text

        if not reasoning:
            return ""

        reasoning = reasoning.strip()
        markers = [
            "Final Response:", "Final Choice:", "Final Decision:", "Final Output:", "Final Polish:",
            "Output:", "Draft:", "Reply:", "Answer:", "Response:", "Polished:",
            "最终回复：", "最终输出：", "最终选择：", "最终润色：",
            "Step 6", "6.  **Final", "6.  *Final",
        ]
        for marker in markers:
            idx = reasoning.rfind(marker)
            if idx != -1:
                result = reasoning[idx + len(marker):].strip()
                if result:
                    return result

        paragraphs = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
        skip_prefixes = (
            "Thinking", "Analyze", "Determine", "Interpret", "Evaluate",
            "Drafting", "Refining", "Polishing", "Conclusion", "Review",
            "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.",
            "Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6",
            "*", "**", "-",
        )
        for p in reversed(paragraphs):
            if not any(p.startswith(sp) for sp in skip_prefixes):
                if p.startswith('"') and p.endswith('"'):
                    p = p[1:-1].strip()
                if p:
                    return p
        if paragraphs:
            last = paragraphs[-1]
            if last.startswith('"') and last.endswith('"'):
                last = last[1:-1].strip()
            return last
        return reasoning

    def _build_kwargs(self, request: GenerateRequest_v3) -> Dict[str, Any]:
        """构建 OpenAI API 参数。"""
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": request.to_messages(),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        elif request.response_format == "json_schema" and request.json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.json_schema.get("name", "schema"),
                    "schema": request.json_schema,
                    "strict": True,
                }
            }
        return kwargs

    # ── 核心异步生成 ─────────────────────────────────────────────────────

    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """原生异步生成（核心实现，重试由基类 ``generate_async`` 统一处理）。"""
        start_ms = time.time() * 1000

        if request.stream:
            aggregator = StreamingAggregator(
                provider_name=self.name,
                model_id=self.config.model,
            )
            return await aggregator.consume(self.stream_generate(request))

        client = self._get_async_client()
        kwargs = self._build_kwargs(request)

        try:
            response = await self._with_timeout(
                client.chat.completions.create(**kwargs),
                request.timeout_ms,
            )
            text = self._extract_text(response.choices[0].message)
            latency_ms = (time.time() * 1000) - start_ms

            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            reasoning = getattr(choice.message, "reasoning_content", "")
            if not text and finish_reason == "length" and reasoning:
                text = "[模型思考过程被截断，请增加 max_tokens 或禁用 thinking 模式]"
            elif not text and finish_reason == "length":
                text = "[回复被截断，请增加 max_tokens]"
            elif len(text) < 5 and finish_reason == "length":
                text = text + " [回复可能被截断]"

            usage = response.usage
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            cost = 0.0
            if self.config.pricing:
                cost = self.config.pricing.estimate_cost(input_tokens, output_tokens)
            self.record_success(latency_ms, input_tokens, output_tokens, cost)

            structured = None
            if request.response_format in ("json", "json_schema"):
                structured = self._safe_json_parse(text)

            return GenerateResult_v3(
                text=text,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                model_id=self.config.model,
                provider_name=self.name,
                structured=structured,
                finish_reason=finish_reason,
                raw_response=response,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() * 1000) - start_ms
            self.record_failure(latency_ms, ErrorCategory.TIMEOUT)
            logger.warning(f"OpenAIProvider_v3 timeout: {self.name}")
            return GenerateResult_v3(
                text="",
                latency_ms=latency_ms,
                success=False,
                error_type="timeout",
                error_category=ErrorCategory.TIMEOUT,
                provider_name=self.name,
                model_id=self.config.model,
            )

        except Exception as exc:
            latency_ms = (time.time() * 1000) - start_ms
            error_category = self._classify_error(exc)

            # 自动降级：response_format 不被支持时重试
            if kwargs.get("response_format") and any(
                kw in str(exc).lower()
                for kw in ["response_format", "json_object", "not supported", "bad request", "invalid"]
            ):
                logger.warning(f"OpenAIProvider_v3 response_format not supported, retrying plain text...")
                kwargs.pop("response_format", None)
                try:
                    response = await self._with_timeout(
                        client.chat.completions.create(**kwargs),
                        request.timeout_ms,
                    )
                    text = self._extract_text(response.choices[0].message)
                    latency_ms = (time.time() * 1000) - start_ms
                    usage = response.usage
                    input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
                    output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
                    self.record_success(latency_ms, input_tokens, output_tokens)
                    structured = self._safe_json_parse(text) if request.response_format else None
                    return GenerateResult_v3(
                        text=text, latency_ms=latency_ms,
                        input_tokens=input_tokens, output_tokens=output_tokens,
                        success=True, model_id=self.config.model,
                        provider_name=self.name, structured=structured,
                        raw_response=response,
                    )
                except Exception:
                    pass

            self.record_failure(latency_ms, error_category)
            logger.error(f"OpenAIProvider_v3 error: {exc}")
            return GenerateResult_v3(
                text="",
                latency_ms=latency_ms,
                success=False,
                error_type=error_category.value,
                error_category=error_category,
                provider_name=self.name,
                model_id=self.config.model,
            )

    # ── 流式生成 ───────────────────────────────────────────────────────

    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """原生异步流式生成。"""
        start_ms = time.time() * 1000
        client = self._get_async_client()
        kwargs = self._build_kwargs(request)
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}

        try:
            stream = await self._with_timeout(
                client.chat.completions.create(**kwargs),
                request.timeout_ms,
            )
            index = 0
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                text = getattr(delta, "content", "") or ""
                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                usage = getattr(chunk, "usage", None)
                usage_dict = None
                if usage:
                    usage_dict = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                    }

                yield StreamingChunk(
                    index=index,
                    text=text,
                    finish_reason=finish_reason,
                    provider_name=self.name,
                    model_id=self.config.model,
                    latency_ms=(time.time() * 1000) - start_ms,
                    usage=usage_dict,
                )
                if finish_reason:
                    break
                index += 1

        except asyncio.TimeoutError:
            logger.warning(f"OpenAIProvider_v3 stream timeout: {self.name}")
            yield StreamingChunk(
                index=0, text="", finish_reason="timeout",
                provider_name=self.name, model_id=self.config.model,
            )
        except Exception as exc:
            logger.error(f"OpenAIProvider_v3 stream error: {exc}")
            yield StreamingChunk(
                index=0, text="", finish_reason="error",
                provider_name=self.name, model_id=self.config.model,
            )

    # ── 健康检查 ───────────────────────────────────────────────────────

    async def health_check_async(self) -> bool:
        """异步健康检查：发送最小请求。"""
        try:
            req = GenerateRequest_v3(prompt="hi", max_tokens=1, timeout_ms=5000)
            result = await self.generate_async(req)
            return result.success
        except Exception as exc:
            logger.warning(f"OpenAIProvider_v3 health check failed: {exc}")
            return False

    # ── 延迟预估 ───────────────────────────────────────────────────────

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """
        基于经验公式预估延迟。
        云端 API：首 token 延迟 ~200ms + 每 token ~20ms。
        """
        backend_factors = {
            ProviderBackend.OPENAI: (200, 20),
            ProviderBackend.AZURE: (250, 22),
            ProviderBackend.KIMI: (300, 25),
            ProviderBackend.DEEPSEEK: (350, 18),
        }
        base, per_token = backend_factors.get(self.config.backend, (200, 20))
        return base + (prompt_tokens + output_tokens) * per_token

    # ── 资源清理 ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """关闭异步 client，释放资源。"""
        if self._async_client:
            try:
                await self._async_client.close()
                self._async_client = None
            except Exception as exc:
                logger.warning(f"OpenAIProvider_v3 close error: {exc}")
