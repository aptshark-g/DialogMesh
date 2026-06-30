# -*- coding: utf-8 -*-
"""
core/agent/context_window/models.py
──────────────────────────────────
Data models for context window management.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from core.agent.pcr.datacontract import HistoryEntry


@dataclass(frozen=False)
class WindowTurn:
    """窗口中的单轮记录（可能为压缩后）。"""
    sequence: int
    role: str
    content: str
    # 压缩元信息
    compression_level: int = 0  # 0=原始, 1=轻度压缩, 2=中度, 3=高度摘要
    original_content: Optional[str] = None  # 压缩前的原始内容
    # 意图标签（温窗口保留）
    intent_category: Optional[str] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    # 时间戳
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_history_entry(self) -> HistoryEntry:
        """转换为 PCR HistoryEntry。"""
        return HistoryEntry(
            role=self.role,
            content=self.content,
            expectation=self.intent_category or "",
            timestamp=self.timestamp,
            metadata=self.metadata,
        )

    @property
    def estimated_tokens(self) -> int:
        """估算 token 数（中文字符 ≈ 1 token，英文 ≈ 0.75 token）。"""
        content = self.content or ""
        # 简单估算：每个字符按语言权重计算
        cn_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
        other_chars = len(content) - cn_chars
        return int(cn_chars * 1.0 + other_chars * 0.75)

    def __repr__(self) -> str:
        return f"WindowTurn(seq={self.sequence}, role={self.role}, comp={self.compression_level}, tokens={self.estimated_tokens})"


@dataclass(frozen=False)
class CompressedSummary:
    """冷窗口的高度摘要。"""
    topic: str = ""                    # 主题标签
    key_entities: List[str] = field(default_factory=list)  # 关键实体
    turn_range: tuple = (0, 0)        # 覆盖的原始轮次范围
    summary_text: str = ""            # 摘要文本
    intent_distribution: Dict[str, int] = field(default_factory=dict)  # 意图分布统计

    def to_window_turn(self, sequence: int) -> WindowTurn:
        """转换为 WindowTurn 用于插入窗口。"""
        return WindowTurn(
            sequence=sequence,
            role="system",
            content=self.summary_text,
            compression_level=3,
            intent_category="summary",
            metadata={
                "topic": self.topic,
                "key_entities": self.key_entities,
                "turn_range": self.turn_range,
                "intent_distribution": self.intent_distribution,
            },
        )

    def __repr__(self) -> str:
        return f"CompressedSummary(topic={self.topic!r}, range={self.turn_range}, entities={self.key_entities})"
