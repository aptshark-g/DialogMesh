"""层2 编译 serializer 家族（B5-3-P3）。

to_ir 产出语言中立 IR（Context IR v2），serializer 渲染为 4 种给 LLM 的形态:
  - json     : 结构化精确（默认）
  - xml      : A8 精确语义, 树形结构自然映射
  - markdown : 文本线性化（assemble_prompt 现有形态）
  - natural  : 自然语言（通用模型友好, 模糊）

设计: 单一入口 serialize(ir, fmt) + 每形态独立函数, 无副作用。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


FORMATS = ("json", "xml", "markdown", "natural")
FORMAT_ALIASES = {
    "text": "markdown",
    "nl": "natural",
    "prompt": "markdown",
    "structured": "json",
}


def normalize_format(fmt: str) -> str:
    """归一形态名（兼容别名），非法回退 json。"""
    key = (fmt or "json").strip().lower()
    return FORMAT_ALIASES.get(key, key if key in FORMATS else "json")


def _entries(ir: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = ir.get("entries", [])
    return entries if isinstance(entries, list) else []


def to_json(ir: Dict[str, Any]) -> str:
    """JSON 结构化（Context IR v2 直出）。"""
    return json.dumps(ir, ensure_ascii=False, indent=2)


def to_xml(ir: Dict[str, Any]) -> str:
    """XML: 树形精确语义（A8）。"""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<context>')
    lines.append(f'  <meta perspective="{_esc(ir.get("perspective", ""))}" '
                 f'intent="{_esc(ir.get("intent_category", ""))}" '
                 f'strategy="{_esc(ir.get("compile_strategy", ""))}" '
                 f'total_tokens="{ir.get("total_estimated_tokens", 0)}" '
                 f'budget="{ir.get("budget", 0)}"/>')
    alloc = ir.get("domain_allocation") or {}
    if isinstance(alloc, dict) and alloc:
        lines.append('  <allocation>')
        for k, v in alloc.items():
            lines.append(f'    <domain name="{_esc(str(k))}" tokens="{v}"/>')
        lines.append('  </allocation>')
    if _entries(ir):
        lines.append('  <entries>')
        for e in _entries(ir):
            lines.append('    <entry>')
            lines.append(f'      <domain>{_esc(e.get("domain", ""))}</domain>')
            lines.append(f'      <type>{_esc(e.get("type", ""))}</type>')
            lines.append(f'      <confidence>{e.get("confidence", 0.5)}</confidence>')
            lines.append(f'      <tokens>{e.get("estimated_tokens", 0)}</tokens>')
            lines.append(f'      <content>{_esc(e.get("content", ""))}</content>')
            for ref in e.get("cross_refs") or []:
                if isinstance(ref, dict):
                    lines.append(f'      <cross_ref target="{_esc(ref.get("target_domain", ""))}" '
                                 f'event="{_esc(ref.get("target_event_id", ""))}" '
                                 f'note="{_esc(ref.get("note", ""))}"/>')
            lines.append('    </entry>')
        lines.append('  </entries>')
    lines.append('</context>')
    return "\n".join(lines)


def to_markdown(ir: Dict[str, Any]) -> str:
    """Markdown 文本线性化（原 assemble_prompt 形态）。"""
    lines = [f"### Context — {ir.get('perspective', '?')} perspective"]
    lines.append(f"- intent: {ir.get('intent_category', '?')}")
    lines.append(f"- strategy: {ir.get('compile_strategy', '?')}")
    lines.append(f"- total_tokens: {ir.get('total_estimated_tokens', 0)}")
    if _entries(ir):
        lines.append("")
        for e in _entries(ir):
            lines.append(f"- [{e.get('domain', '?')}] {e.get('content', '')}")
            for ref in e.get("cross_refs") or []:
                if isinstance(ref, dict):
                    lines.append(f"  - ^ref: {ref.get('target_domain', '?')}."
                                 f"{ref.get('target_event_id', '')} = {ref.get('note', '')}")
    return "\n".join(lines)


def to_natural(ir: Dict[str, Any]) -> str:
    """自然语言: 通用模型友好（模糊但可读）。"""
    parts = []
    perspective = ir.get("perspective", "当前")
    intent = ir.get("intent_category", "一般查询")
    parts.append(f"以下是关于「{perspective}」视角的上下文，当前意图为「{intent}」。")
    alloc = ir.get("domain_allocation") or {}
    if isinstance(alloc, dict) and alloc:
        domains = "、".join(f"{k}（{v} token）" for k, v in alloc.items())
        parts.append(f"上下文按领域分配如下：{domains}。")
    entries = _entries(ir)
    if entries:
        parts.append("具体内容包括：")
        for e in entries:
            domain = e.get("domain", "?")
            content = e.get("content", "")
            conf = e.get("confidence", 0.5)
            parts.append(f"- 领域{domain}：{content}（置信度 {conf:.2f}）")
            for ref in e.get("cross_refs") or []:
                if isinstance(ref, dict):
                    parts.append(f"  关联到领域{ref.get('target_domain', '?')}"
                                 f"（{ref.get('note', '')}）")
    else:
        parts.append("当前暂无具体内容。")
    parts.append("请基于以上上下文作答。")
    return "\n".join(parts)


def serialize(ir: Dict[str, Any], fmt: str = "json") -> Dict[str, Any]:
    """统一入口: 渲染 IR 为指定形态。返回 {format, text, tokens}。"""
    fmt = normalize_format(fmt)
    if fmt == "xml":
        text = to_xml(ir)
    elif fmt == "markdown":
        text = to_markdown(ir)
    elif fmt == "natural":
        text = to_natural(ir)
    else:
        text = to_json(ir)
    return {"format": fmt, "text": text, "tokens": len(text) // 4}


def _esc(text: Any) -> str:
    """XML 转义。"""
    s = str(text if text is not None else "")
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;")
             .replace("'", "&apos;"))
