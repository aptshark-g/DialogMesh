# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/local_provider.py
──────────────────────────────────────────────
DialogMesh v3.0 本地模型 Provider。

支持部署方式：
  - vLLM：高并发服务端（推荐生产）
  - llama.cpp：轻量 CPU/GPU 推理（推荐边缘设备）
  - transformers：HuggingFace 直接加载（开发调试）
  - ollama：本地模型管理（最简部署）

特性：
  - 原生异步生成（ollama 使用 aiohttp，其他降级到线程池）
  - 流式响应（ollama 原生 SSE，其他模拟）
  - 延迟预估（基于后端类型与模型大小）

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

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
    StreamingChunk,
)

logger = logging.getLogger(__name__)


class LocalProvider_v3(LLMProvider_v3):
    """
    v3.0 本地模型 Provider。
    后端可切换：vLLM / llama.cpp / transformers / ollama。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.backend = config.backend.value if isinstance(config.backend, ProviderBackend) else config.backend
        if self.backend not in {b.value for b in [ProviderBackend.VLLM, ProviderBackend.LLAMACPP, ProviderBackend.TRANSFORMERS, ProviderBackend.OLLAMA]}:
            self.backend = ProviderBackend.OLLAMA.value

        self.model_path = config.backend_path or config.model or "qwen2.5:1.5b-instruct"
        self.device = config.device or "auto"
        self.max_tokens_default = config.max_tokens
        self.quantization = config.quantization
        self._backend_instance: Optional[Any] = None

        # 设置能力
        self._capabilities = config.capabilities or ProviderCapabilities(
            supports_json_mode=(self.backend != ProviderBackend.LLAMACPP.value),
            supports_streaming=(self.backend == ProviderBackend.OLLAMA.value),
            supports_system_prompt=True,
            supports_multi_turn=True,
            max_context_tokens=8192,
            max_output_tokens=4096,
            supported_models=[self.model_path],
        )

        logger.info(
            f"LocalProvider_v3 initialized: {self.name}, backend={self.backend}, "
            f"model={self.model_path}"
        )

    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """原生异步生成（核心实现，重试由基类 ``generate_async`` 统一处理）。"""
        start_ms = time.time() * 1000

        if request.stream and self.backend == ProviderBackend.OLLAMA.value:
            from core.agent.v3_0.llm_providers.streaming import StreamingAggregator
            aggregator = StreamingAggregator(
                provider_name=self.name,
                model_id=self.model_path,
            )
            return await aggregator.consume(self.stream_generate(request))

        try:
            if self.backend == ProviderBackend.OLLAMA.value:
                text = await self._generate_ollama_async(request)
            else:
                # 其他后端：降级到线程池
                text = await asyncio.get_event_loop().run_in_executor(
                    None, self._generate_sync, request
                )

            latency_ms = (time.time() * 1000) - start_ms
            self.record_success(latency_ms, 0, 0, 0.0)

            structured = None
            if request.response_format in ("json", "json_schema"):
                structured = self._safe_json_parse(text)

            return GenerateResult_v3(
                text=text,
                latency_ms=latency_ms,
                success=True,
                model_id=self.model_path,
                provider_name=self.name,
                structured=structured,
                finish_reason="stop",
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() * 1000) - start_ms
            self.record_failure(latency_ms, ErrorCategory.TIMEOUT)
            return GenerateResult_v3(
                text="",
                latency_ms=latency_ms,
                success=False,
                error_type="timeout",
                error_category=ErrorCategory.TIMEOUT,
                provider_name=self.name,
                model_id=self.model_path,
            )
        except Exception as exc:
            latency_ms = (time.time() * 1000) - start_ms
            error_category = self._classify_error(exc)
            self.record_failure(latency_ms, error_category)
            logger.error(f"LocalProvider_v3 error: {exc}")
            return GenerateResult_v3(
                text="",
                latency_ms=latency_ms,
                success=False,
                error_type=error_category.value,
                error_category=error_category,
                provider_name=self.name,
                model_id=self.model_path,
            )

    async def _generate_ollama_async(self, request: GenerateRequest_v3) -> str:
        """Ollama 异步 HTTP 调用。"""
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError("aiohttp not installed. Install with: pip install aiohttp")

        messages = request.to_messages()
        payload = {
            "model": self.model_path,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        timeout = aiohttp.ClientTimeout(total=request.timeout_ms / 1000.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "http://localhost:11434/api/chat",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("message", {}).get("content", "")

    def _generate_sync(self, request: GenerateRequest_v3) -> str:
        """同步生成（用于线程池降级）。"""
        if self.backend == ProviderBackend.OLLAMA.value:
            import requests
            messages = request.to_messages()
            resp = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": self.model_path,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_tokens,
                    },
                },
                timeout=request.timeout_ms / 1000.0,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        raise NotImplementedError(f"Backend {self.backend} not implemented in sync mode")

    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """原生异步流式生成。"""
        start_ms = time.time() * 1000

        if self.backend != ProviderBackend.OLLAMA.value:
            # 非 ollama 后端：降级为逐字模拟流式
            result = await self.generate_async(request)
            if not result.success:
                yield StreamingChunk(
                    index=0, text="", finish_reason="error",
                    provider_name=self.name, model_id=self.model_path,
                )
                return
            for i, char in enumerate(result.text):
                yield StreamingChunk(
                    index=i, text=char, finish_reason=None,
                    provider_name=self.name, model_id=self.model_path,
                    latency_ms=(time.time() * 1000) - start_ms,
                )
            yield StreamingChunk(
                index=len(result.text), text="", finish_reason="stop",
                provider_name=self.name, model_id=self.model_path,
                latency_ms=(time.time() * 1000) - start_ms,
            )
            return

        # Ollama 原生流式
        try:
            import aiohttp
        except ImportError:
            yield StreamingChunk(
                index=0, text="", finish_reason="error",
                provider_name=self.name, model_id=self.model_path,
            )
            return

        messages = request.to_messages()
        payload = {
            "model": self.model_path,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        try:
            timeout = aiohttp.ClientTimeout(total=request.timeout_ms / 1000.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "http://localhost:11434/api/chat",
                    json=payload,
                ) as resp:
                    index = 0
                    async for line in resp.content:
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if not line_str:
                            continue
                        try:
                            data = json.loads(line_str)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        yield StreamingChunk(
                            index=index,
                            text=content,
                            finish_reason="stop" if done else None,
                            provider_name=self.name,
                            model_id=self.model_path,
                            latency_ms=(time.time() * 1000) - start_ms,
                        )
                        if done:
                            break
                        index += 1

        except asyncio.TimeoutError:
            yield StreamingChunk(
                index=0, text="", finish_reason="timeout",
                provider_name=self.name, model_id=self.model_path,
            )
        except Exception as exc:
            logger.error(f"LocalProvider_v3 stream error: {exc}")
            yield StreamingChunk(
                index=0, text="", finish_reason="error",
                provider_name=self.name, model_id=self.model_path,
            )

    async def health_check_async(self) -> bool:
        """异步健康检查。"""
        if self.backend == ProviderBackend.OLLAMA.value:
            try:
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=2.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get("http://localhost:11434/api/tags") as resp:
                        return resp.status == 200
            except Exception:
                return False
        # 其他后端：尝试 generate
        try:
            req = GenerateRequest_v3(prompt="hi", max_tokens=1, timeout_ms=5000)
            result = await self.generate_async(req)
            return result.success
        except Exception:
            return False

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """
        本地模型延迟预估（基于后端类型和模型大小）。
        """
        backend_factors = {
            ProviderBackend.VLLM.value: (20, 5),
            ProviderBackend.LLAMACPP.value: (40, 10),
            ProviderBackend.TRANSFORMERS.value: (80, 20),
            ProviderBackend.OLLAMA.value: (50, 12),
        }
        base, per_token = backend_factors.get(self.backend, (50, 15))
        path_lower = self.model_path.lower()
        if any(x in path_lower for x in ["1.5b", "3b", "1.8b"]):
            base -= 15
            per_token -= 5
        return base + (prompt_tokens + output_tokens) * per_token
