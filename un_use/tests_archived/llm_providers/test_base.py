# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/tests/test_base.py
──────────────────────────────────────────────
v3.0 LLM Provider 单元测试。

覆盖：
  - models.py 数据模型
  - base.py 基类与请求/响应
  - streaming.py 流式聚合
  - circuit_breaker.py 熔断器
  - mock_provider.py Mock Provider

运行方式：
  python -m pytest core/agent/v3_0/llm_providers/tests/test_base.py -v
  或 python core/agent/v3_0/llm_providers/tests/test_base.py

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录加入路径
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from core.agent.llm_providers.models import (
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
    BatchGenerateRequest,
    BatchGenerateResult,
)
from core.agent.llm_providers.base import (
    GenerateRequest_v3,
    GenerateResult_v3,
    LLMProvider_v3,
)

# 解析 BatchGenerateResult 的前向引用（Pydantic v2 需要显式 rebuild）
BatchGenerateResult.model_rebuild()
from core.agent.llm_providers.streaming import (
    ProgressiveJSONParser,
    SSEFormatter,
    StreamingAggregator,
    WebSocketFormatter,
)
from core.agent.llm_providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
)
from core.agent.llm_providers.mock_provider import MockProvider_v3


# ═══════════════════════════════════════════════════════════════════════════════
# models.py 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenPricing:
    def test_estimate_cost(self):
        pricing = TokenPricing(input_price_per_1k=0.1, output_price_per_1k=0.3)
        assert pricing.estimate_cost(1000, 500) == 0.25


class TestProviderConfig:
    def test_temperature_clamping(self):
        cfg = ProviderConfig(name="test", temperature=3.0)
        assert cfg.temperature == 2.0

    def test_defaults(self):
        cfg = ProviderConfig(name="test")
        assert cfg.backend == ProviderBackend.OPENAI
        assert cfg.max_tokens == 512
        assert cfg.timeout_seconds == 30.0


class TestStreamingChunk:
    def test_is_finished(self):
        chunk = StreamingChunk(index=0, text="hi")
        assert not chunk.is_finished()
        chunk2 = StreamingChunk(index=1, text="", finish_reason="stop")
        assert chunk2.is_finished()


class TestCallStatistics:
    def test_record_success(self):
        stats = CallStatistics()
        stats.record_success(100.0, 10, 20, 0.01)
        assert stats.total_calls == 1
        assert stats.success_rate == 1.0
        assert stats.avg_latency_ms == 100.0

    def test_record_failure(self):
        stats = CallStatistics()
        stats.record_failure(200.0, ErrorCategory.TIMEOUT)
        assert stats.total_calls == 1
        assert stats.success_rate == 0.0
        assert stats.last_error == "timeout"


class TestProviderResult:
    def test_ok(self):
        r = ProviderResult[str].ok(data="hello")
        assert r.success is True
        assert r.data == "hello"

    def test_fail(self):
        r = ProviderResult[str].fail(error="boom", error_category=ErrorCategory.CONNECTION)
        assert r.success is False
        assert r.error == "boom"


class TestBatchGenerateResult:
    def test_is_all_success(self):
        result = BatchGenerateResult()
        assert not result.is_all_success()

    def test_get_best_result(self):
        result = BatchGenerateResult()
        assert result.get_best_result() is None


# ═══════════════════════════════════════════════════════════════════════════════
# base.py 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateRequest_v3:
    def test_to_messages_with_prompt(self):
        req = GenerateRequest_v3(prompt="hello", system_prompt="sys")
        msgs = req.to_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "hello"

    def test_to_messages_with_messages(self):
        req = GenerateRequest_v3(messages=[{"role": "user", "content": "hi"}])
        msgs = req.to_messages()
        assert msgs[0]["content"] == "hi"


class TestGenerateResult_v3:
    def test_to_dict(self):
        res = GenerateResult_v3(text="ok", latency_ms=100.0)
        d = res.to_dict()
        assert d["text"] == "ok"
        assert d["latency_ms"] == 100.0


class TestLLMProvider_v3:
    def test_classify_error(self):
        class DummyProvider(LLMProvider_v3):
            async def _generate_async_impl(self, request):
                pass
            async def health_check_async(self):
                return True
            def estimate_latency_ms(self, p, o):
                return 0.0
            async def stream_generate(self, request):
                yield StreamingChunk()

        provider = DummyProvider(ProviderConfig(name="dummy"))
        assert provider._classify_error(asyncio.TimeoutError()) == ErrorCategory.TIMEOUT
        assert provider._classify_error(Exception("rate limit")) == ErrorCategory.RATE_LIMIT
        assert provider._classify_error(Exception("connection refused")) == ErrorCategory.CONNECTION


