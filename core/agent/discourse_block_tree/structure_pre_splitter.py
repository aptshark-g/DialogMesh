# -*- coding: utf-8 -*-
"""StructurePreSplitter — 结构化预分割层（STRUCTURE_PRESPLITTER_DESIGN_20260811）。

在 EDU 闭环切分之前, 让 markdown 结构成为天然边界:
  代码块/JSON/表格整体保留（non_chunkable）; 标题+首段同块（锚点语义）;
  列表/引用成组; 纯装饰分隔线/空壳标题 → noise 过滤。
"""
from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class StructureUnit:
    kind: str          # title | code | json | list | quote | paragraph | noise
    text: str
    non_chunkable: bool = False
    heading: str = ""  # title 单元的标题文本（元数据, 供溯源）
    children: List["StructureUnit"] = field(default_factory=list)


_CODE_FENCE = re.compile(r"^```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_=~])\1{2,}\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+|\s*\d+[.、)]\s+")


class StructurePreSplitter:
    """递归优先级: 代码块 > JSON > 标题 > 分隔线 > 列表 > 引用 > 段落。"""

    def _make_summary(self, text: str, maxlen: int = 120) -> str:
        """摘要粒度（Coarse scan 用）: 首句 + 关键实体, 不截断正文。

        设计 12.2 三级粒度（data/summary/l2_summary）的 summary 级:
        快速扫描定位用, 保留主题锚点; 命中后 Full recall 取全文。
        """
        text = text.strip()
        if not text:
            return ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        first = lines[0][:60]
        # 关键实体: 引号/粗体/大写缩写（粗略, 后续可接 LLM 摘要）
        import re as _re
        entities = _re.findall(r"\*\*([^*]{2,30})\*\*|`([^`]{2,30})`|「([^」]{2,30})」", text)
        ent = " ".join(e for tup in entities for e in tup if e)[:60]
        parts = [first]
        if ent:
            parts.append("| " + ent)
        return " ".join(parts)[:maxlen]

    def split(self, text: str) -> List[StructureUnit]:
        lines = text.split("\n")
        return self._split_lines(lines)

    def _split_lines(self, lines: List[str]) -> List[StructureUnit]:
        out: List[StructureUnit] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 1. 代码块: 整体保留, non_chunkable
            if _CODE_FENCE.match(stripped):
                buf = [line]
                i += 1
                while i < n and not _CODE_FENCE.match(lines[i].strip()):
                    buf.append(lines[i])
                    i += 1
                if i < n:  # 收尾 fence
                    buf.append(lines[i])
                    i += 1
                # 空代码块（无内容）→ noise
                body_lines = buf[1:-1] if len(buf) >= 2 else buf[1:]
                if not "".join(body_lines).strip():
                    continue
                out.append(StructureUnit("code", "\n".join(buf), non_chunkable=True))
                continue

            # 2. 顶层 JSON/数组: 整体保留, non_chunkable
            if stripped.startswith(("{", "[")):
                buf = [line]
                i += 1
                depth = 0
                while i < n:
                    buf.append(lines[i])
                    depth += lines[i].count("{") + lines[i].count("[")
                    depth -= lines[i].count("}") + lines[i].count("]")
                    i += 1
                    if depth <= 0:
                        break
                joined = "\n".join(buf)
                try:
                    _json.loads(joined)
                    out.append(StructureUnit("json", joined, non_chunkable=True))
                    continue
                except Exception:
                    # 不是合法 JSON → 退回段落累积
                    out.append(StructureUnit("paragraph", joined))
                    continue

            # 3. 标题: 新块锚点 + 吸收后继段落/列表（锚点语义）
            hm = _HEADING.match(stripped)
            if hm:
                title = hm.group(2).strip()
                body: List[str] = []
                i += 1
                while i < n:
                    nxt = lines[i].strip()
                    if (_HEADING.match(nxt) or _CODE_FENCE.match(nxt)
                            or _RULE.match(nxt)):
                        break
                    body.append(lines[i])
                    i += 1
                body_text = "\n".join(body).strip()
                if body_text:
                    out.append(StructureUnit(
                        "title", f"{title}\n{body_text}", heading=title))
                else:
                    # 空壳标题: 无后继内容 → noise
                    out.append(StructureUnit("noise", title))
                continue

            # 4. 分隔线: 结构边界; 纯装饰 → noise
            if _RULE.match(stripped):
                i += 1
                continue

            # 5. 引用块: 成组
            if _QUOTE.match(stripped):
                buf = [line]
                i += 1
                while i < n and _QUOTE.match(lines[i].strip()):
                    buf.append(lines[i])
                    i += 1
                out.append(StructureUnit(
                    "quote", "\n".join(buf), heading="quote"))
                continue

            # 6. 列表: 连续列表项并入一块
            if _LIST_ITEM.match(stripped):
                buf = [line]
                i += 1
                while i < n:
                    nxt = lines[i].strip()
                    if not nxt or _LIST_ITEM.match(nxt):
                        buf.append(lines[i])
                        i += 1
                    else:
                        break
                out.append(StructureUnit("list", "\n".join(buf)))
                continue

            # 7. 段落: 空行分隔, 软边界
            buf = [line]
            i += 1
            while i < n:
                nxt = lines[i].strip()
                if not nxt or _HEADING.match(nxt) or _CODE_FENCE.match(nxt) \
                        or _RULE.match(nxt) or _QUOTE.match(nxt):
                    break
                buf.append(lines[i])
                i += 1
            out.append(StructureUnit("paragraph", "\n".join(buf).strip()))

        return out

    def split_edus(self, text: str, maxlen: int = 280) -> List[str]:
        """结构预分割 → 单元组装（含 non_chunkable 超长保护 + 噪音过滤）。"""
        units = self.split(text)
        chunks: List[str] = []
        para_buf = ""
        for u in units:
            if u.kind == "noise" or not u.text.strip():
                continue
            if u.kind in ("code", "json") or u.non_chunkable:
                if para_buf:
                    chunks.append(para_buf)
                    para_buf = ""
                chunks.append(u.text)          # non_chunkable 不机械截断
                continue
            if u.kind == "title":
                if para_buf:
                    chunks.append(para_buf)
                    para_buf = ""
                chunks.append(u.text)          # 标题+正文段同块
                continue
            # 段落/list/quote: 相邻合并到 maxlen
            if len(para_buf) + len(u.text) <= maxlen and para_buf:
                para_buf += "。" + u.text
            else:
                if para_buf:
                    chunks.append(para_buf)
                para_buf = u.text
        if para_buf:
            chunks.append(para_buf)
        # 短块（<15 字符且非代码/JSON）并入前一块: 过渡语（"运行结果："）不应
        # 独立成块, 与后继内容同块保上下文（2026-08-11, goldset 复查发现）
        merged = []
        for c in chunks:
            c = c.strip()
            if not c:
                continue
            if (len(c) < 15 and not c.startswith(("```", "{"))
                    and not c.startswith("[")):
                if merged:
                    merged[-1] = merged[-1] + "。" + c
                else:
                    merged.append(c)
            else:
                merged.append(c)
        return merged

    def split_with_granularity(self, text: str, maxlen: int = 280
                               ) -> List[dict]:
        """两级粒度切分（设计 12.2）: 每块带 {text(全文), summary(摘要)}。

        摘要 = 首句+关键实体（Coarse scan 快速定位）; 全文 = Full recall
        精确加载。块内多主题由 summary 粒度缓解——小块先定位, 大块再取。
        """
        chunks = self.split_edus(text, maxlen=maxlen)
        out = []
        for c in chunks:
            out.append({
                "text": c,
                "summary": self._make_summary(c),
                "granularity": "coarse" if len(c) > 200 else "full",
            })
        return out
