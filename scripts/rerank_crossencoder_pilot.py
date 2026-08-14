#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""cross-encoder 精排试点 — bge-reranker-v2-m3（2026-08-14）。

设计口径: 生产 RAG 共识的两级级联 — 粗召回（现状融合）→ cross-encoder
精排（query+候选联合打分, 排序层替换）。与 LLM 单选试点对比:
LLM 是"生成式模型凭直觉选", cross-encoder 是"为相关性任务训练的
判别式模型打分" — 预期后者更稳（业界标准做法）。

指标（与 eval_100 同口径 + 口径分离）:
  - 严格: top1 块 ∈ 期望块集
  - 文件级: top1 块的 doc ∈ 期望文档集（区分"挑对文件挑错块"）
  - 与 fused top1 / LLM 单选试点逐条对比

用法: .venv\\Scripts\\python.exe scripts/rerank_crossencoder_pilot.py
输出: docs/test/RERANK_CROSSENCODER_PILOT_YYYYMMDD.md
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set
from scripts.recall_goldset import build_service
import scripts.doc_recall_bench as drb

MODEL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "models", "bge-reranker-v2-m3")


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
    print("loading CrossEncoder:", MODEL, flush=True)
    t0 = time.time()
    ce = CrossEncoder(MODEL, max_length=1024, device="cuda")
    print("model loaded %.1fs" % (time.time() - t0), flush=True)

    rows = []
    stats = {"n": 0, "fused": 0, "ce": 0, "fused_file": 0, "ce_file": 0,
             "rrf": 0, "mrr_fused": 0.0, "mrr_ce": 0.0, "mrr_rrf": 0.0}
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
        res = svc.recall(qi["query"], intent=intent, top_k=15,
                         use_hyde=False)
        hits = res.hits[:15]
        # fused 判定
        f_rank = next((i + 1 for i, h in enumerate(hits) if h.id in exp), None)
        f_file_rank = next(
            (i + 1 for i, h in enumerate(hits)
             if h.path and h.path[0] in exp_files), None)
        # cross-encoder 打分（小块文本 + parent_context, 与返回层同口径）
        pairs = [(qi["query"], ((h.text or "")[:400] + " " +
                                (h.parent_context or "")[:200]))
                 for h in hits]
        t0 = time.time()
        scores = ce.predict(pairs, batch_size=16)
        dt = (time.time() - t0) * 1000
        t_ce.append(dt)
        order = sorted(range(len(scores)), key=lambda i: scores[i],
                       reverse=True)
        # 多信号精排: RRF(fused 排序, CE 排序) — 后期融合, 不替换任何信号
        rrf_score = {}
        for pos, h in enumerate(hits, 1):
            rrf_score[h.id] = 1.0 / (60 + pos)   # fused 贡献
        for pos, idx in enumerate(order, 1):
            h = hits[idx]
            rrf_score[h.id] = rrf_score.get(h.id, 0.0) + 1.0 / (60 + pos)
        rrf_order = sorted(hits, key=lambda h: rrf_score[h.id], reverse=True)
        rrf_rank = next((i + 1 for i, h in enumerate(rrf_order)
                         if h.id in exp), None)
        ce_rank = None
        ce_file_rank = None
        for pos, idx in enumerate(order, 1):
            h = hits[idx]
            if ce_rank is None and h.id in exp:
                ce_rank = pos
            if ce_file_rank is None and h.path and h.path[0] in exp_files:
                ce_file_rank = pos
            if ce_rank is not None and ce_file_rank is not None:
                break
        stats["n"] += 1
        stats["fused"] += f_rank == 1
        stats["ce"] += ce_rank == 1
        stats["rrf"] += rrf_rank == 1
        stats["fused_file"] += f_file_rank == 1
        stats["ce_file"] += ce_file_rank == 1
        if f_rank:
            stats["mrr_fused"] += 1.0 / f_rank
        if ce_rank:
            stats["mrr_ce"] += 1.0 / ce_rank
        if rrf_rank:
            stats["mrr_rrf"] += 1.0 / rrf_rank
        rows.append({
            "query": qi["query"][:42], "f_rank": f_rank,
            "ce_rank": ce_rank, "f_file": f_file_rank,
            "ce_file": ce_file_rank, "rrf_rank": rrf_rank,
            "top1_src": hits[0].source if hits else "-",
        })
        print(f"[{stats['n']}] fused={f_rank} ce={ce_rank} rrf={rrf_rank} "
              f"file: {f_file_rank}/{ce_file_rank} {dt:.0f}ms | "
              f"{qi['query'][:30]}", flush=True)

    n = stats["n"]
    out = [
        "# cross-encoder 精排试点 — doc 域（%s）" % time.strftime("%Y-%m-%d"),
        "",
        f"- 模型: {MODEL} (CrossEncoder, 判别式相关性打分)",
        f"- 粗召回: 融合 top-15（与 LLM 试点同口径）",
        f"- 总耗时: {sum(t_ce)/1000:.0f}s | 平均打分: "
        f"{sum(t_ce)/max(len(t_ce),1):.0f} ms/query", "",
        "## 汇总", "",
        f"- 运行: {n} 条 doc 查询",
        f"- fused top1: {stats['fused']}/{n} "
        f"({100.0*stats['fused']/n:.1f}%)",
        f"- **CE top1: {stats['ce']}/{n} "
        f"({100.0*stats['ce']/n:.1f}%)**",
        f"- **RRF(fused+CE) top1: {stats['rrf']}/{n} "
        f"({100.0*stats['rrf']/n:.1f}%)** — 多信号后期融合, 不替换",
        f"- fused 文件级 top1: {stats['fused_file']}/{n} "
        f"({100.0*stats['fused_file']/n:.1f}%)",
        f"- CE 文件级 top1: {stats['ce_file']}/{n} "
        f"({100.0*stats['ce_file']/n:.1f}%)",
        f"- MRR@15 fused: {stats['mrr_fused']/n:.3f} | CE: "
        f"{stats['mrr_ce']/n:.3f} | RRF: {stats['mrr_rrf']/n:.3f}", "",
        "## 逐条", "",
    ]
    for r in rows:
        out.append(
            f"- fused_rank={r['f_rank']} ce_rank={r['ce_rank']} "
            f"rrf_rank={r['rrf_rank']} file={r['f_file']}/{r['ce_file']} "
            f"[{r['top1_src']}] | "
            f"{r['query']}")
    report = "\n".join(out)
    path = "docs/test/RERANK_CROSSENCODER_PILOT_%s.md" % time.strftime("%Y%m%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + "\n".join(out[:16]))
    print("\nwritten:", path)


if __name__ == "__main__":
    main()
