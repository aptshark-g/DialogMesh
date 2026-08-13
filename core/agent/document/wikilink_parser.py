# -*- coding: utf-8 -*-
"""WikilinkParser — MarkdownParser 超集: frontmatter + [[双链]] 解析。

CONTENT_TO_GRAPH_20260811 设计 1: Obsidian vault 文档的显式图边
（双链）与元数据（frontmatter）此前被 MarkdownParser 丢弃;
本解析器在保留原标题层级树的同时, 把图关系挂到 root 元数据:
  root.meta = {frontmatter: {...}, wikilinks: [...], is_index: bool}
"""
from __future__ import annotations

import re
from typing import Dict, List

from .parsers import MarkdownParser
from .tree import DocumentNode


def parse_frontmatter(text: str) -> Dict[str, str]:
    """解析 Obsidian frontmatter（--- 包裹的 YAML 头部, 简化版 key: value）。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def extract_wikilinks(text: str) -> List[str]:
    """提取 [[target]] 双链（含别名 [[target|显示名]] → 取 target）。"""
    return [t.strip() for t in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)]


class WikilinkParser(MarkdownParser):
    """MarkdownParser 超集: 标题层级 + frontmatter + 双链。"""

    def parse(self, content: str, source_path: str) -> DocumentNode:
        root = super().parse(content, source_path)
        root.meta = {  # type: ignore[attr-defined]
            "frontmatter": parse_frontmatter(content),
            "wikilinks": extract_wikilinks(content),
            "is_index": bool(re.search(r"(00-INDEX|MOC|INDEX)", source_path)),
        }
        return root
