#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Obsidian Vault → 图落盘（CONTENT_TO_GRAPH 设计 1, 2026-08-11）。

解析 dialogmesh-design vault（35 篇）: frontmatter + [[双链]] →
  UnifiedGraphStore 节点（domain=vault_docs）+ 边（wikilink, extracted）。

用法: .venv\\Scripts\\python.exe scripts/build_vault_graph.py
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.document.wikilink_parser import (
    WikilinkParser, parse_frontmatter, extract_wikilinks)
import glob as _glob

VAULT = r"C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design"


def main():
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    store = UnifiedGraphStore(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "unified_graph.db"))
    store.open()
    store.delete_domain("vault_docs")  # 幂等重建（2026-08-11）
    parser = WikilinkParser()
    files = sorted(glob.glob(os.path.join(VAULT, "*.md")))
    # docs 文件名 → 相对路径映射（跨库引用解析, 2026-08-11）
    docs_map = {}
    for df in _glob.glob(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", "**", "*.md"), recursive=True):
        base = os.path.splitext(os.path.basename(df))[0]
        rel = os.path.relpath(df, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        docs_map.setdefault(base, rel)
    nodes = 0
    edges = 0
    verified_count = 0
    unresolved = set()
    cross_edges = 0
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        fm = parse_frontmatter(text)
        links = extract_wikilinks(text)
        # 摘要: INDEX 表格"焦点"无法简单解析, 先用 frontmatter title + 首行
        first_line = next(
            (l.strip() for l in text.splitlines() if l.strip()), "")
        summary = " ".join([
            fm.get("title", name),
            first_line.lstrip("#").strip()[:80],
        ])[:160]
        store.save_node(
            node_id=f"vault:{name}", node_type="document",
            domain="vault_docs",
            data={"title": fm.get("title", name), "tags": fm.get("tags", ""),
                  "source": fm.get("source", ""), "is_index": "INDEX" in name
                  or "MOC" in name},
            summary=summary, tier="H")
        nodes += 1
        for target in links:
            clean_target = target.split("#")[0].strip()
            if os.path.exists(os.path.join(VAULT, clean_target + ".md")):
                store.save_edge(
                    edge_type="wikilink", domain="vault_docs",
                    source_id=f"vault:{name}", target_id=f"vault:{clean_target}",
                    data={"source_kind": "extracted"}, weight=0.9)
                edges += 1
            elif clean_target in docs_map:
                # 跨库: vault → docs 文件（双向语义: docs 是源, vault 是索引）
                store.save_node(
                    node_id=f"doc:{docs_map[clean_target]}",
                    node_type="document", domain="vault_docs",
                    data={"title": clean_target, "source": docs_map[clean_target]},
                    summary=clean_target, tier="W")
                store.save_edge(
                    edge_type="cross_ref", domain="vault_docs",
                    source_id=f"vault:{name}",
                    target_id=f"doc:{docs_map[clean_target]}",
                    data={"source_kind": "extracted"}, weight=0.8)
                cross_edges += 1
            else:
                unresolved.add(target)
    # 隐式关系核验结果重放（2026-08-11）: delete_domain 重建后补 verified 边
    verify_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "test", "IMPLICIT_EDGE_VERIFY_20260811.json")
    if os.path.exists(verify_path):
        import json as _json
        vdata = _json.load(open(verify_path, encoding="utf-8"))
        for r in vdata.get("results", []):
            if not r.get("is_relation"):
                continue
            store.save_edge(
                edge_type="inferred", domain="vault_docs",
                source_id=f"vault:{r['source']}",
                target_id=f"vault:{r['target']}",
                data={"source_kind": "inferred_verified",
                      "rel_type": r.get("rel_type", ""),
                      "similarity": r.get("similarity")},
                weight=0.6)
            verified_count += 1
    store.close()
    print("vault 文档: %d | 节点: %d | 双链边: %d | 跨库边: %d | verified: %d | 未解析: %d" % (
        len(files), nodes, edges, cross_edges, verified_count, len(unresolved)))
    if unresolved:
        print("未解析目标示例:", sorted(unresolved)[:10])


if __name__ == "__main__":
    main()