# ═══════════════════════════════════════════════════════════════════════════════
# streaming.py 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStreamingAggregator:
    @pytest.mark.asyncio
    async def test_consume(self):
        async def _stream():
            for i, text in enumerate(["Hel", "lo"]):
                yield StreamingChunk(index=i, text=text, provider_name="mock")
            yield StreamingChunk(index=2, text="", finish_reason="stop", provider_name="mock")

        agg = StreamingAggregator(provider_name="mock", model_id="test")
        result = await agg.consume(_stream())
        assert result.text == "Hello"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_partial_text(self):
        async def _stream():
            yield StreamingChunk(index=0, text="pa", provider_name="mock")
            yield StreamingChunk(index=1, text="rt", provider_name="mock")

        agg = StreamingAggregator()
        # 手动消费但不等待完成
        async for chunk in _stream():
            agg._chunks.append(chunk)
            agg._text_parts.append(chunk.text)
        assert agg.get_partial_text() == "part"


class TestSSEFormatter:
    def test_format_chunk(self):
        chunk = StreamingChunk(index=0, text="hi", provider_name="mock")
        sse = SSEFormatter.format_chunk(chunk)
        assert sse.startswith("data: ")
        assert "hi" in sse

    def test_format_done(self):
        assert SSEFormatter.format_done() == "data: [DONE]\n\n"


class TestProgressiveJSONParser:
    def test_feed(self):
        parser = ProgressiveJSONParser()
        assert parser.feed('{"a": 1') is None
        result = parser.feed(', "b": 2}')
        assert result == {"a": 1, "b": 2}

    def test_reset(self):
        parser = ProgressiveJSONParser()
        parser.feed('{"a": 1}')
        parser.reset()
        assert parser.get_partial() == ""


# ═══════════════════════════════════════════════════════════════════════════════
# circuit_breaker.py 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        cb = CircuitBreaker("test")
        assert cb.is_closed()
        assert await cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_open_after_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_rate_threshold=0.5,
            min_calls_to_evaluate=5,
            wait_duration_open_ms=100.0,
        ))
        for _ in range(5):
            await cb.record_failure(10.0, ErrorCategory.TIMEOUT)
        assert cb.is_open()
        assert await cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_rate_threshold=0.5,
            min_calls_to_evaluate=5,
            wait_duration_open_ms=100.0,
        ))
        for _ in range(5):
            await cb.record_failure(10.0, ErrorCategory.TIMEOUT)
        await asyncio.sleep(0.15)
        assert await cb.allow_request() is True  # HALF_OPEN
        await cb.record_success(10.0)
        assert cb.is_closed()

    @pytest.mark.asyncio
    async def test_reset(self):
        cb = CircuitBreaker("test")
        for _ in range(5):
            await cb.record_failure(10.0, ErrorCategory.TIMEOUT)
        await cb.reset()
        assert cb.is_closed()


class TestCircuitBreakerRegistry:
    def test_register_and_get(self):
        reg = CircuitBreakerRegistry()
        reg.register("p1")
        assert reg.get("p1") is not None
        assert reg.get("p2") is None

    def test_get_all_states(self):
        reg = CircuitBreakerRegistry()
        reg.register("p1")
        reg.register("p2")
        states = reg.get_all_states()
        assert len(states) == 2

    @pytest.mark.asyncio
    async def test_reset_all(self):
        reg = CircuitBreakerRegistry()
        reg.register("p1", CircuitBreakerConfig(
            failure_rate_threshold=0.5,
            min_calls_to_evaluate=5,
            wait_duration_open_ms=100.0,
        ))
        cb = reg.get("p1")
        for _ in range(5):
            await cb.record_failure(10.0, ErrorCategory.TIMEOUT)
        assert cb.is_open()  # 确保已触发 OPEN
        await reg.reset_all()
        assert cb.is_closed()


# ═══════════════════════════════════════════════════════════════════════════════
# mock_provider.py 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockProvider_v3:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        config = ProviderConfig(
            name="mock",
            backend=ProviderBackend.MOCK,
            metadata={"response_text": "hello world"},
        )
        provider = MockProvider_v3(config)
        req = GenerateRequest_v3(prompt="hi")
        result = await provider.generate_async(req)
        assert result.text == "hello world"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_error(self):
        config = ProviderConfig(
            name="mock",
            backend=ProviderBackend.MOCK,
            metadata={"simulate_error": "timeout"},
        )
        provider = MockProvider_v3(config)
        req = GenerateRequest_v3(prompt="hi")
        result = await provider.generate_async(req)
        assert result.success is False
        assert result.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_stream_generate(self):
        config = ProviderConfig(
            name="mock",
            backend=ProviderBackend.MOCK,
            metadata={"response_text": "abc"},
        )
        provider = MockProvider_v3(config)
        req = GenerateRequest_v3(prompt="hi")
        chunks = []
        async for chunk in provider.stream_generate(req):
            chunks.append(chunk)
        assert len(chunks) == 4  # a, b, c, stop
        assert chunks[-1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_health_check(self):
        config = ProviderConfig(name="mock", backend=ProviderBackend.MOCK)
        provider = MockProvider_v3(config)
        assert await provider.health_check_async() is True


# ═══════════════════════════════════════════════════════════════════════════════
# 直接运行
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
