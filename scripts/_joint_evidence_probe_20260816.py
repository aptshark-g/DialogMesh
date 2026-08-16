#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""联合证据分离性探查（2026-08-16）:

对 B 类 miss 的期望块与 route_unique 假阳性块, 打印各自在 vector 路线
的 rank（1-100 内）, 验证"bm25 rank1 + vector rank 21-60"是否能把
真命中与假阳性分开（混合信号 = A25 多信号交叉的精确形态）。
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.query_set import load_query_set  # noqa: E402
from scripts.recall_goldset import build_service  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    queries = load_query_set("docs/test/recall_queries_100.md")
    targets = ("agentic 工具节点", "决策事件有哪些", "执行迹和变更日志",
               "隐式关系候选", "v2.1 召回桥")
    for qi in queries:
        if not any(t in qi["query"] for t in targets):
            continue
        exp_files = qi["expected"]
        exp = set()
        for e in exp_files:
            e = e.strip()
            if not e:
                continue
            if e in file_to_ids:
                exp |= file_to_ids[e]
            else:
                exp.add(e)
        print("=" * 78)
        print("[%s]" % qi["query"])
        bm = svc._bm25_anchors(qi["query"], 10)
        vec_all = svc._vector_anchors(qi["query"], 100)
        vec_rank = {h.id: i + 1 for i, h in enumerate(vec_all)}
        for i, h in enumerate(bm[:6], 1):
            vr = vec_rank.get(h.id)
            tag = "EXP" if h.id in exp else "   "
            print("  bm25#%d score=%.3f vec_rank=%-4s %s %s" % (
                i, h.score, vr if vr else "-", tag, h.id[:58]))


if __name__ == "__main__":
    main()
