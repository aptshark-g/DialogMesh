# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/openai_provider.py
──────────────────────────────────────────────
OpenAI API / 兼容 API Provider（v2.4 新增）。

支持：OpenAI、Kimi（Moonshot）、DeepSeek、Qwen API、AnyScale 等
兼容 OpenAI SDK 的云端服务。

配置项：
  - api_key: API 密钥
  - base_url: 自定义 Base URL（如 Kimi: https://api.moonshot.cn/v1）
  - model: 模型 ID（如 "gpt-4o-mini", "kimi-latest", "deepseek-chat"）
  - max_retries: 最大重试次数（默认 2）
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.agent.llm_providers.base import (
    LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics,
)


class OpenAIProvider(LLMProvider):
    """
    OpenAI API 兼容 Provider。
    使用 openai 库（可选安装：pip install openai）。
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.model = config.get("model", "gpt-4o-mini")
        self.max_retries = config.get("max_retries", 2)
        self.timeout_s = config.get("timeout_s", 30)
        self._client = None
        # P2-1: 常驻线程池，避免每次调用创建/销毁开销
        import concurrent.futures
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _wrap_with_timeout(self, fn, timeout_ms: int, *args, **kwargs):
        """使用常驻线程池执行带超时调用。"""
        future = self._executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"LLM call exceeded {timeout_ms}ms")

    def _get_client(self):
        """延迟初始化 OpenAI client。"""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    max_retries=self.max_retries,
                    timeout=self.timeout_s,
                )
            except ImportError:
                raise RuntimeError(
                    "openai library not installed. "
                    "Install with: pip install openai"
                )
        return self._client

    def _extract_text_from_response(self, response) -> str:
        """从 OpenAI 响应中提取文本，兼容 reasoning 模型。

        Qwen 3.5 等 thinking 模型可能把思考过程放在 reasoning_content 中，
        实际回复在 content 中。如果 content 为空，尝试从 reasoning 中提取。
        """
        text = response.choices[0].message.content or ""
        reasoning = getattr(response.choices[0].message, "reasoning_content", "")

        if text:
            return text

        if not reasoning:
            return ""

        # content 为空但 reasoning 有内容：从 reasoning 中提取实际回复
        # 策略：找最后一段（通常是最终回复），去掉 Thinking Process 前缀
        reasoning = reasoning.strip()

        # 尝试找 Final / Draft / Output 标记后的内容
        markers = [
            "Final Response:", "Final Choice:", "Final Decision:", "Final Output:", "Final Polish:",
            "Output:", "Draft:", "Reply:", "Answer:", "Response:", "Polished:",
            "最终回复：", "最终输出：", "最终选择：", "最终润色：",
            "Step 6", "6.  **Final", "6.  *Final",
        ]
        for marker in markers:
            idx = reasoning.rfind(marker)  # 用 rfind 找最后一个
            if idx != -1:
                result = reasoning[idx + len(marker):].strip()
                if result:
                    return result

        # 没有找到标记：提取最后一段（按双换行分隔）
        paragraphs = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
        if paragraphs:
            # 过滤掉以数字、Thinking、Analyze、Determine、Drafting、Refining 等开头的段落
            skip_prefixes = (
                "Thinking", "Analyze", "Determine", "Interpret", "Evaluate",
                "Drafting", "Refining", "Polishing", "Conclusion", "Review",
                "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.",
                "Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6",
                "*", "**", "-",
            )
            for p in reversed(paragraphs):
                if not any(p.startswith(sp) for sp in skip_prefixes):
                    # 去掉引号包裹
                    if p.startswith('"') and p.endswith('"'):
                        p = p[1:-1].strip()
                    if p:
                        return p
            # 如果全部都被过滤，返回最后一段（去掉引号）
            last = paragraphs[-1]
            if last.startswith('"') and last.endswith('"'):
                last = last[1:-1].strip()
            return last

        return reasoning

    def generate(self, request: GenerateRequest) -> GenerateResult:
        start_ms = time.time() * 1000
        client = self._get_client()

        # 优先使用调用方传入的标准 messages 列表
        if request.messages:
            messages = request.messages.copy()
        else:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._wrap_with_timeout(
                client.chat.completions.create,
                request.timeout_ms,
                **kwargs
            )
            text = self._extract_text_from_response(response)
            latency_ms = (time.time() * 1000) - start_ms

            # 检测 thinking 模式截断
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
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=latency_ms,
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                success=True,
                model_id=self.model,
            )
            self.record_metrics(metrics)

            structured = None
            if request.response_format == "json":
                structured = self._safe_json_parse(text)

            return GenerateResult(
                text=text, metrics=metrics, raw_response=response,
                structured=structured,
            )

        except Exception as e_first:
            # 重试：如果是因为 response_format 不被支持（LM Studio / local llama.cpp）
            if kwargs.get("response_format") and ("response_format" in str(e_first).lower() or "json_object" in str(e_first).lower() or "not supported" in str(e_first).lower() or "bad request" in str(e_first).lower() or "invalid" in str(e_first).lower()):
                print(f"    [WARN] response_format=json_object 不被后端支持，自动重试（plain text）...")
                kwargs.pop("response_format", None)
                try:
                    response = self._wrap_with_timeout(
                        client.chat.completions.create,
                        request.timeout_ms,
                        **kwargs
                    )
                    text = self._extract_text_from_response(response)
                    latency_ms = (time.time() * 1000) - start_ms

                    usage = response.usage
                    metrics = LLMCallMetrics(
                        provider_name=self.name,
                        latency_ms=latency_ms,
                        input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                        output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                        success=True,
                        model_id=self.model,
                    )
                    self.record_metrics(metrics)

                    structured = None
                    if request.response_format == "json":
                        structured = self._safe_json_parse(text)

                    return GenerateResult(
                        text=text, metrics=metrics, raw_response=response,
                        structured=structured,
                    )
                except Exception:
                    pass  # 落到下面的统一异常处理

            # 统一异常处理
            if isinstance(e_first, TimeoutError):
                latency_ms = (time.time() * 1000) - start_ms
                metrics = LLMCallMetrics(
                    provider_name=self.name, latency_ms=latency_ms,
                    success=False, error_type="timeout",
                )
                self.record_metrics(metrics)
                return GenerateResult(
                    text="", metrics=metrics,
                )

            latency_ms = (time.time() * 1000) - start_ms
            error_type = "rate_limit" if "rate" in str(e_first).lower() else "connection"
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type=error_type,
            )
            self.record_metrics(metrics)
            return GenerateResult(
                text="", metrics=metrics,
            )

    async def generate_async(self, request: GenerateRequest) -> GenerateResult:
        """
        原生异步生成：使用 openai.AsyncOpenAI 客户端。
        支持流式响应（stream=True）和非流式。
        """
        import asyncio
        start_ms = time.time() * 1000

        try:
            import openai
            async_client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=self.max_retries,
                timeout=self.timeout_s,
            )
        except ImportError:
            # 降级：使用线程池包装同步 generate
            return await super().generate_async(request)

        messages = []
        if request.messages:
            messages = request.messages.copy()
        else:
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await asyncio.wait_for(
                async_client.chat.completions.create(**kwargs),
                timeout=request.timeout_ms / 1000.0,
            )
            text = self._extract_text_from_response(response)
            latency_ms = (time.time() * 1000) - start_ms

            usage = response.usage
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=latency_ms,
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                success=True,
                model_id=self.model,
            )
            self.record_metrics(metrics)

            structured = None
            if request.response_format == "json":
                structured = self._safe_json_parse(text)

            await async_client.close()
            return GenerateResult(
                text=text, metrics=metrics, raw_response=response,
                structured=structured,
            )

        except asyncio.TimeoutError:
            await async_client.close()
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type="timeout",
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

        except Exception as e:
            await async_client.close()
            latency_ms = (time.time() * 1000) - start_ms
            error_type = "rate_limit" if "rate" in str(e).lower() else "connection"
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type=error_type,
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

    def health_check(self) -> bool:
        """快速探测：发送最小请求。"""
        try:
            req = GenerateRequest(
                prompt="hi", max_tokens=1, timeout_ms=5000,
            )
            res = self.generate(req)
            return res.metrics.success
        except Exception:
            return False

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """
        基于经验公式预估延迟。
        云端 API：首 token 延迟 ~200ms + 每 token ~20ms。
        """
        return 200 + (prompt_tokens + output_tokens) * 20
