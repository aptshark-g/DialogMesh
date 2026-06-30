# -*- coding: utf-8 -*-
"""
core/agent/window/token_counter.py
───────────────────────────────────
Light-weight token estimator.

设计要点：
  - 不依赖 tiktoken / transformers（零外部依赖）
  - 混合文本：保守估算，中文 ≈ 1 token / 字（粗略），英文 ≈ 1 token / 4 chars
  - 实际策略：总字符数 / 4 作为上限估算，对中英混合偏保守
  - 可插拔：未来可替换为精确计数器
"""

from __future__ import annotations

import re
from typing import List, Tuple

from core.agent.pcr.datacontract import HistoryEntry


class TokenCounter:
    """
    轻量级 Token 估算器。
    基于字符长度与词汇密度的混合估算。
    """

    # 中文字符范围
    _CJK_RE = re.compile(r"[\u4e00-\u9fff]")

    def __init__(self, chars_per_token: float = 4.0, cjk_weight: float = 1.0):
        """
        :param chars_per_token: 非 CJK 字符每 token 的字符数（默认 4）
        :param cjk_weight: CJK 字符权重（默认 1.0，即每个 CJK 字算 1 token）
        """
        self.chars_per_token = chars_per_token
        self.cjk_weight = cjk_weight

    def estimate_text(self, text: str) -> int:
        """
        估算单段文本的 token 数。
        公式：CJK 字数 * cjk_weight + 非 CJK 字符数 / chars_per_token
        """
        if not text:
            return 0

        cjk_count = len(self._CJK_RE.findall(text))
        non_cjk_count = len(text) - cjk_count

        tokens = int(cjk_count * self.cjk_weight + non_cjk_count / self.chars_per_token)
        return max(1, tokens) if text else 0

    def estimate_entry(self, entry: HistoryEntry) -> int:
        """估算单条 HistoryEntry 的 token 数。"""
        total = 0
        total += self.estimate_text(entry.role)
        total += self.estimate_text(entry.content)
        total += self.estimate_text(entry.expectation)
        # 元数据少量开销（固定 10 token 估算）
        if entry.metadata:
            total += 10
        return total

    def estimate_entries(self, entries: List[HistoryEntry]) -> int:
        """估算列表总 token 数。"""
        return sum(self.estimate_entry(e) for e in entries)

    def estimate_turns(self, turns: List[Tuple[str, str]]) -> int:
        """
        估算 (role, content) 列表的 token 数。
        用于快速估算，不构造 HistoryEntry。
        """
        total = 0
        for role, content in turns:
            total += self.estimate_text(role)
            total += self.estimate_text(content)
            total += 4  # 格式开销
        return total
