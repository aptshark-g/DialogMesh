# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/local_provider.py
──────────────────────────────────────────
本地模型 Provider（v2.4 新增）。

支持部署方式：
  - vLLM：高并发服务端（推荐生产）
  - llama.cpp：轻量 CPU/GPU 推理（推荐边缘设备）
  - transformers：HuggingFace 直接加载（开发调试）
  - ollama：本地模型管理（最简部署）

配置项：
  - backend: "vllm" | "llamacpp" | "transformers" | "ollama"
  - model_path: 模型路径或 ID
  - device: "cuda" | "cpu" | "auto"
  - max_tokens: 最大生成长度
  - quantization: "int8" | "int4" | "none"（仅 transformers）
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.agent.llm_providers.base import (
    LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics,
)


class LocalProvider(LLMProvider):
    """
    本地模型 Provider。
    后端可切换：vLLM / llama.cpp / transformers / ollama。
    """

    def health_check(self) -> bool:
        """默认健康检查：基类返回 False（未连接后端时）。子类覆盖。"""
        return False

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.backend = config.get("backend", "ollama")
        self.model_path = config.get("model_path", "qwen2.5-1.5b-instruct")
        self.device = config.get("device", "auto")
        self.max_tokens_default = config.get("max_tokens", 512)
        self.quantization = config.get("quantization", "none")
        self._backend_instance = None
        self._model_id_for_estimation = self.model_path

    def _load_backend(self):
        """延迟加载后端。"""
        if self._backend_instance is not None:
            return self._backend_instance

        if self.backend == "vllm":
            self._backend_instance = _VLLMBackend(self.model_path, self.device)
        elif self.backend == "llamacpp":
            self._backend_instance = _LlamaCppBackend(self.model_path, self.device)
        elif self.backend == "transformers":
            self._backend_instance = _TransformersBackend(
                self.model_path, self.device, self.quantization
            )
        elif self.backend == "ollama":
            self._backend_instance = _OllamaBackend(self.model_path)
        else:
            raise ValueError(f"Unknown local backend: {self.backend}")

        return self._backend_instance

    def generate(self, request: GenerateRequest) -> GenerateResult:
        start_ms = time.time() * 1000

        try:
            backend = self._load_backend()
            text = backend.generate(
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                timeout_ms=request.timeout_ms,
            )
            latency_ms = (time.time() * 1000) - start_ms

            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=latency_ms,
                success=True,
                model_id=self.model_path,
            )
            self.record_metrics(metrics)

            structured = None
            if request.response_format == "json":
                structured = self._safe_json_parse(text)

            return GenerateResult(
                text=text, metrics=metrics, structured=structured,
            )

        except TimeoutError:
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type="timeout",
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

        except Exception as e:
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type="connection",
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

    async def generate_async(self, request: GenerateRequest) -> GenerateResult:
        """
        原生异步生成。
        - ollama 后端：使用 aiohttp 异步 HTTP + 流式
        - 其他后端：降级到线程池（默认实现）
        """
        import asyncio
        start_ms = time.time() * 1000

        if self.backend == "ollama":
            return await self._generate_async_ollama(request, start_ms)
        # 其他后端（vllm/llamacpp/transformers）降级到线程池
        return await super().generate_async(request)

    async def _generate_async_ollama(self, request: GenerateRequest, start_ms: float) -> GenerateResult:
        """Ollama 异步流式生成。"""
        import asyncio
        try:
            import aiohttp
        except ImportError:
            # aiohttp 未安装，降级到线程池
            return await super().generate_async(request)

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": self.model_path,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        chunks: List[str] = []
        try:
            timeout = aiohttp.ClientTimeout(total=request.timeout_ms / 1000.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "http://localhost:11434/api/chat",
                    json=payload,
                ) as resp:
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
                        if "message" in data and "content" in data["message"]:
                            chunks.append(data["message"]["content"])
                        if data.get("done", False):
                            break

            text = "".join(chunks)
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name,
                latency_ms=latency_ms,
                success=True,
                model_id=self.model_path,
            )
            self.record_metrics(metrics)

            structured = None
            if request.response_format == "json":
                structured = self._safe_json_parse(text)

            return GenerateResult(text=text, metrics=metrics, structured=structured)

        except asyncio.TimeoutError:
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type="timeout",
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

        except Exception as e:
            latency_ms = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency_ms,
                success=False, error_type="connection",
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """
        本地模型延迟预估（基于后端类型和模型大小）。
        1.5B Qwen CPU: ~50ms + 15ms/token
        7B GPU: ~30ms + 8ms/token
        vLLM: ~20ms + 5ms/token
        """
        backend_factors = {
            "vllm": (20, 5),
            "llamacpp": (40, 10),
            "transformers": (80, 20),
            "ollama": (50, 12),
        }
        base, per_token = backend_factors.get(self.backend, (50, 15))
        # 模型大小修正：路径含 "1.5b" 或 "3b" 则更快
        path_lower = self.model_path.lower()
        if any(x in path_lower for x in ["1.5b", "3b", "1.8b"]):
            base -= 15
            per_token -= 5
        return base + (prompt_tokens + output_tokens) * per_token


# ── 后端适配器（占位实现，按需扩展）──────────────────────────

class _VLLMBackend:
    """vLLM 服务端适配器。"""
    def __init__(self, model: str, device: str):
        self.model = model
        self.device = device

    def generate(self, prompt: str, system_prompt: Optional[str], max_tokens: int,
                 temperature: float, timeout_ms: int) -> str:
        # 实际实现：调用 vLLM 的 OpenAI 兼容 API 或 LLM 引擎
        # 这里提供占位，生产环境接入 vllm.LLMEngine
        raise NotImplementedError("vLLM backend requires vllm library")

    def health_check(self) -> bool:
        return True


class _LlamaCppBackend:
    """llama.cpp 适配器。"""
    def __init__(self, model: str, device: str):
        self.model = model
        self.device = device

    def generate(self, prompt: str, system_prompt: Optional[str], max_tokens: int,
                 temperature: float, timeout_ms: int) -> str:
        # 实际实现：调用 llama_cpp.Llama
        raise NotImplementedError("llama.cpp backend requires llama-cpp-python")

    def health_check(self) -> bool:
        return True


class _TransformersBackend:
    """HuggingFace transformers 适配器。"""
    def __init__(self, model: str, device: str, quantization: str):
        self.model = model
        self.device = device
        self.quantization = quantization
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            from transformers import pipeline
            self._pipeline = pipeline(
                "text-generation", model=self.model, device=self.device,
                torch_dtype="auto",
            )
        return self._pipeline

    def generate(self, prompt: str, system_prompt: Optional[str], max_tokens: int,
                 temperature: float, timeout_ms: int) -> str:
        # 占位：实际调用 transformers pipeline
        raise NotImplementedError("transformers backend requires transformers library")

    def health_check(self) -> bool:
        return True


class _OllamaBackend:
    """Ollama 本地模型适配器。"""
    def __init__(self, model: str):
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str], max_tokens: int,
                 temperature: float, timeout_ms: int) -> str:
        import requests
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout_ms / 1000.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    def health_check(self) -> bool:
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False
