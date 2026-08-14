# -*- coding: utf-8 -*-
"""查询集加载 — 支持 md/json 双格式（2026-08-11）。

md 格式（docs/test/recall_queries_doc.md）: 表格
  | id | query | expected | level | note | intent |（intent 可省略）
软拓展: 直接编辑 md 加行即可, 测试脚本解析。
"""
from __future__ import annotations

import json
import re
from typing import List, Optional


def load_query_set(path: str) -> List[dict]:
    """按扩展名加载查询集（md 表格 / json）。"""
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("queries", d) if isinstance(d, dict) else d
    return load_query_set_md(path)


def load_query_set_md(path: str) -> List[dict]:
    """解析 md 表格查询集: | id | query | expected | level | note | intent |。

    intent（第 6 列, 2026-08-13, W1 意图感知评测）: 该 query 在生产的
    意图类别（与 _GatewayLLMAdapter.classify_intent 类别集对齐）; 省略
    时默认 "记忆召回"（知识类 query 为主, 保守默认）。
    """
    out = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    header_seen = False
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header_seen:
            if cells and cells[0].lower() == "id":
                header_seen = True
            continue
        if len(cells) < 4 or set("".join(cells)) <= {"-", " "}:
            continue
        qid = cells[0]
        query = cells[1].replace("\\|", "|")
        expected = [e.strip() for e in cells[2].split(";") if e.strip()]
        level = cells[3] if len(cells) > 3 else "simple"
        note = cells[4].replace("\\|", "|") if len(cells) > 4 else ""
        intent = cells[5].strip() if len(cells) > 5 else "记忆召回"
        out.append({"id": qid, "query": query, "expected": expected,
                    "level": level, "note": note, "intent": intent})
    return out


def dedupe_queries(queries: List[dict]) -> List[dict]:
    """按 query 文本去重（保留首条）。"""
    seen = set()
    out = []
    for q in queries:
        key = q["query"].strip()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out
