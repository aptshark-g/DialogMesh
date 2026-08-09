# -*- coding: utf-8 -*-
"""文本与序列化基础设施 — 根治类型/编码/匹配类反复问题.

设计: docs/only/blueprint/ERROR_META_REFLECTION_20260806.md §二

三类问题的统一解法:
  - safe_str:         任意对象 → str（防 None/Dataclass/自定义类 repr 崩溃）
  - to_json_safe:     任意对象 → JSON 可序列化（决策事件/工具结果/before-after）
  - zh_keyword_match: 双语言匹配（中文字典优先, 英文子串兜底）
  - normalize_text:   UTF-8 归一化（去 BOM/混入编码/控制字符）
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


def safe_str(x: Any, limit: int = 500) -> str:
    """任意对象 → str，绝不抛异常。"""
    try:
        if x is None:
            return ""
        if isinstance(x, str):
            s = x
        elif isinstance(x, (dict, list, tuple)):
            s = json.dumps(x, ensure_ascii=False, default=str)
        else:
            s = str(x)
        if limit and len(s) > limit:
            return s[:limit] + "..."
        return s
    except Exception:
        try:
            return repr(x)[:limit]
        except Exception:
            return "<unprintable>"


def to_json_safe(x: Any, limit: int = 1000) -> Any:
    """任意对象 → JSON 可序列化值（递归降级，绝不抛异常）。"""
    try:
        if x is None or isinstance(x, (str, int, float, bool)):
            return x
        if isinstance(x, dict):
            return {str(k): to_json_safe(v, limit) for k, v in x.items()}
        if isinstance(x, (list, tuple, set)):
            return [to_json_safe(v, limit) for v in x]
        if is_dataclass(x) and not isinstance(x, type):
            return to_json_safe(asdict(x), limit)
        if hasattr(x, "to_dict") and callable(x.to_dict):
            return to_json_safe(x.to_dict(), limit)
        # 兜底: 摘要 str
        return safe_str(x, limit=limit)
    except Exception:
        return safe_str(x, limit=limit)


def zh_keyword_match(query: str, keywords_zh: Iterable[str],
                     en_text: str = "", name: str = "") -> bool:
    """双语言匹配：中文字典命中优先, 英文子串兜底。

    解决 "discover('查论文') 匹配不到英文工具描述"（ERROR_META §一 类2）。
    任一命中即返回 True:
      - 任一中文关键词是 query 的子串（或 query 是关键词子串）
      - query 在英文 name/en_text 子串中（原 discover 逻辑）
    """
    if not query:
        return False
    q = query.lower()
    # 中文: 关键词 ↔ query 互相子串
    for kw in keywords_zh or []:
        if not kw:
            continue
        if kw in query or query in kw:
            return True
    # 英文: name/en_text 子串（保持原 discover 语义）
    if name and q in name.lower():
        return True
    if en_text and q in en_text.lower():
        return True
    return False


def normalize_text(s: Any) -> str:
    """UTF-8 归一化：去 BOM/混入编码/不可见控制字符。"""
    text = safe_str(s, limit=0)
    if text.startswith("\ufeff"):
        text = text[1:]
    # 去控制字符（保留换行/制表）
    chars = []
    for ch in text:
        cp = ord(ch)
        if cp < 32 and ch not in "\n\t\r":
            continue
        chars.append(ch)
    return "".join(chars)
