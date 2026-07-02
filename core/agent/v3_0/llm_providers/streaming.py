# -*- coding: utf-8 -*-
"""
core/agent/v3_0/llm_providers/streaming.py
──────────────────────────────────────────
DialogMesh v3.0 LLM Provider 流式响应支持。

用途：
- 提供统一流式响应生成器，适配 SSE（Server-Sent Events）与 WebSocket 推送。
- 实现流式文本聚合器（StreamingAggregator），将 StreamingChunk 序列合并为完整结果。
- 支持流式 JSON 解析（分块 JSON 的渐进式解析）。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Callable

from core.agent.v3_0.llm_providers.models import StreamingChunk, ErrorCategory
from core.agent.v3_0.llm_providers.base import GenerateRequest_v3, GenerateResult_v3

logger = logging.getLogger(__name__)


class StreamingAggregator:
    """
    流式响应聚合器。

    将 AsyncIterator[StreamingChunk] 聚合为完整的 GenerateResult_v3，
    同时支持实时回调（如 WebSocket 推送）。
    """

    def __init__(
        self,
        provider_name: str = "",
        model_id: Optional[str] = None,
        on_chunk: Optional[Callable[[StreamingChunk], None]] = None,
    ):
        self.provider_name = provider_name
        self.model_id = model_id
        self.on_chunk = on_chunk
        self._chunks: List[StreamingChunk] = []
        self._text_parts: List[str] = []
        self._start_time = time.time()

    async def consume(self, stream: AsyncIterator[StreamingChunk]) -> GenerateResult_v3:
        """消费流式生成器，返回聚合结果。"""
        try:
            index = 0
            async for chunk in stream:
                self._chunks.append(chunk)
                self._text_parts.append(chunk.text)
                if self.on_chunk:
                    try:
                        self.on_chunk(chunk)
                    except Exception as cb_exc:
                        logger.warning(f"StreamingAggregator on_chunk callback error: {cb_exc}")
                if chunk.is_finished():
                    break
                index += 1

            full_text = "".join(self._text_parts)
            latency_ms = (time.time() - self._start_time) * 1000

            # 从最后一个 chunk 提取 usage 与 finish_reason
            last_chunk = self._chunks[-1] if self._chunks else None
            usage: Optional[Dict[str, int]] = last_chunk.usage if last_chunk else None
            finish_reason = last_chunk.finish_reason if last_chunk else None

            # 尝试解析 JSON
            structured = None
            if full_text.strip():
                try:
                    structured = json.loads(full_text)
                except json.JSONDecodeError:
                    pass

            return GenerateResult_v3(
                text=full_text,
                latency_ms=latency_ms,
                input_tokens=usage.get("prompt_tokens", 0) if usage else 0,
                output_tokens=usage.get("completion_tokens", 0) if usage else 0,
                success=True,
                model_id=self.model_id,
                provider_name=self.provider_name,
                structured=structured,
                finish_reason=finish_reason,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - self._start_time) * 1000
            logger.error(f"StreamingAggregator timeout for {self.provider_name}")
            return GenerateResult_v3(
                text="".join(self._text_parts),
                latency_ms=latency_ms,
                success=False,
                error_type="timeout",
                error_category=ErrorCategory.TIMEOUT,
                provider_name=self.provider_name,
                model_id=self.model_id,
            )

        except Exception as exc:
            latency_ms = (time.time() - self._start_time) * 1000
            logger.error(f"StreamingAggregator error for {self.provider_name}: {exc}")
            return GenerateResult_v3(
                text="".join(self._text_parts),
                latency_ms=latency_ms,
                success=False,
                error_type="streaming_error",
                error_category=ErrorCategory.UNKNOWN,
                provider_name=self.provider_name,
                model_id=self.model_id,
            )

    def get_chunks(self) -> List[StreamingChunk]:
        """获取已接收的所有 chunk。"""
        return self._chunks.copy()

    def get_partial_text(self) -> str:
        """获取当前已接收的部分文本。"""
        return "".join(self._text_parts)


class SSEFormatter:
    """
    SSE（Server-Sent Events）格式化器。

    将 StreamingChunk 序列格式化为 SSE 规范的字符串流。
    """

    @staticmethod
    def format_chunk(chunk: StreamingChunk) -> str:
        """将单个 chunk 格式化为 SSE 消息。"""
        data = json.dumps({
            "index": chunk.index,
            "text": chunk.text,
            "finish_reason": chunk.finish_reason,
            "provider_name": chunk.provider_name,
            "model_id": chunk.model_id,
            "usage": chunk.usage,
        }, ensure_ascii=False)
        return f"data: {data}\n\n"

    @staticmethod
    def format_done() -> str:
        """生成 SSE 结束标记。"""
        return "data: [DONE]\n\n"

    @staticmethod
    async def as_async_generator(
        stream: AsyncIterator[StreamingChunk],
    ) -> AsyncIterator[str]:
        """将 StreamingChunk 流转换为 SSE 字符串流。"""
        async for chunk in stream:
            yield SSEFormatter.format_chunk(chunk)
        yield SSEFormatter.format_done()


class WebSocketFormatter:
    """
    WebSocket 格式化器。

    将 StreamingChunk 序列格式化为 WebSocket JSON 消息。
    """

    @staticmethod
    def format_chunk(chunk: StreamingChunk, event_type: str = "stream_chunk") -> str:
        """将单个 chunk 格式化为 WebSocket JSON 字符串。"""
        return json.dumps({
            "type": event_type,
            "payload": chunk.model_dump(exclude_none=True),
            "timestamp": time.time(),
        }, ensure_ascii=False)

    @staticmethod
    def format_done(event_type: str = "stream_done") -> str:
        """生成 WebSocket 结束标记。"""
        return json.dumps({
            "type": event_type,
            "payload": {},
            "timestamp": time.time(),
        }, ensure_ascii=False)

    @staticmethod
    async def as_async_generator(
        stream: AsyncIterator[StreamingChunk],
        event_type: str = "stream_chunk",
    ) -> AsyncIterator[str]:
        """将 StreamingChunk 流转换为 WebSocket JSON 字符串流。"""
        async for chunk in stream:
            yield WebSocketFormatter.format_chunk(chunk, event_type)
        yield WebSocketFormatter.format_done(event_type)


class ProgressiveJSONParser:
    """
    渐进式 JSON 解析器。

    在流式输出中逐步尝试解析 JSON，适用于模型逐字输出 JSON 的场景。
    """

    def __init__(self):
        self._buffer = ""
        self._last_valid: Optional[Dict[str, Any]] = None

    def feed(self, text: str) -> Optional[Dict[str, Any]]:
        """接收新文本，尝试解析 JSON，返回当前可解析的最佳结果。"""
        self._buffer += text
        buf = self._buffer.strip()
        if not buf:
            return self._last_valid

        # 尝试直接解析
        try:
            parsed = json.loads(buf)
            if isinstance(parsed, dict):
                self._last_valid = parsed
                return parsed
        except json.JSONDecodeError:
            pass

        # 尝试提取最外层 { ... }
        import re
        match = re.search(r'(\{.*\})', buf, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    self._last_valid = parsed
                    return parsed
            except json.JSONDecodeError:
                pass

        return self._last_valid

    def reset(self) -> None:
        """重置解析器状态。"""
        self._buffer = ""
        self._last_valid = None

    def get_partial(self) -> str:
        """获取当前缓冲区内容。"""
        return self._buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _mock_stream() -> AsyncIterator[StreamingChunk]:
        """模拟流式生成器。"""
        for i, text in enumerate(["Hel", "lo", ", ", "wo", "rld", "!"]):
            yield StreamingChunk(index=i, text=text, provider_name="mock")
        yield StreamingChunk(index=6, text="", finish_reason="stop", provider_name="mock")

    async def _self_test() -> None:
        logger.info("=== v3.0 streaming self-test ===")

        # 1. StreamingAggregator
        aggregator = StreamingAggregator(provider_name="mock", model_id="test-model")
        result = await aggregator.consume(_mock_stream())
        assert result.text == "Hello, world!", f"Expected 'Hello, world!', got {result.text}"
        assert result.success is True
        print(f"[PASS] StreamingAggregator: text={result.text}")

        # 2. SSEFormatter
        chunks = [StreamingChunk(index=0, text="hi", provider_name="mock")]
        sse = SSEFormatter.format_chunk(chunks[0])
        assert sse.startswith("data: ")
        print(f"[PASS] SSEFormatter")

        # 3. WebSocketFormatter
        ws = WebSocketFormatter.format_chunk(chunks[0])
        assert "stream_chunk" in ws
        print(f"[PASS] WebSocketFormatter")

        # 4. ProgressiveJSONParser
        parser = ProgressiveJSONParser()
        assert parser.feed('{"a": 1') is None
        assert parser.feed(', "b": 2}') == {"a": 1, "b": 2}
        print(f"[PASS] ProgressiveJSONParser")

        logger.info("=== All v3.0 streaming self-tests passed ===")

    asyncio.run(_self_test())
