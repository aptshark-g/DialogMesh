#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统一评测 100 条（2026-08-11, 无 LLM 全指标, 一次跑完）。

数据: docs/test/recall_queries_100.md（39 对话 + 61 文档）
指标（纯本地）: top1/3/5、MRR、nDCG、Recall@5/10/20、Context Precision、
每 query 耗时。输出 docs/test/EVAL_100_20260811.md。
用法: .venv\\Scripts\\python.exe scripts/eval_100.py
"""
from __future__ import annotations

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set


def _mrr_ndcg(hits, expected, top_k):
    exp = set(expected)
    mrr = 0.0
    rel = []
    for i, h in enumerate(hits[:top_k], 1):
        r = 1.0 if h in exp else 0.0
        rel.append(r)
        if r and mrr == 0.0:
            mrr = 1.0 / i
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
    ideal = sorted(rel, reverse=True)
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    return mrr, (dcg / idcg if idcg else 0.0)


def main():
    from collections import Counter
    from scripts.recall_goldset import load_goldset, build_service
    import scripts.doc_recall_bench as drb

    queries = load_query_set("docs/test/recall_queries_100.md")
    gold = load_goldset()
    gold_blocks = {b["id"]: b for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="vector_primary")
    doc_blocks = drb.load_blocks()
    print("文档块: %d" % len(doc_blocks))
    # 批量编码 + 磁盘缓存（2026-08-11: 首次 GPU/批量 embed, 二次秒级）
    drb.prepare_vectors(doc_blocks)
    # 文件级 expected → 节级块 id 展开（2026-08-12）: 评测集 expected 写的是
    # 文件路径, 块池是 file#heading 节级块; 精确匹配恒 0 → 按 doc 字段展开,
    # 命中该文件任一节块即算命中。
    file_to_ids = {}
    for b in doc_blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    # 文档域用同一个 service（向量懒计算, 块池换文档块）
    doc_service = build_service(doc_blocks, mode="vector_primary")

    stats = {"dialogue": {"n": 0, "top1": 0, "top3": 0, "top5": 0,
                          "mrr": 0.0, "ndcg": 0.0, "cp": 0.0,
                          "r5": 0, "r10": 0, "r20": 0, "time_ms": 0.0},
             "doc": dict.fromkeys(["n", "top1", "top3", "top5", "mrr",
                                   "ndcg", "cp", "r5", "r10", "r20",
                                   "time_ms"], 0.0)}
    # 诊断明细（2026-08-12）: 融合排名 / 各路线最佳排名 / 耗时 / 分类 /
    # top1 块来源。目的: 一次跑完即知"为什么高/低/快/慢"。
    rows = []
    t_total = time.time()
    for qi in queries:
        exp_files = qi["expected"]
        # 2026-08-12 修复: load_query_set 已把 ";" 拆成列表 —
        # 此前只取 [0] 导致多文件期望行只评估第一个文件。
        if exp_files and exp_files[0].startswith("goldset:"):
            exp = exp_files[0].split(":", 1)[1].split(",")
            svc_use, tag = svc, "dialogue"
        else:
            exp = []
            for e in exp_files:
                e = e.strip()
                if not e:
                    continue
                if e in file_to_ids:
                    exp.extend(sorted(file_to_ids[e]))
                else:
                    exp.append(e)
            svc_use, tag = doc_service, "doc"
        s = stats[tag]
        s["n"] += 1
        t0 = time.time()
        res = svc_use.recall(qi["query"], top_k=20, use_hyde=False)
        s["time_ms"] += (time.time() - t0) * 1000
        ids = [h.id for h in res.hits]
        exp_set = set(exp)
        hit = [i + 1 for i, x in enumerate(ids[:20]) if x in exp_set]
        if hit:
            r = hit[0]
            if r == 1:
                s["top1"] += 1
            if r <= 3:
                s["top3"] += 1
            if r <= 5:
                s["top5"] += 1
            if r <= 5:
                s["r5"] += 1
            if r <= 10:
                s["r10"] += 1
            if r <= 20:
                s["r20"] += 1
        mrr, ndcg = _mrr_ndcg(ids, exp_set, 5)
        s["mrr"] += mrr
        s["ndcg"] += ndcg
        # ── 诊断采集 ────────────────────────────────────────────
        detail = {
            "query": qi["query"], "tag": tag, "fused_rank": None,
            "routes": {}, "top1_source": None, "cls": "A",
        }
        if hit:
            detail["fused_rank"] = hit[0]
        for src, fn in (("vector", svc_use._vector_anchors),
                        ("bm25", svc_use._bm25_anchors),
                        ("spo", svc_use._spo_anchors)):
            t0 = time.time()
            hs = fn(qi["query"], 20)
            dt = (time.time() - t0) * 1000
            best = next(
                (i for i, h in enumerate(hs, 1) if h.id in exp_set), None)
            detail["routes"][src] = {"best": best, "ms": round(dt, 1)}
        if detail["fused_rank"] is None:
            detail["cls"] = ("B" if any(
                r["best"] is not None for r in detail["routes"].values())
                else "C")
        if res.hits:
            detail["top1_source"] = res.hits[0].source
        rows.append(detail)
        # CP: 加权位置（分母=相关项数）
        relevant = 0
        num = 0.0
        for k, x in enumerate(ids[:5], 1):
            if x in exp_set:
                relevant += 1
                tp = sum(1 for j, y in enumerate(ids[:k], 1) if y in exp_set)
                num += tp / k
        s["cp"] += num / relevant if relevant else 0.0

    out = ["# 统一评测 100 条 — 无 LLM 全指标（2026-08-11）", "",
           f"- 数据: docs/test/recall_queries_100.md（100 条）",
           f"- 总耗时: {time.time() - t_total:.0f}s", ""]
    for tag, s in stats.items():
        n = s["n"] or 1
        out += ["## %s 域（%d 条）" % (tag, s["n"]), "",
                f"- top1: {s['top1']}/{s['n']} ({100.0*s['top1']/n:.1f}%)",
                f"- top3: {100.0*s['top3']/n:.1f}% | top5: {100.0*s['top5']/n:.1f}%",
                f"- MRR@5: {s['mrr']/n:.3f} | nDCG@5: {s['ndcg']/n:.3f}",
                f"- Recall@5: {100.0*s['r5']/n:.1f}% | @10: {100.0*s['r10']/n:.1f}% | @20: {100.0*s['r20']/n:.1f}%",
                f"- Context Precision@5: {s['cp']/n:.3f}",
                f"- 平均耗时: {s['time_ms']/n:.0f} ms/query", ""]
    # ── 诊断汇总（为什么）────────────────────────────────────────
    by_cls = Counter(r["cls"] for r in rows)
    fused_top1 = [r for r in rows if r["fused_rank"] == 1]
    win_src = Counter(r["top1_source"] or "?" for r in fused_top1)
    route_lead1 = Counter()
    route_best_any = Counter()
    route_ms = Counter()
    route_ms_n = Counter()
    for r in rows:
        for src, v in r["routes"].items():
            if v["best"] == 1:
                route_lead1[src] += 1
            if v["best"] is not None:
                route_best_any[src] += 1
            route_ms[src] += v["ms"]
            route_ms_n[src] += 1
    near_miss = sum(1 for r in rows
                    if r["fused_rank"] is not None and r["fused_rank"] > 1)
    out += [
        "## 诊断汇总（为什么）", "",
        f"- 分类: A(融合命中)={by_cls['A']}  B(路线内被融合挤出)="
        f"{by_cls['B']}  C(检索缺口)={by_cls['C']}",
        f"- top1 命中块的来源: {dict(win_src)}",
        f"- 期望块在单路线排第 1 的 query 数: {dict(route_lead1)}",
        f"- 期望块进入某路线 top-20 的 query 数: {dict(route_best_any)}",
        f"- 融合命中但非 top1（排序竞争）: {near_miss}",
        f"- 各路线平均耗时 ms/query: "
        f"{ {k: round(route_ms[k] / route_ms_n[k], 1) for k in route_ms} }",
        "",
        "## 逐条明细", "",
    ]
    for r in rows:
        out.append(
            "- [%s] fused=%s vec=%s bm25=%s spo=%s | vec%.0fms bm25%.0fms "
            "spo%.0fms | top1源=%s | %s" % (
                r["cls"], r["fused_rank"],
                r["routes"]["vector"]["best"],
                r["routes"]["bm25"]["best"],
                r["routes"]["spo"]["best"],
                r["routes"]["vector"]["ms"],
                r["routes"]["bm25"]["ms"],
                r["routes"]["spo"]["ms"],
                r["top1_source"] or "-", r["query"][:44]))
    with open("docs/test/EVAL_100_20260811.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    with open("docs/test/EVAL_100_DETAIL_20260812.md", "w",
              encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
