#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""召回式隐式关系发现 — 候选生成（2026-08-11）。

显式边（双链/INDEX）之外, 用文档摘要向量相似度找"语义相关但无链接"
的隐式关系候选 → 供 LLM 核验（inferred_verified）。

用法: .venv\\Scripts\\python.exe scripts/implicit_edge_candidates.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VAULT = r"C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design"
THRESHOLD = 0.55   # 相似度阈值（排除 INDEX 后收紧, 宁缺勿滥）


def main():
    from core.agent.compiler.semantic_encoder import SemanticEncoder
    encoder = SemanticEncoder()

    # 1. 文档摘要（frontmatter title + 首行 + INDEX 焦点近似）
    docs = []
    all_files = sorted(glob.glob(os.path.join(VAULT, "*.md")))
    # 排除 INDEX/MOC 导航页: 它们是索引非内容, 格式相似度高易假阳性
    content_files = [fp for fp in all_files
                     if not re.search(r"(00-INDEX|MOC)", os.path.basename(fp))]
    for fp in content_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        text = open(fp, encoding="utf-8").read()
        fm = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        title = name
        if fm:
            m = re.search(r"title:\s*(.+)", fm.group(1))
            if m:
                title = m.group(1).strip().strip("\"'")
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        first = re.sub(r"^#+\s*", "", first)[:100]
        docs.append({"name": name, "title": title,
                     "summary": f"{title}。{first}"[:200]})

    # 2. 显式边集（双链, 用于排除）
    explicit = set()
    for fp in glob.glob(os.path.join(VAULT, "*.md")):
        name = os.path.splitext(os.path.basename(fp))[0]
        text = open(fp, encoding="utf-8").read()
        for t in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text):
            explicit.add((name, t.split("#")[0].strip()))
            explicit.add((t.split("#")[0].strip(), name))

    # 显式边排除也要过滤导航页（内容文档之间的显式链接才有效）

    # 3. 编码 + 两两相似
    print("内容文档: %d（排除 INDEX/MOC %d 个）" % (
        len(docs), len(all_files) - len(content_files)))
    vecs = encoder.encode([d["summary"] for d in docs])
    import numpy as np
    sims = vecs @ vecs.T
    candidates = []
    n = len(docs)
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sims[i][j])
            if s < THRESHOLD:
                continue
            a, b = docs[i]["name"], docs[j]["name"]
            if (a, b) in explicit:
                continue
            candidates.append({
                "source": a, "target": b, "similarity": round(s, 3),
                "source_summary": docs[i]["summary"][:80],
                "target_summary": docs[j]["summary"][:80],
            })
    candidates.sort(key=lambda c: -c["similarity"])

    out = {
        "docs": n,
        "explicit_edges": len(explicit) // 2,
        "threshold": THRESHOLD,
        "implicit_candidates": len(candidates),
        "candidates": candidates,
    }
    with open("data/implicit_edge_candidates.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("文档: %d | 显式边: %d | 隐式候选: %d (阈值 %.2f)" % (
        n, len(explicit) // 2, len(candidates), THRESHOLD))
    for c in candidates[:15]:
        print("  %s <-> %s (%.3f)" % (
            c["source"][:40], c["target"][:40], c["similarity"]))


if __name__ == "__main__":
    main()
