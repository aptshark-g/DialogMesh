# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/base.py
───────────────────────────────────
LLM Provider 抽象基类与通用接口（v2.4 新增）。

设计原则：
  - 统一接口：所有 Provider 实现相同 generate() 签名
  - 延迟预算：调用方传入 max_latency_ms，Provider 自行超时/降级
  - 结构化输出：支持 JSON Schema 约束，防止 LLM 自由发散
  - 可观测：每次调用记录 latency、token_usage、error_type，供 Router 学习
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class LLMCallMetrics:
    """单次 LLM 调用遥测数据。"""
    provider_name: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error_type: Optional[str] = None  # "timeout" | "rate_limit" | "connection" | "validation"
    status_code: Optional[int] = None
    model_id: Optional[str] = None


@dataclass
class GenerateRequest:
    """标准化生成请求。"""
    prompt: str = ""                         # 如果 messages 为空，用这个构建单条消息
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None  # 标准 OpenAI Chat messages 格式（优先）
    max_tokens: int = 512
    temperature: float = 0.3          # 低温度，减少发散（任务型 LLM 不需要创意）
    timeout_ms: int = 30000           # 默认 30s 超时
    response_format: Optional[str] = None  # "json" | "text"（默认 text）
    json_schema: Optional[Dict] = None     # JSON Schema 约束（仅部分 provider 支持）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 调用方透传标记


@dataclass
class GenerateResult:
    """标准化生成结果。"""
    text: str
    metrics: LLMCallMetrics
    raw_response: Optional[Any] = None  # 原始响应（调试用，不暴露给业务层）
    structured: Optional[Dict] = None   # 如果 response_format="json" 且解析成功


class LLMProvider(ABC):
    """
    LLM Provider 抽象基类。

    所有具体实现必须提供：
      - generate(request) -> GenerateResult
      - health_check() -> bool（快速探测可用性）
      - estimate_latency_ms(prompt_len) -> float（预估延迟，用于路由决策）
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._metrics_history: List[LLMCallMetrics] = []
        self._max_history = 100

    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """执行生成。必须处理内部超时和异常，返回统一的 GenerateResult。"""
        raise NotImplementedError

    async def generate_async(self, request: GenerateRequest) -> GenerateResult:
        """Async wrapper for generate() using run_in_executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate, request)

    @abstractmethod
    def health_check(self) -> bool:
        """快速健康检查（< 100ms）。返回 True/False，不抛异常。"""
        raise NotImplementedError

    @abstractmethod
    def estimate_latency_ms(self, prompt_tokens: int, output_tokens: int) -> float:
        """基于 prompt 长度预估延迟（ms），用于 HybridRouter 预筛选。"""
        raise NotImplementedError

    def record_metrics(self, metrics: LLMCallMetrics) -> None:
        """记录调用指标，滑动窗口。"""
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self._max_history:
            self._metrics_history.pop(0)

    def get_recent_stats(self, window: int = 10) -> Dict[str, float]:
        """返回最近 N 次调用的统计：成功率、平均延迟、P95 延迟。"""
        recent = self._metrics_history[-window:]
        if not recent:
            return {"success_rate": 1.0, "avg_latency_ms": 0.0, "p95_latency_ms": 0.0}
        latencies = [m.latency_ms for m in recent]
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95) - 1
        p95_idx = max(0, p95_idx)
        success_rate = sum(1 for m in recent if m.success) / len(recent)
        return {
            "success_rate": success_rate,
            "avg_latency_ms": sum(latencies) / len(latencies),
            "p95_latency_ms": latencies[p95_idx],
        }

    def _wrap_with_timeout(self, fn, timeout_ms: int, *args, **kwargs):
        """内部辅助：带超时执行。子类可用，也可自行实现。"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout_ms / 1000.0)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"LLM call exceeded {timeout_ms}ms")

    def _safe_json_parse(self, text: str) -> Optional[Dict]:
        """安全解析 JSON，提取 Markdown 代码块中的 JSON。"""
        import json, re
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试提取最外层 { ... }
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None
