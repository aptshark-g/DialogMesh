#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统一查询集 100 条（2026-08-11）: 39 对话 + 61 文档 → md。

对话行 expected = "goldset:r000,r001,..."（块 id, 前缀 goldset）;
文档行 expected = 文档路径。测试脚本按前缀分流。
输出: docs/test/recall_queries_100.md
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set


def main():
    gold = json.load(open("data/recall_goldset.json", encoding="utf-8"))
    doc_qs = load_query_set("docs/test/recall_queries_doc.md")

    lines = [
        "# DialogMesh 统一召回查询集 — 100 条（2026-08-11）",
        "",
        "> 39 对话（goldset 块期望） + 61 文档（文档路径期望）",
        "> 格式: | id | query | expected | level | note |; 软拓展直接加行",
        "",
        "| id | query | expected | level | note |",
        "|---|---|---|---|---|",
    ]
    # 对话部分（c001...）
    for i, qi in enumerate(gold["queries"], 1):
        exp = "goldset:" + ",".join(qi["expected"])
        lines.append("| c%03d | %s | %s | dialogue | %s |" % (
            i, qi["query"].replace("|", "\\|"), exp,
            qi.get("sid", "")[:12]))
    # 文档部分（d001... 沿用原 id）
    for q in doc_qs:
        exp = "; ".join(q["expected"])
        lines.append("| %s | %s | %s | %s | %s |" % (
            q["id"], q["query"].replace("|", "\\|"),
            exp.replace("|", "\\|"),
            q.get("level", ""), (q.get("note", "") or "").replace("|", "\\|")))

    with open("docs/test/recall_queries_100.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    n = len(gold["queries"]) + len(doc_qs)
    print("written: docs/test/recall_queries_100.md (%d 条)" % n)


if __name__ == "__main__":
    main()
