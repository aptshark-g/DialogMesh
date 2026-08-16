#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""doc 域 miss 逐条诊断（2026-08-16）: 6 条 B/C 类 + 全部 A 类 rank>1。

对每条 query 打印: 融合 top-20（id/源/分）、各路线期望块 rank 与分数、
期望块文本片段。跑完落盘 scripts/_doc_miss_dump_20260816.md。
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["DM_RERANK"] = "1"

from scripts.query_set import load_query_set  # noqa: E402
from scripts.recall_goldset import load_goldset, build_service  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402


def main():
    queries = load_query_set("docs/test/recall_queries_100.md")
    gold = load_goldset()
    _ = gold  # 对话域不用
    doc_blocks = drb.load_blocks()
    print("文档块: %d" % len(doc_blocks))
    drb.prepare_vectors(doc_blocks)
    doc_service = build_service(doc_blocks, mode="vector_primary")
    file_to_ids = {}
    for b in doc_blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    byid = {b["id"]: b for b in doc_blocks}

    lines: list[str] = []
    lines.append("# doc 域 miss 诊断（2026-08-16）")
    lines.append("")
    miss_top1 = 0
    miss_any = 0
    for qi in queries:
        exp_files = qi["expected"]
        if exp_files and exp_files[0].startswith("goldset:"):
            continue  # 只分析 doc 域
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
        res = doc_service.recall(qi["query"], intent=qi.get("intent"),
                                 top_k=20, use_hyde=False)
        ids = [h.id for h in res.hits]
        hit = [i + 1 for i, x in enumerate(ids) if x in exp_set]
        if not hit:
            miss_any += 1
        elif hit[0] > 1:
            miss_top1 += 1
        else:
            continue
        lines.append("## %s" % qi["query"])
        lines.append("- expected: %s" % exp_files)
        lines.append("- fused rank: %s" % (hit[0] if hit else "MISS"))
        lines.append("")
        lines.append("### 融合 top-20")
        for i, h in enumerate(res.hits[:20], 1):
            mark = " <==" if h.id in exp_set else ""
            lines.append(
                "%2d  %-12s score=%.4f rerank=%.4f src=%s%s" % (
                    i, h.id[:16], h.score, h.rerank_score,
                    h.source, mark))
        lines.append("")
        lines.append("### 各路线期望块")
        for src, fn in (("vector", doc_service._vector_anchors),
                        ("bm25", doc_service._bm25_anchors),
                        ("spo", doc_service._spo_anchors)):
            hs = fn(qi["query"], 20)
            best = next((i for i, h in enumerate(hs, 1)
                         if h.id in exp_set), None)
            info = ""
            if best is not None:
                h = hs[best - 1]
                info = "rank=%d score=%.4f" % (best, h.score)
            lines.append("- %-6s %s" % (src, info))
        lines.append("")
        lines.append("### 期望块文本")
        for eid in sorted(exp_set):
            b = byid.get(eid)
            if b:
                lines.append("- %s: %s" % (eid[:16],
                                           (b.get("text") or "")[:220].replace(
                                               "\n", " ")))
        lines.append("")
    lines.insert(2, "miss top1=%d  miss all=%d" % (miss_top1, miss_any))
    out_path = os.path.join(ROOT, "scripts",
                            "_doc_miss_dump_20260816.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("written:", out_path)
    print("miss top1=%d miss all=%d" % (miss_top1, miss_any))


if __name__ == "__main__":
    main()
