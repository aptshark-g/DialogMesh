# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/mock_provider.py
────────────────────────────────────────────
DialogMesh v3.0 Mock / Stub Provider。

用途：
- 单元测试：无需真实 LLM，返回固定内容
- 开发调试：模拟特定场景（超时、错误、JSON 输出、流式）
- 性能基准：排除 LLM 延迟，只测编排逻辑
- 支持流式模拟（逐字输出固定文本）

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
    ProviderHealth,
    StreamingChunk,
)

logger = logging.getLogger(__name__)


class MockProvider_v3(LLMProvider_v3):
    """
    v3.0 Mock Provider：按配置返回固定内容，不调用任何外部服务。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.response_text = config.metadata.get("response_text", "[MOCK RESPONSE]")
        self.response_json = config.metadata.get("response_json")
        self.simulate_error = config.metadata.get("simulate_error")
        self.latency_ms = config.metadata.get("latency_ms", 0)
        self.stream_delay_ms = config.metadata.get("stream_delay_ms", 50)
        self._health = config.metadata.get("health", True)

        # 设置能力
        self._capabilities = config.capabilities or ProviderCapabilities(
            supports_json_mode=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_multi_turn=True,
            max_context_tokens=128000,
            max_output_tokens=4096,
        )

        logger.info(f"MockProvider_v3 initialized: {self.name}, health={self._health}")

    async def _generate_async_impl(self, request: GenerateRequest_v3) -> GenerateResult_v3:
        """异步生成（模拟延迟，核心实现，重试由基类 ``generate_async`` 统一处理）。"""
        start_ms = time.time() * 1000

        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        if self.simulate_error:
            latency = (time.time() * 1000) - start_ms
            error_map = {
                "timeout": (ErrorCategory.TIMEOUT, "模拟超时"),
                "connection": (ErrorCategory.CONNECTION, "模拟连接错误"),
                "rate_limit": (ErrorCategory.RATE_LIMIT, "模拟速率限制"),
            }
            error_category, error_msg = error_map.get(self.simulate_error, (ErrorCategory.UNKNOWN, "模拟未知错误"))
            self.record_failure(latency, error_category)
            return GenerateResult_v3(
                text="",
                latency_ms=latency,
                success=False,
                error_type=self.simulate_error,
                error_category=error_category,
                provider_name=self.name,
                model_id="mock",
            )

        # 智能 Mock：根据 prompt 关键词返回合理的结构化响应
        prompt = request.prompt.lower()
        if self.response_json is not None:
            response = self.response_json
        else:
            # 默认：根据 prompt 内容推断响应类型
            if "intent" in prompt or "意图" in prompt:
                if "scan" in prompt or "memory" in prompt:
                    response = {
                        "intent_inference": {
                            "primary_intent": "SCAN_MEMORY",
                            "confidence": 0.8,
                            "implied_entities": [],
                            "ambiguity_assessment": "low"
                        },
                        "confidence": 0.8
                    }
                elif "read" in prompt:
                    response = {
                        "intent_inference": {
                            "primary_intent": "READ_MEMORY",
                            "confidence": 0.8,
                            "implied_entities": [],
                            "ambiguity_assessment": "low"
                        },
                        "confidence": 0.8
                    }
                elif "hack" in prompt or "health" in prompt:
                    response = {
                        "intent_inference": {
                            "primary_intent": "HACK_VALUE",
                            "confidence": 0.75,
                            "implied_entities": [],
                            "ambiguity_assessment": "low"
                        },
                        "confidence": 0.75
                    }
                else:
                    response = {
                        "intent_inference": {
                            "primary_intent": "UNKNOWN",
                            "confidence": 0.4,
                            "implied_entities": [],
                            "ambiguity_assessment": "high"
                        },
                        "confidence": 0.4
                    }
            elif "noise" in prompt or "pcr" in prompt or "认知" in prompt:
                response = {
                    "noise_analysis": {
                        "semantic_noise": 0.2,
                        "structural_noise": 0.3,
                        "referential_noise": 0.2
                    },
                    "expectation_inference": {
                        "primary": "tool",
                        "confidence": 0.8,
                        "reasoning": "rule-based heuristic"
                    },
                    "cognitive_snapshot": {
                        "metacognition": 0.6,
                        "divergence": 0.2,
                        "stability": 0.8
                    },
                    "confidence": 0.8
                }
            elif "plan" in prompt or "规划" in prompt:
                response = {
                    "plan": [{"step": 1, "action": "scan_memory", "params": {"value": 100}}],
                    "confidence": 0.8
                }
            elif "response" in prompt or "answer" in prompt or "回复" in prompt:
                response = {
                    "response": f"已处理你的请求：{request.prompt[:50]}...",
                    "confidence": 0.8,
                    "honesty_declared": False,
                    "cited_nodes": [],
                    "fallback_reason": ""
                }
            else:
                response = {"raw_text": self.response_text, "confidence": 0.5}

        text = json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else response

        latency = (time.time() * 1000) - start_ms
        self.record_success(latency, 0, 0, 0.0)

        structured = None
        if request.response_format in ("json", "json_schema"):
            structured = self._safe_json_parse(text)

        return GenerateResult_v3(
            text=text,
            latency_ms=latency,
            success=True,
            input_tokens=0,
            output_tokens=0,
            model_id="mock",
            provider_name=self.name,
            structured=structured,
            finish_reason="stop",
        )

    async def stream_generate(self, request: GenerateRequest_v3) -> AsyncIterator[StreamingChunk]:
        """模拟流式生成：逐字输出固定文本。"""
        text = self.response_text
        if self.simulate_error:
            yield StreamingChunk(
                index=0, text="", finish_reason=self.simulate_error,
                provider_name=self.name, model_id="mock",
            )
            return

        for i, char in enumerate(text):
            if self.stream_delay_ms > 0:
                await asyncio.sleep(self.stream_delay_ms / 1000.0)
            yield StreamingChunk(
                index=i, text=char, finish_reason=None,
                provider_name=self.name, model_id="mock",
            )

        yield StreamingChunk(
            index=len(text), text="", finish_reason="stop",
            provider_name=self.name, model_id="mock",
        )

    async def health_check_async(self) -> bool:
        """异步健康检查。"""
        await asyncio.sleep(0)  # 让出事件循环
        return self._health

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """预估延迟。"""
        return float(self.latency_ms)
