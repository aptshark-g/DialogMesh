# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/mock_provider.py
──────────────────────────────────────────
Mock / Stub Provider（v2.4 新增）。

用于：
  - 单元测试：无需真实 LLM，返回固定内容
  - 开发调试：模拟特定场景（超时、错误、JSON 输出）
  - 性能基准：排除 LLM 延迟，只测编排逻辑

配置项：
  - response_text: 固定返回文本
  - response_json: 固定返回 JSON（自动包装为 text）
  - simulate_error: None | "timeout" | "connection" | "rate_limit"
  - latency_ms: 模拟延迟（默认 0）
"""

from __future__ import annotations

import time
import json
from typing import Any, Dict, Optional

from core.agent.llm_providers.base import (
    LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics,
)


class MockProvider(LLMProvider):
    """
    Mock Provider：按配置返回固定内容，不调用任何外部服务。
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.response_text = config.get("response_text", "[MOCK RESPONSE]")
        self.response_json = config.get("response_json")
        self.simulate_error = config.get("simulate_error")
        self.latency_ms = config.get("latency_ms", 0)
        self._health = config.get("health", True)

    def generate(self, request: GenerateRequest) -> GenerateResult:
        start_ms = time.time() * 1000

        # 模拟延迟
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        # 模拟错误
        if self.simulate_error:
            latency = (time.time() * 1000) - start_ms
            metrics = LLMCallMetrics(
                provider_name=self.name, latency_ms=latency,
                success=False, error_type=self.simulate_error,
            )
            self.record_metrics(metrics)
            return GenerateResult(text="", metrics=metrics)

        # 构建响应文本
        text = self.response_text
        if self.response_json is not None:
            text = json.dumps(self.response_json)

        latency = (time.time() * 1000) - start_ms
        metrics = LLMCallMetrics(
            provider_name=self.name, latency_ms=latency,
            success=True, input_tokens=0, output_tokens=0,
            model_id="mock",
        )
        self.record_metrics(metrics)

        structured = None
        if request.response_format == "json":
            structured = self._safe_json_parse(text)

        return GenerateResult(
            text=text, metrics=metrics, structured=structured,
        )

    def health_check(self) -> bool:
        return self._health

    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        return float(self.latency_ms)
