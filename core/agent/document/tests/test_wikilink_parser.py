# -*- coding: utf-8 -*-
"""WikilinkParser 测试（CONTENT_TO_GRAPH 设计 1, 2026-08-11）。"""
from __future__ import annotations

from core.agent.document.wikilink_parser import (
    WikilinkParser, parse_frontmatter, extract_wikilinks)


def test_parse_frontmatter():
    text = """---
title: Intent Parser
tags: [index, intent-parser]
source: docs/v3.0/x.md
---

# 正文"""
    fm = parse_frontmatter(text)
    assert fm["title"] == "Intent Parser"
    assert fm["source"] == "docs/v3.0/x.md"


def test_parse_frontmatter_missing():
    assert parse_frontmatter("无 frontmatter 的正文") == {}


def test_extract_wikilinks():
    text = "见 [[design_layer1_intent_parser]] 和 [[DESIGN_03_INPUT_AND_SKILL|技能层]]"
    links = extract_wikilinks(text)
    assert "design_layer1_intent_parser" in links
    assert "DESIGN_03_INPUT_AND_SKILL" in links  # 别名只取 target


def test_wikilink_parser_attaches_meta():
    parser = WikilinkParser()
    text = """---
title: 测试文档
tags: [test]
---

# 标题

参考 [[其他文档]]
"""
    root = parser.parse(text, "vault:测试文档")
    assert root.meta["frontmatter"]["title"] == "测试文档"
    assert "其他文档" in root.meta["wikilinks"]
    assert root.meta["is_index"] is False


def test_wikilink_parser_index_detection():
    parser = WikilinkParser()
    root = parser.parse("# x\n\n[[a]]", "00-INDEX-INTENT.md")
    assert root.meta["is_index"] is True


def test_wikilink_parser_keeps_heading_tree():
    """超集不破坏原标题层级解析。"""
    parser = WikilinkParser()
    root = parser.parse("## 二级标题\n正文\n### 三级标题\n更多", "t.md")
    headings = [c.raw_text for c in root.children]
    assert any("二级标题" in h for h in headings)
