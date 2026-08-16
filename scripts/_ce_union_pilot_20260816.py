#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""路线并集 + CE 精排试点（2026-08-16）:

候选池 = vector top-20 ∪ bm25 top-20 ∪ spo top-20（每路各取 20, 去重,
不被 vector_primary 埋掉）→ CrossEncoder 判别式打分 → 直接排序。
验证: 池内包含 B 类期望块后, CE 能否把它们判到 top1（对比 fused）。
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.query_set import load_query_set  # noqa: E402
from scripts.recall_goldset import build_service  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402

MODEL = os.path.join(ROOT, "models", "bge-reranker-v2-m3")


def main():
    queries = load_query_set("docs/test/recall_queries_100.md")
    blocks = drb.load_blocks()
    print("doc blocks:", len(blocks), flush=True)
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    byid = {b["id"]: b for b in blocks}
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    from sentence_transformers import CrossEncoder
    print("loading CrossEncoder...", flush=True)
    t0 = time.time()
    ce = CrossEncoder(MODEL, max_length=1024, device="cuda")
    print("model loaded %.1fs" % (time.time() - t0), flush=True)

    rows = []
    stats = {"n": 0, "base": 0, "ce": 0}
    t_ce = []
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
        intent = qi.get("intent") or "记忆召回"
        res = svc.recall(qi["query"], intent=intent, top_k=20,
                         use_hyde=False)
        base_rank = next(
            (i + 1 for i, h in enumerate(res.hits) if h.id in exp), None)
        pool = {}
        for h in res.hits:
            pool.setdefault(h.id, h)
        for fn in (svc._vector_anchors, svc._bm25_anchors,
                   svc._spo_anchors):
            for h in fn(qi["query"], 20):
                pool.setdefault(h.id, h)
        cands = list(pool.values())
        pairs = [(
            qi["query"],
            ((h.full_text or h.text or "")[:800] + " " +
             (h.parent_context or "")[:200])) for h in cands]
        t0 = time.time()
        scores = ce.predict(pairs, batch_size=32)
        dt = (time.time() - t0) * 1000
        t_ce.append(dt)
        order = sorted(range(len(scores)), key=lambda i: scores[i],
                       reverse=True)
        ce_rank = next(
            (i + 1 for i, idx in enumerate(order)
             if cands[idx].id in exp), None)
        stats["n"] += 1
        stats["base"] += base_rank == 1
        stats["ce"] += ce_rank == 1
        rows.append((qi["query"], base_rank, ce_rank, len(cands)))
        print("[%d/%d] base=%-4s ce=%-4s pool=%d %s" % (
            stats["n"], 61, base_rank, ce_rank, len(cands),
            qi["query"][:32]), flush=True)
    n = stats["n"]
    print()
    print("==== route-union + CE ====")
    print("base top1: %d/%d (%.1f%%)" % (
        stats["base"], n, 100.0 * stats["base"] / n))
    print("CE  top1: %d/%d (%.1f%%)" % (
        stats["ce"], n, 100.0 * stats["ce"] / n))
    print("CE 平均: %.0f ms/query" % (sum(t_ce) / max(len(t_ce), 1)))
    out = ["# 路线并集 + CE 精排试点（2026-08-16）", "",
           f"- base top1: {stats['base']}/{n} "
           f"({100.0*stats['base']/n:.1f}%)",
           f"- **CE top1: {stats['ce']}/{n} "
           f"({100.0*stats['ce']/n:.1f}%)**",
           f"- CE 平均: {sum(t_ce)/max(len(t_ce),1):.0f} ms/query", "",
           "## 逐条（base → ce, pool=候选数）", ""]
    for q, b, c, p in rows:
        out.append(f"- base={b} ce={c} pool={p} | {q}")
    path = os.path.join(ROOT, "scripts", "_ce_union_delta_20260816.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("written:", path)


if __name__ == "__main__":
    main()
