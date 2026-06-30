# -*- coding: utf-8 -*-
"""
core/agent/window/compressor.py
──────────────────────────────
History compression strategies.

设计要点：
  - 分层策略：Hot（保留完整）→ Warm（截断/合并）→ Cold（丢弃/摘要）
  - 可配置：通过 max_tokens / max_turns 控制各层
  - 压缩后保留时间戳顺序（旧 → 新）
  - 不依赖 LLM（本地规则压缩），可选外部摘要
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from core.agent.pcr.datacontract import HistoryEntry
from core.agent.window.token_counter import TokenCounter


class CompressionResult:
    """压缩结果。"""

    def __init__(
        self,
        entries: List[HistoryEntry],
        dropped: int = 0,
        merged: int = 0,
        summary_tokens: int = 0,
    ):
        self.entries = entries
        self.dropped = dropped
        self.merged = merged
        self.summary_tokens = summary_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kept": len(self.entries),
            "dropped": self.dropped,
            "merged": self.merged,
            "summary_tokens": self.summary_tokens,
        }


class Compressor(ABC):
    """压缩器抽象基类。"""

    @abstractmethod
    def compress(self, entries: List[HistoryEntry]) -> CompressionResult:
        ...


class PassThroughCompressor(Compressor):
    """透传：不压缩。"""

    def compress(self, entries: List[HistoryEntry]) -> CompressionResult:
        return CompressionResult(entries=list(entries))


class TruncationCompressor(Compressor):
    """
    截断压缩器：保留尾部 N 条，丢弃前面。
    适用于 Warm 区快速截断。
    """

    def __init__(self, max_turns: int = 10, max_tokens: Optional[int] = None):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._counter = TokenCounter()

    def compress(self, entries: List[HistoryEntry]) -> CompressionResult:
        if not entries:
            return CompressionResult(entries=[])

        # 先按尾部截断
        kept = entries[-self.max_turns :] if len(entries) > self.max_turns else list(entries)
        dropped = len(entries) - len(kept)

        # 如果仍超 token，从头部继续丢弃
        if self.max_tokens is not None:
            while kept and self._counter.estimate_entries(kept) > self.max_tokens and len(kept) > 1:
                kept.pop(0)
                dropped += 1

        return CompressionResult(entries=kept, dropped=dropped)


class HierarchicalCompressor(Compressor):
    """
    分层压缩器：三阶段压缩。

    Hot 区：保留最近 N 轮完整内容。
    Warm 区：中间 M 轮，截断或合并为短摘要。
    Cold 区：更老的轮次，完全丢弃或压缩为单条元摘要。

    默认配置（来自 agent_config.yaml）：
      hot_max=5, warm_max=15, cold_max=80
    """

    def __init__(
        self,
        hot_max_turns: int = 5,
        warm_max_turns: int = 15,
        cold_max_turns: int = 80,
        hot_max_tokens: Optional[int] = None,
        warm_max_tokens: Optional[int] = None,
        enable_cold_summary: bool = False,
        llm_compressor: Optional[Any] = None,
    ):
        self.hot_max_turns = hot_max_turns
        self.warm_max_turns = warm_max_turns
        self.cold_max_turns = cold_max_turns
        self.hot_max_tokens = hot_max_tokens
        self.warm_max_tokens = warm_max_tokens
        self.enable_cold_summary = enable_cold_summary
        self.llm_compressor = llm_compressor
        self._counter = TokenCounter()

    def compress(self, entries: List[HistoryEntry]) -> CompressionResult:
        if not entries:
            return CompressionResult(entries=[])

        n = len(entries)
        if n <= self.hot_max_turns and self.hot_max_tokens is None:
            # 全部在 Hot 区且无限 token，无需压缩
            return CompressionResult(entries=list(entries))

        # 1. Hot 区：尾部 hot_max_turns 保留完整
        hot_start = max(0, n - self.hot_max_turns)
        hot_entries = entries[hot_start:]

        # 如果 Hot 区超 token，从 Hot 区内部再截断（保留至少 1 条）
        if self.hot_max_tokens is not None:
            while (
                len(hot_entries) > 1
                and self._counter.estimate_entries(hot_entries) > self.hot_max_tokens
            ):
                hot_entries.pop(0)

        # 2. Warm 区：中间部分
        warm_end = hot_start
        warm_start = max(0, warm_end - self.warm_max_turns)
        warm_entries = entries[warm_start:warm_end]

        # Warm 区截断到 max_tokens
        if self.warm_max_tokens is not None and warm_entries:
            while (
                len(warm_entries) > 1
                and self._counter.estimate_entries(warm_entries) > self.warm_max_tokens
            ):
                warm_entries.pop(0)

        # 3. Cold 区：warm_start 之前的老数据
        cold_entries = entries[:warm_start]
        dropped = len(cold_entries)
        summary_tokens = 0

        result_entries = []

        if cold_entries and self.enable_cold_summary:
            # 生成一条 Cold 摘要条目（占位实现，不调用 LLM）
            summary = self._generate_cold_summary(cold_entries)
            result_entries.append(summary)
            summary_tokens = self._counter.estimate_entry(summary)
            dropped = 0  # 转为摘要，不算丢弃
            merged = len(cold_entries)
        else:
            merged = 0

        # 拼接：Cold 摘要 + Warm 截断 + Hot 完整
        result_entries.extend(warm_entries)
        result_entries.extend(hot_entries)

        return CompressionResult(
            entries=result_entries,
            dropped=dropped,
            merged=merged,
            summary_tokens=summary_tokens,
        )

    def _generate_cold_summary(self, entries: List[HistoryEntry]) -> HistoryEntry:
        """生成 Cold 区摘要。优先使用 LLMCompressor，失败回退到本地规则。"""
        # 如果配置了 LLMCompressor 且可用，尝试 LLM 摘要
        if self.llm_compressor is not None:
            try:
                summary = self.llm_compressor.compress(entries)
                if summary is not None:
                    return summary
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("LLM cold summary failed: %s", exc)

        # 本地规则回退
        expectations = [e.expectation for e in entries if e.expectation]
        roles = [e.role for e in entries]
        user_count = roles.count("user")
        assistant_count = roles.count("assistant")

        content = (
            f"[历史摘要] 共 {len(entries)} 轮对话，"
            f"用户 {user_count} 轮，助手 {assistant_count} 轮。"
        )
        if expectations:
            uniq = list(dict.fromkeys(expectations))[:5]
            content += f" 涉及意图：{', '.join(uniq)}。"

        return HistoryEntry(
            role="system",
            content=content,
            expectation="cold_summary",
            metadata={"compressed_turns": len(entries)},
        )
