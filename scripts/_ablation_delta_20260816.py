#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对比 baseline vs route_unique 的逐 query 变化（2026-08-16）。

打印: 融合 rank 变化的 doc 查询（升/降/新增命中）, 定位回归机制。
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


def _ranks(route_unique: bool):
    if route_unique:
        os.environ["DM_ROUTE_UNIQUE"] = "1"
    else:
        os.environ.pop("DM_ROUTE_UNIQUE", None)
    os.environ["DM_RERANK"] = "1"
    doc_blocks = drb.load_blocks()
    drb.prepare_vectors(doc_blocks)
    svc = build_service(doc_blocks, mode="vector_primary")
    file_to_ids = {}
    for b in doc_blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    queries = load_query_set("docs/test/recall_queries_100.md")
    out = {}
    for qi in queries:
        exp_files = qi["expected"]
        if exp_files and exp_files[0].startswith("goldset:"):
            continue
        exp = []
        for e in exp_files:
            e = e.strip()
            if not e:
                continue
            if e in file_to_ids:
                exp.extend(sorted(file_to_ids[e]))
            else:
                exp.append(e)
        exp_set = set(exp)
        res = svc.recall(qi["query"], intent=qi.get("intent"),
                         top_k=20, use_hyde=False)
        ids = [h.id for h in res.hits]
        hit = next((i + 1 for i, x in enumerate(ids) if x in exp_set), None)
        out[qi["query"]] = hit
    return out


def main():
    base = _ranks(False)
    ru = _ranks(True)
    print("== 变化明细 ==")
    for q in sorted(base):
        a, b = base[q], ru[q]
        if a != b:
            print("%-44s base=%-4s route_unique=%-4s" % (
                q[:44], a, b))


if __name__ == "__main__":
    main()
