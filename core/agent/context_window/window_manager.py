# -*- coding: utf-8 -*-
"""
core/agent/context_window/window_manager.py
────────────────────────────────────────
Window manager: Hot/Warm/Cold 3-layer window architecture.

设计要点：
  - 热窗口：最近 5 轮，原始记录，全精度
  - 温窗口：第 6-20 轮，轻度压缩，保留意图标签
  - 冷窗口：第 21-100 轮，中度压缩，摘要记录
  - 归档：100 轮以上，不进入窗口（仅持久化）
  - 动态压缩：当总 tokens > 阈值时，从温窗口开始压缩
  - 零 LLM 依赖：所有压缩由 RuleBasedCompressor 完成
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.context_window.models import WindowTurn, CompressedSummary
from core.agent.context_window.compressor import RuleBasedCompressor, CompressionLevel
from core.agent.pcr.datacontract import HistoryEntry


@dataclass(frozen=False)
class WindowConfig:
    """窗口配置参数。"""
    hot_size: int = 5                # 热窗口保留轮数
    warm_size: int = 15              # 温窗口保留轮数 (6-20)
    cold_size: int = 80              # 冷窗口保留轮数 (21-100)
    max_hot_tokens: int = 800      # 热窗口最大 tokens
    max_warm_tokens: int = 1200    # 温窗口最大 tokens
    max_cold_tokens: int = 2000    # 冷窗口最大 tokens
    max_total_tokens: int = 4000   # 总窗口最大 tokens
    enable_compression: bool = True  # 是否启用压缩


class WindowManager:
    """
    三层窗口管理器。
    负责将历史轮次组织为 Hot/Warm/Cold 三层结构，
    并在 tokens 超限时触发压缩。
    """

    def __init__(self, config: Optional[WindowConfig] = None):
        self.config = config or WindowConfig()
        self.compressor = RuleBasedCompressor()

        # 三层窗口存储
        self.hot: List[WindowTurn] = []
        self.warm: List[WindowTurn] = []
        self.cold: List[WindowTurn] = []

        # 压缩统计
        self._compression_stats: Dict[str, Any] = {
            "total_compressed": 0,
            "total_turns": 0,
            "last_compression_time_ms": 0.0,
        }

    # ── 核心 API ───────────────────────────────────────────

    def add_turn(self, turn: WindowTurn) -> None:
        """添加一轮到窗口系统，并触发窗口滑动。"""
        # 新轮次进入热窗口
        self.hot.append(turn)
        self._compression_stats["total_turns"] += 1

        # 触发窗口滑动
        self._slide_windows()

        # 检查 tokens 超限并压缩
        self._enforce_token_limits()

    def build_pcr_input(self, current_query: str = "") -> List[HistoryEntry]:
        """
        构建 PCR 输入用的历史记录。
        顺序：冷窗口摘要 → 温窗口 → 热窗口 → 当前查询（不包含）。
        """
        entries: List[HistoryEntry] = []

        # 冷窗口（高度压缩）
        for turn in self.cold:
            entries.append(turn.to_history_entry())

        # 温窗口（中度压缩）
        for turn in self.warm:
            entries.append(turn.to_history_entry())

        # 热窗口（原始）
        for turn in self.hot:
            entries.append(turn.to_history_entry())

        return entries

    def get_window_summary(self) -> Dict[str, Any]:
        """获取窗口状态摘要。"""
        hot_tokens = self.compressor.estimate_tokens(self.hot)
        warm_tokens = self.compressor.estimate_tokens(self.warm)
        cold_tokens = self.compressor.estimate_tokens(self.cold)

        return {
            "hot": {"count": len(self.hot), "tokens": hot_tokens, "max": self.config.max_hot_tokens},
            "warm": {"count": len(self.warm), "tokens": warm_tokens, "max": self.config.max_warm_tokens},
            "cold": {"count": len(self.cold), "tokens": cold_tokens, "max": self.config.max_cold_tokens},
            "total_tokens": hot_tokens + warm_tokens + cold_tokens,
            "total_max": self.config.max_total_tokens,
            "compression_stats": dict(self._compression_stats),
        }

    def clear(self) -> None:
        """清空所有窗口。"""
        self.hot.clear()
        self.warm.clear()
        self.cold.clear()
        self._compression_stats = {
            "total_compressed": 0,
            "total_turns": 0,
            "last_compression_time_ms": 0.0,
        }

    # ── 窗口滑动 ───────────────────────────────────────────

    def _slide_windows(self) -> None:
        """根据窗口大小限制滑动窗口。"""
        # 热窗口溢出 → 移到温窗口
        while len(self.hot) > self.config.hot_size:
            oldest = self.hot.pop(0)
            # 温窗口也满了，先处理温窗口溢出
            if len(self.warm) >= self.config.warm_size:
                self._promote_warm_to_cold()
            self.warm.append(oldest)

        # 温窗口溢出 → 移到冷窗口
        while len(self.warm) > self.config.warm_size:
            self._promote_warm_to_cold()

        # 冷窗口溢出 → 归档（丢弃）
        while len(self.cold) > self.config.cold_size:
            self.cold.pop(0)

    def _promote_warm_to_cold(self) -> None:
        """将温窗口最旧的轮次移到冷窗口。"""
        if not self.warm:
            return

        oldest = self.warm.pop(0)

        # 尝试合并到冷窗口已有摘要
        if self.cold and self.cold[-1].intent_category == "summary":
            # 已有摘要，可以扩展（但这里简化为单独压缩）
            pass

        # 压缩后进入冷窗口
        compressed = self.compressor.compress(oldest, CompressionLevel.MEDIUM)
        self.cold.append(compressed)
        self._compression_stats["total_compressed"] += 1

    # ── Token 限制 ───────────────────────────────────────────

    def _enforce_token_limits(self) -> None:
        """检查 tokens 超限并触发压缩。"""
        if not self.config.enable_compression:
            return

        start = time.time()

        # 检查总 tokens
        total = self.compressor.estimate_tokens(self.hot + self.warm + self.cold)
        if total <= self.config.max_total_tokens:
            return

        # 超限：先压缩温窗口
        self._compress_warm()

        # 还超限：再压缩冷窗口
        total = self.compressor.estimate_tokens(self.hot + self.warm + self.cold)
        if total > self.config.max_total_tokens:
            self._compress_cold()

        self._compression_stats["last_compression_time_ms"] = (time.time() - start) * 1000

    def _compress_warm(self) -> None:
        """压缩温窗口：从轻度到中度。"""
        for i, turn in enumerate(self.warm):
            if turn.compression_level < CompressionLevel.MEDIUM.value:
                self.warm[i] = self.compressor.compress(turn, CompressionLevel.MEDIUM)
                self._compression_stats["total_compressed"] += 1

    def _compress_cold(self) -> None:
        """压缩冷窗口：合并多轮为摘要。"""
        # 将冷窗口中连续的非摘要轮次合并为摘要
        new_cold: List[WindowTurn] = []
        buffer: List[WindowTurn] = []

        for turn in self.cold:
            if turn.compression_level == 3 or turn.intent_category == "summary":
                # 已有摘要，先 flush buffer
                if buffer:
                    summary = self.compressor.summarize_range(buffer)
                    new_cold.append(summary.to_window_turn(buffer[-1].sequence))
                    buffer.clear()
                new_cold.append(turn)
            else:
                buffer.append(turn)

        # 处理剩余 buffer
        if buffer:
            summary = self.compressor.summarize_range(buffer)
            new_cold.append(summary.to_window_turn(buffer[-1].sequence))

        self.cold = new_cold

    # ── 批量加载 ───────────────────────────────────────────

    def load_from_history(self, history: List[HistoryEntry]) -> None:
        """从历史记录批量加载到窗口。"""
        self.clear()
        for i, entry in enumerate(history):
            turn = WindowTurn(
                sequence=i + 1,
                role=entry.role,
                content=entry.content,
                intent_category=entry.expectation,
                timestamp=entry.timestamp,
                metadata=entry.metadata,
            )
            self.add_turn(turn)

    # ── 查询 ───────────────────────────────────────────

    def find_turn_by_keyword(self, keyword: str, max_lookback: int = 20) -> Optional[WindowTurn]:
        """按关键词搜索最近 N 轮中的记录。"""
        all_turns = list(self.cold) + list(self.warm) + list(self.hot)
        # 按时间倒序搜索
        for turn in reversed(all_turns):
            if keyword.lower() in turn.content.lower():
                return turn
        return None

    def get_recent_entities(self, max_lookback: int = 10) -> List[str]:
        """获取最近 N 轮中的实体值。"""
        all_turns = list(self.warm) + list(self.hot)
        entities = []
        for turn in reversed(all_turns[-max_lookback:]):
            for e in turn.entities:
                if isinstance(e, dict):
                    val = e.get("value")
                    if val:
                        entities.append(str(val))
                elif isinstance(e, str):
                    entities.append(e)
        return entities
