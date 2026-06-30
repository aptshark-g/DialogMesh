# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/decomposer.py
──────────────────────────────────────────
Syntactic decomposer with ambiguity detection.

设计要点（修正坑1）：
  - 歧义检测：COMPLEX_CLAUSE_LENGTH=30, MAX_CLAUSES_PER_INPUT=5
  - AMBIGUOUS_CONJUNCTIONS 检测多主语/多宾语
  - 复杂句标记 parse_failed 转交 hybrid 路径
  - fast 路径只处理极简指令（单主语+单谓语+单宾语）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    jieba = None  # type: ignore
    JIEBA_AVAILABLE = False


class CompilerMode(Enum):
    """编译器运行模式（与 compiler.py 共享）。"""
    FAST = "fast"
    HYBRID = "hybrid"
    FULL = "full"
    AUTO = "auto"


@dataclass(frozen=False)
class ParsedClause:
    """解析后的子句。"""
    subject: str = ""
    predicate: str = ""
    object: str = ""
    modifiers: List[str] = field(default_factory=list)  # 否定、形容词等
    parse_failed: bool = False
    parse_failed_reason: str = ""
    raw_text: str = ""
    # 回溯标记
    backfilled: bool = False           # 是否被系统补全
    backfill_source: Optional[str] = None  # 回溯来源描述
    metadata: Dict[str, Any] = field(default_factory=dict)  # 通用扩展

    def to_query(self) -> str:
        """重建查询文本。不包含内部语义标记（如 NOT()）。"""
        if self.parse_failed:
            return self.raw_text
        parts = [self.subject, self.predicate, self.object]
        parts = [p for p in parts if p]
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "modifiers": self.modifiers,
            "parse_failed": self.parse_failed,
            "parse_failed_reason": self.parse_failed_reason,
            "raw_text": self.raw_text,
            "backfilled": self.backfilled,
            "backfill_source": self.backfill_source,
            "metadata": self.metadata,
        }


