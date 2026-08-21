# -*- coding: utf-8 -*-
"""B-3 固化前缀（编译器侧契约, 2026-08-22）。

对齐网关 prefix 包（switch/prefix）的角色分段:

    P0 系统提示 + 平台工具定义       → 网关 Seg0（system + tools）
    P1 租户块（人格/合规/租户知识）  → 网关 Seg1（历史）
    P2 项目块（项目语料/约束）       → 网关 Seg1
    P3 会话块（折叠历史）            → 网关 Seg1
    P4 本轮输入（时间戳/uuid 等易变）→ 网关 Seg2

铁律（基线 §5.1）:
  - P0..P3 只追加、不插入、不重排;
  - 时间戳/uuid/trace_id/request_id 只进 P4 或 header;
  - 网关禁止静默改写前缀, 固化在编译器完成, 网关只做检测/统计。

本模块提供: 去噪（strip_volatile）+ 分层重排（normalize_stable_prefix）+
稳定指纹（stable_fingerprint, golden 测试 0 漂移断言）。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

# 易变内容正则（命中 → 归一化占位, 不让其进入前缀影响命中）
_VOLATILE_PATTERNS = [
    # ISO 时间戳: 2026-08-22T12:00:00Z / 2026-08-22 12:00:00.123 +08:00
    re.compile(r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
               r"(?:Z|[+-]\d{2}:?\d{2})?\b"),
    re.compile(r"\b[0-9a-f]{32}\b"),          # md5/hex32
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
               r"[0-9a-f]{4}-[0-9a-f]{12}\b"),  # uuid
    re.compile(r"\breq[-_][0-9a-z]{6,}\b", re.I),   # request_id
    re.compile(r"\btrace[-_][0-9a-z]{6,}\b", re.I),  # trace_id
    re.compile(r"\bsession[-_][0-9a-z]{6,}\b", re.I),  # session_id
]


def strip_volatile(text: str) -> str:
    """把易变内容从前缀剥离（归一化占位, 不删除长度语义）。"""
    out = text or ""
    for pat in _VOLATILE_PATTERNS:
        out = pat.sub("<V>", out)
    return out


def normalize_stable_prefix(
    messages: List[Dict[str, Any]],
    *,
    role_key: str = "role",
    content_key: str = "content",
) -> List[Dict[str, Any]]:
    """分层重排 + 去噪（P0-P3 稳定, P4 保留原文）。

    - system 消息全部置前（P0, 保持原相对顺序）;
    - 其余历史除最后一条为 P1-P3（按原序, 去噪）;
    - 最后一条消息为 P4（本轮输入, 保留原文——它本就不参与命中前缀）。
    """
    if not messages:
        return list(messages)
    system = [m for m in messages if m.get(role_key) == "system"]
    rest = [m for m in messages if m.get(role_key) != "system"]
    out: List[Dict[str, Any]] = []
    for m in system:
        out.append({**m, content_key: strip_volatile(m.get(content_key, ""))})
    for m in rest[:-1]:
        out.append({**m, content_key: strip_volatile(m.get(content_key, ""))})
    if rest:
        out.append(dict(rest[-1]))  # P4 原样
    return out


def stable_fingerprint(
    messages: List[Dict[str, Any]],
    *,
    include_p4: bool = False,
) -> str:
    """规范化前缀的稳定指纹（golden 测试断言 0 漂移用）。

    include_p4=False（默认）: 只对 P0-P3 归一化内容做指纹,
    用于断言「同逻辑上下文 → 同前缀」;
    include_p4=True: 全量（含本轮输入）。
    """
    norm = normalize_stable_prefix(messages)
    payload = norm if include_p4 else norm[:-1]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tool_defs_sorted(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """工具定义按 name 排序（P0 稳定性的一部分; 网关 prefix 包同样排序）。"""
    if not tools:
        return list(tools or [])
    return sorted(tools, key=lambda t: str(t.get("name", "")))
