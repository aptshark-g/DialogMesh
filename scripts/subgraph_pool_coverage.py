#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C 最小版量化 — 文件命中候选池扩展对子图可及性的提升（2026-08-14）。

原理: 文件命中 → 该文件节块进 pool_extras（不抬排序, 只扩候选）→
子图编译消费 pool_extras 作为额外锚点。量化: 期望块不在 fused top-20
（检索缺口）时, 是否通过 pool_extras 变得"子图可及"。

用法: DM_FILE_POOL=1 .venv\\Scripts\\python.exe scripts/subgraph_pool_coverage.py
输出: docs/test/SUBGRAPH_POOL_COVERAGE_YYYYMMDD.md
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set
from scripts.recall_goldset import build_service
import scripts.doc_recall_bench as drb


def main():
    queries = load_query_set("docs/test/recall_queries_100.md")
    blocks = drb.load_blocks()
    print("doc blocks:", len(blocks), flush=True)
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    n = n_gap = n_pool_rescue = n_gap_without_pool = 0
    rows = []
    for qi in queries:
        exp_files = qi["expected"]
        if not exp_files or exp_files[0].startswith("goldset:"):
            continue
        exp = set()
        for e in exp_files:
            e = e.strip()
            if not e:
                continue
            if e in file_to_ids:
                exp |= file_to_ids[e]
            else:
                exp.add(e)
        res = svc.recall(qi["query"],
                         intent=qi.get("intent") or "记忆召回",
                         top_k=20, use_hyde=False)
        in_hits = any(h.id in exp for h in res.hits)
        in_pool = any(h.id in exp for h in res.pool_extras)
        n += 1
        if not in_hits:
            n_gap += 1
            if in_pool:
                n_pool_rescue += 1
            rows.append((qi["query"][:40], in_pool))
    out = [
        "# 子图候选池覆盖（C 最小版, %s）" % time.strftime("%Y-%m-%d"), "",
        f"- 运行: {n} 条 doc 查询 | fused top-20 缺口: {n_gap}",
        f"- **pool_extras 救回（缺口 → 子图可及）: {n_pool_rescue}",
        f"  ({100.0*n_pool_rescue/max(n_gap,1):.0f}% of 缺口)**",
        "- 说明: pool_extras 只扩候选不抬排序（消融结论）; 子图编译",
        "  消费 pool_extras 作为额外锚点, 执行层可经路径精确查阅。", "",
        "## 缺口明细（是否被 pool 救回）", "",
    ]
    for q, ok in rows:
        out.append(f"- {'✅ 救回' if ok else '❌ 仍缺'} | {q}")
    report = "\n".join(out)
    path = "docs/test/SUBGRAPH_POOL_COVERAGE_%s.md" % time.strftime("%Y%m%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