class SyntacticDecomposer:
    """
    句法分解器。
    纯规则实现，不依赖 spaCy/NLTK/Jieba。
    """

    # 歧义检测参数
    COMPLEX_CLAUSE_LENGTH = 30         # 超过此长度的子句视为复杂
    MAX_CLAUSES_PER_INPUT = 5         # 超过此数量的子句标记为复杂
    AMBIGUOUS_CONJUNCTIONS = {
        "然后", "接着", "之后", "再", "并且", "而且", "同时",
        "and then", "then", "after that", "meanwhile", "also",
    }

    # 填充词/可省略词（用于简化解析）— 只作为独立词去除，避免误删子串
    FILLER_WORDS = {
        "请", "麻烦", "能不能", "可以帮我", "可以", "一下",
        "好吗", "谢谢", "谢谢了", "the", "please",
        "could you", "can you", "would you", "just", "maybe",
        "perhaps", "kind of", "sort of",
    }

    # 简单谓语映射（fast 路径使用）
    SIMPLE_PREDICATES = {
        "scan", "read", "write", "patch", "disassemble", "trace",
        "find", "hook", "break", "分析", "扫描", "读取", "写入",
        "修改", "反汇编", "追踪", "断点", "查找", "搜索",
    }

    def decompose(
        self, text: str, mode: CompilerMode = CompilerMode.AUTO
    ) -> Tuple[List[ParsedClause], List[str]]:
        """
        分解输入文本。
        返回 (子句列表, 解析追踪日志)。
        """
        trace = []
        text = text.strip()

        # 歧义检测 1: 复杂度检查
        if self._is_complex_input(text):
            trace.append(f"[DECOMP] 复杂输入 detected (len={len(text)})")
            if mode.value == "fast":
                # fast 模式无法处理，标记失败转交 hybrid
                trace.append("[DECOMP] fast 模式标记 parse_failed，建议转 hybrid")
                return [
                    ParsedClause(
                        raw_text=text,
                        parse_failed=True,
                        parse_failed_reason="复杂输入超出 fast 模式处理能力",
                    )
                ], trace

        # 歧义检测 2: 多主语检查
        if self._has_multiple_subjects(text):
            trace.append("[DECOMP] 多主语 detected")
            if mode.value == "fast":
                trace.append("[DECOMP] fast 模式标记 parse_failed")
                return [
                    ParsedClause(
                        raw_text=text,
                        parse_failed=True,
                        parse_failed_reason="多主语句无法 fast 解析",
                    )
                ], trace

        # 按连词分割为多个子句
        raw_clauses = self._split_clauses(text)
        trace.append(f"[DECOMP] 分割为 {len(raw_clauses)} 个子句")

        if len(raw_clauses) > self.MAX_CLAUSES_PER_INPUT:
            trace.append(f"[DECOMP] 子句数 {len(raw_clauses)} > {self.MAX_CLAUSES_PER_INPUT}，标记为复杂")
            if mode.value == "fast":
                return [
                    ParsedClause(
                        raw_text=text,
                        parse_failed=True,
                        parse_failed_reason=f"子句数 {len(raw_clauses)} 超过 {self.MAX_CLAUSES_PER_INPUT}",
                    )
                ], trace

        # 逐个解析子句
        clauses = []
        for i, raw_clause in enumerate(raw_clauses):
            clause = self._parse_clause(raw_clause)
            if clause.parse_failed:
                trace.append(f"[DECOMP] 子句 {i} 解析失败: {clause.parse_failed_reason}")
            else:
                trace.append(f"[DECOMP] 子句 {i}: {clause}")
            clauses.append(clause)

        return clauses, trace

    # ── 歧义检测 ───────────────────────────────────────────

    def _is_complex_input(self, text: str) -> bool:
        """检查是否为复杂输入（超过长度阈值或包含复杂结构）。"""
        if len(text) > 100:  # 长句
            return True
        # 检查嵌套从句（多个逗号、分号）
        if text.count(",") + text.count("，") >= 3:
            return True
        if text.count(";") + text.count("；") >= 2:
            return True
        return False

    def _has_multiple_subjects(self, text: str) -> bool:
        """检查是否包含多主语（多个独立主语通过连词/逗号连接）。"""
        conjunction_count = sum(1 for c in self.AMBIGUOUS_CONJUNCTIONS if c in text)
        # 多个连词 → 肯定多主语
        if conjunction_count >= 2:
            return True
        # 逗号 + 至少一个连词 → 也很可能是多主语/多子句
        comma_count = text.count(",") + text.count("，")
        if comma_count >= 1 and conjunction_count >= 1:
            return True
        return False

    # ── 子句分割 ───────────────────────────────────────────

    def _split_clauses(self, text: str) -> List[str]:
        """按连词/标点分割子句。优先使用 Jieba 分词辅助边界识别。"""
        if JIEBA_AVAILABLE and len(text) > 10:
            # Jieba 分词辅助：识别复合词边界，避免误切分
            words = jieba.lcut(text)
            # 将连词位置作为分割点，但保护复合词
            return self._jieba_aware_split(words, text)
        # 回退：正则分割
        separators = self.AMBIGUOUS_CONJUNCTIONS | {",", "，", ";", "；", ".", "。"}
        for sep in sorted(separators, key=len, reverse=True):
            text = text.replace(sep, "|SEP|")
        raw = [c.strip() for c in text.split("|SEP|") if c.strip()]
        return raw if raw else [text]

    def _jieba_aware_split(self, words: List[str], original: str) -> List[str]:
        """基于 Jieba 分词的保护性分割。"""
        # 识别连词在词列表中的位置
        split_positions = []
        for i, word in enumerate(words):
            if word in self.AMBIGUOUS_CONJUNCTIONS or word in {",", "，", ";", "；", "。", "."}:
                split_positions.append(i)

        if not split_positions:
            return [original.strip()]

        # 按位置切分
        clauses = []
        start = 0
        for pos in split_positions:
            clause = "".join(words[start:pos]).strip()
            if clause:
                clauses.append(clause)
            start = pos + 1

        # 最后一段
        tail = "".join(words[start:]).strip()
        if tail:
            clauses.append(tail)

        return clauses if clauses else [original.strip()]

    # ── 单句解析 ───────────────────────────────────────────

    def _parse_clause(self, text: str) -> ParsedClause:
        """解析单个子句。"""
        text = text.strip()
        if not text:
            return ParsedClause(raw_text=text, parse_failed=True, parse_failed_reason="空子句")

        # 去除填充词（空格分词后再替换，避免误删子串）
        words = text.split()
        cleaned_words = [w for w in words if w not in self.FILLER_WORDS]
        cleaned = " ".join(cleaned_words).strip()

        # 提取修饰语（否定、形容词等）
        modifiers = []
        # 否定词
        negation = ["不", "没", "not", "don't", "doesn't", "can't", "won't"]
        for neg in negation:
            if neg in cleaned:
                modifiers.append(f"NOT({neg})")
                cleaned = cleaned.replace(neg, "", 1)

        # 识别谓语（fast 路径：只匹配已知谓语列表）
        predicate = ""
        for pred in sorted(self.SIMPLE_PREDICATES, key=len, reverse=True):
            if pred in cleaned.lower():
                predicate = pred
                cleaned = cleaned.replace(pred, "", 1)
                break

        if not predicate:
            # 无已知谓语，标记为失败但保留已提取的修饰语
            return ParsedClause(
                raw_text=text,
                modifiers=modifiers,
                parse_failed=True,
                parse_failed_reason="未识别到已知谓语",
            )

        # 简单拆分：剩余部分第一个词作为主语，其余作为宾语
        words = [w for w in cleaned.split() if w]
        subject = words[0] if words else ""
        object_text = " ".join(words[1:]) if len(words) > 1 else ""

        return ParsedClause(
            subject=subject,
            predicate=predicate,
            object=object_text,
            modifiers=modifiers,
            raw_text=text,
        )

    def __repr__(self) -> str:
        return f"SyntacticDecomposer(jieba={JIEBA_AVAILABLE}, max_clauses={self.MAX_CLAUSES_PER_INPUT})"
