# -*- coding: utf-8 -*-
"""
core/agent/context_window/compressor.py
───────────────────────────────────
Rule-based compressor for context window management.

设计要点：
  - 零 LLM 依赖：纯规则 + 关键词提取
  - 三级压缩：轻度（保留关键实体）→ 中度（保留意图标签）→ 高度（摘要）
  - 可逆性：压缩不丢失意图分类所需的关键信息
  - 延迟 < 5ms / 轮
"""

from __future__ import annotations

import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.context_window.models import WindowTurn, CompressedSummary


class CompressionLevel(Enum):
    """压缩级别。"""
    NONE = 0       # 原始记录
    LIGHT = 1      # 轻度：保留关键实体 + 删除填充词
    MEDIUM = 2     # 中度：保留意图标签 + 实体列表
    HEAVY = 3      # 高度：仅保留主题 + 关键实体 + 统计信息


class RuleBasedCompressor:
    """
    基于规则的上下文压缩器。
    不调用 LLM，纯 Python 规则处理。
    """

    # 填充词（可删除而不影响意图分类）
    FILLER_WORDS = {
        "请", "麻烦", "能不能", "能不能帮我", "可以帮我", "可以",
        "一下", "一下下", "好吗", "谢谢", "谢谢了", "麻烦了",
        "the", "a", "an", "please", "could you", "can you", "would you",
        "just", "maybe", "perhaps", "kind of", "sort of",
    }

    # 关键实体类型（压缩时保留）
    KEY_ENTITY_TYPES = {
        "memory_address", "numeric_value", "pointer_chain",
        "process_name", "pid", "module_name", "function_name",
        "byte_pattern", "scan_type", "data_type",
    }

    # 意图关键词映射（用于提取意图标签）
    INTENT_KEYWORDS = {
        "scan": "scan_memory",
        "read": "read_memory",
        "write": "write_memory",
        "disassemble": "disassemble",
        "decompile": "decompile",
        "trace": "trace_execution",
        "patch": "write_memory",
        "find": "find_pattern",
        "hook": "set_breakpoint",
        "break": "set_breakpoint",
        "分析": "analyze",
        "扫描": "scan_memory",
        "读取": "read_memory",
        "写入": "write_memory",
        "修改": "write_memory",
        "反汇编": "disassemble",
        "追踪": "trace_execution",
        "断点": "set_breakpoint",
    }

    def __init__(self, max_tokens_per_window: int = 4000):
        self.max_tokens_per_window = max_tokens_per_window

    # ── 压缩 API ───────────────────────────────────────────

    def compress(self, turn: WindowTurn, level: CompressionLevel) -> WindowTurn:
        """对单轮记录执行压缩。"""
        if level == CompressionLevel.NONE:
            return turn

        original = turn.content

        if level == CompressionLevel.LIGHT:
            content = self._light_compress(original)
        elif level == CompressionLevel.MEDIUM:
            content = self._medium_compress(original)
        else:  # HEAVY
            content = self._heavy_compress(original)

        return WindowTurn(
            sequence=turn.sequence,
            role=turn.role,
            content=content,
            compression_level=level.value,
            original_content=original,
            intent_category=turn.intent_category or self._extract_intent(original),
            entities=turn.entities,
            timestamp=turn.timestamp,
            metadata={**turn.metadata, "compressed": True, "original_tokens": self._estimate_tokens(original)},
        )

    def summarize_range(self, turns: List[WindowTurn]) -> CompressedSummary:
        """对多轮记录生成高度摘要。"""
        if not turns:
            return CompressedSummary()

        # 提取主题（通过关键词频率）
        topic = self._extract_topic(turns)

        # 收集所有关键实体
        all_entities: Set[str] = set()
        intent_counts: Dict[str, int] = {}

        for turn in turns:
            intent = turn.intent_category or self._extract_intent(turn.content)
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

            for entity in turn.entities:
                if isinstance(entity, dict):
                    etype = entity.get("type", "")
                    if etype in self.KEY_ENTITY_TYPES:
                        all_entities.add(str(entity.get("value", "")))
                elif isinstance(entity, str):
                    all_entities.add(entity)

        # 生成摘要文本
        min_seq = min(t.sequence for t in turns)
        max_seq = max(t.sequence for t in turns)
        summary_text = self._generate_summary_text(topic, intent_counts, all_entities, min_seq, max_seq)

        return CompressedSummary(
            topic=topic,
            key_entities=list(all_entities)[:20],  # 限制数量
            turn_range=(min_seq, max_seq),
            summary_text=summary_text,
            intent_distribution=intent_counts,
        )

    # ── 压缩策略 ───────────────────────────────────────────

    def _light_compress(self, text: str) -> str:
        """轻度压缩：删除填充词，保留所有实体。"""
        result = text
        for filler in sorted(self.FILLER_WORDS, key=len, reverse=True):
            result = result.replace(filler, "")
        # 清理多余空格
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _medium_compress(self, text: str) -> str:
        """中度压缩：保留意图标签 + 关键实体列表。"""
        intent = self._extract_intent(text)
        entities = self._extract_entities(text)
        # 格式："[意图] 实体1 实体2 ..."
        if entities:
            return f"[{intent}] {', '.join(entities)}"
        return f"[{intent}] {text[:50]}..."

    def _heavy_compress(self, text: str) -> str:
        """高度压缩：仅保留意图标签。"""
        intent = self._extract_intent(text)
        return f"[{intent}]"

    # ── 提取工具 ───────────────────────────────────────────

    def _extract_intent(self, text: str) -> str:
        """从文本中提取意图标签。"""
        text_lower = text.lower()
        for keyword, intent in self.INTENT_KEYWORDS.items():
            if keyword in text_lower:
                return intent
        return "unknown"

    def _extract_entities(self, text: str) -> List[str]:
        """提取文本中的实体（简单正则）。"""
        entities = []
        # 内存地址
        for match in re.finditer(r'0x[0-9a-fA-F]+', text):
            entities.append(match.group())
        # 数值
        for match in re.finditer(r'\b\d+\b', text):
            entities.append(match.group())
        # 进程名
        for match in re.finditer(r'\b\w+\.exe\b', text, re.IGNORECASE):
            entities.append(match.group())
        return entities[:10]

    def _extract_topic(self, turns: List[WindowTurn]) -> str:
        """从多轮记录中提取主题。"""
        # 简单策略：频率最高的意图标签作为主题
        intent_counts: Dict[str, int] = {}
        for turn in turns:
            intent = turn.intent_category or self._extract_intent(turn.content)
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        if not intent_counts:
            return "general"
        return max(intent_counts, key=intent_counts.get)

    def _generate_summary_text(
        self, topic: str, intent_counts: Dict[str, int],
        entities: Set[str], min_seq: int, max_seq: int
    ) -> str:
        """生成摘要文本。"""
        total_turns = max_seq - min_seq + 1
        intent_summary = ", ".join(
            f"{intent}:{count}" for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1])[:3]
        )
        entity_summary = ", ".join(sorted(entities)[:5])

        text = f"[摘要] 轮次 {min_seq}-{max_seq} (共{total_turns}轮) | 主题:{topic} | 意图:{intent_summary}"
        if entity_summary:
            text += f" | 实体:{entity_summary}"
        return text

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数。"""
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - cn_chars
        return int(cn_chars * 1.0 + other_chars * 0.75)

    def estimate_tokens(self, turns: List[WindowTurn]) -> int:
        """估算总 token 数。"""
        return sum(t.estimated_tokens for t in turns)
