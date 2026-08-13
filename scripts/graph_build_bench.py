#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""内容→图 时间效率基准（2026-08-11）。

测量: vault 解析 + 落盘 + ConceptGraph 加载 的耗时分布。
用法: .venv\\Scripts\\python.exe scripts/graph_build_bench.py
"""
from __future__ import annotations

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VAULT = r"C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design"


def main():
    from core.agent.document.wikilink_parser import (
        parse_frontmatter, extract_wikilinks)
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    from core.agent.context.graph_source import ConceptGraph

    out = []
    # 1. 解析
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(VAULT, "*.md")))
    parsed = []
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        parsed.append((name, parse_frontmatter(text), extract_wikilinks(text)))
    t_parse = time.time() - t0
    out.append("解析 %d 篇: %.0f ms (%.1f ms/篇)" % (
        len(files), t_parse * 1000, t_parse * 1000 / max(1, len(files))))

    # 2. 落盘（含 delete_domain 幂等）
    t0 = time.time()
    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    store.delete_domain("vault_docs")
    nodes = edges = 0
    for name, fm, links in parsed:
        store.save_node(
            node_id=f"vault:{name}", node_type="document",
            domain="vault_docs",
            data={"title": fm.get("title", name), "tags": fm.get("tags", ""),
                  "source": fm.get("source", "")},
            summary=fm.get("title", name), tier="H")
        nodes += 1
        for target in links:
            store.save_edge(
                edge_type="wikilink", domain="vault_docs",
                source_id=f"vault:{name}", target_id=f"vault:{target}",
                data={"source_kind": "extracted"}, weight=0.9)
            edges += 1
    store.close()
    t_store = time.time() - t0
    out.append("落盘 %d 节点 %d 边（含清理）: %.0f ms" % (
        nodes, edges, t_store * 1000))

    # 3. ConceptGraph 加载（含社区检测）
    t0 = time.time()
    store2 = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store2.open()
    g = ConceptGraph()
    n = g.build_from_graph_store(store2)
    t_graph = time.time() - t0
    store2.close()
    out.append("ConceptGraph 加载 %d 节点 / %d 边 / %d 社区: %.0f ms" % (
        n, len(g._edges), len(g._communities), t_graph * 1000))
    out.append("总耗时: %.0f ms" % ((t_parse + t_store + t_graph) * 1000))
    out.append("增量更新估算: 单篇解析 %.1f ms + 落盘" % (
        t_parse * 1000 / max(1, len(files))))

    with open("docs/test/GRAPH_BUILD_BENCH_20260811.md", "w", encoding="utf-8") as f:
        f.write("# 内容→图 时间效率基准（2026-08-11）\n\n")
        f.write("\n".join("- " + line for line in out))
        f.write("\n\n- 环境: .venv Python 3.13, 本地无 LLM（纯解析+SQLite）\n")
    print("\n".join(out))
    print("written: docs/test/GRAPH_BUILD_BENCH_20260811.md")


if __name__ == "__main__":
    main()
