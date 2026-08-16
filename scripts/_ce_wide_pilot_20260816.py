#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""宽候选 CE 精排试点（2026-08-16）:

假设（RECALL_MAINSTREAM_GAP §四-3 "Rerank 正解"）: 旧 CE pilot 用 top-15
候选, B 类 miss 的期望块根本不在候选内 → CE 无救; 候选放宽到 top-60 后
期望块在池内, CE 判别式打分应能把它抬上来。

流程: 融合 top-60 → CrossEncoder(query, block) → RRF(fused, CE) 合并 →
top-20 判定。逐条打印 delta, 输出
scripts/_ce_wide_delta_20260816.md。
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
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    from sentence_transformers import CrossEncoder
    print("loading CrossEncoder...", flush=True)
    t0 = time.time()
    ce = CrossEncoder(MODEL, max_length=1024, device="cuda")
    print("model loaded %.1fs" % (time.time() - t0), flush=True)

    rows = []
    stats = {"n": 0, "base": 0, "ce": 0, "rrf": 0}
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
        res = svc.recall(qi["query"], intent=intent, top_k=60,
                         use_hyde=False)
        hits = res.hits[:60]
        base_rank = next(
            (i + 1 for i, h in enumerate(hits[:20]) if h.id in exp), None)
        pairs = [(
            qi["query"],
            ((h.full_text or h.text or "")[:800] + " " +
             (h.parent_context or "")[:200])) for h in hits]
        t0 = time.time()
        scores = ce.predict(pairs, batch_size=32)
        dt = (time.time() - t0) * 1000
        t_ce.append(dt)
        order = sorted(range(len(scores)), key=lambda i: scores[i],
                       reverse=True)
        ce_rank = next(
            (i + 1 for i, idx in enumerate(order)
             if hits[idx].id in exp), None)
        # RRF 合并（fused 序 + CE 序）
        rrf = {}
        for pos, h in enumerate(hits, 1):
            rrf[h.id] = 1.0 / (60 + pos)
        for pos, idx in enumerate(order, 1):
            rrf[hits[idx].id] = rrf.get(hits[idx].id, 0.0) + 1.0 / (60 + pos)
        rrf_order = sorted(hits, key=lambda h: rrf[h.id], reverse=True)
        rrf_rank = next(
            (i + 1 for i, h in enumerate(rrf_order[:20]) if h.id in exp),
            None)
        stats["n"] += 1
        stats["base"] += base_rank == 1
        stats["ce"] += ce_rank == 1
        stats["rrf"] += rrf_rank == 1
        rows.append((qi["query"], base_rank, ce_rank, rrf_rank))
        print("[%d] base=%-4s ce=%-4s rrf=%-4s %s" % (
            stats["n"], base_rank, ce_rank, rrf_rank,
            qi["query"][:36]), flush=True)
    n = stats["n"]
    out = ["# 宽候选 CE 精排试点（top-60, 2026-08-16）", "",
           f"- 候选宽度: 融合 top-60（旧 pilot top-15）",
           f"- 合并: RRF(fused 序, CE 序) → top-20 判定",
           f"- CE 平均打分: {sum(t_ce)/max(len(t_ce),1):.0f} ms/query", "",
           f"- base top1: {stats['base']}/{n} "
           f"({100.0*stats['base']/n:.1f}%)",
           f"- CE 直排 top1: {stats['ce']}/{n} "
           f"({100.0*stats['ce']/n:.1f}%)",
           f"- **RRF(CE) top1: {stats['rrf']}/{n} "
           f"({100.0*stats['rrf']/n:.1f}%)**", "",
           "## 逐条（base → ce → rrf）", ""]
    for q, b, c, r in rows:
        out.append(f"- base={b} ce={c} rrf={r} | {q}")
    path = os.path.join(ROOT, "scripts", "_ce_wide_delta_20260816.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out[:12]))
    print("written:", path)


if __name__ == "__main__":
    main()
