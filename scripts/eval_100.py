#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统一评测 100 条（2026-08-11, 无 LLM 全指标, 一次跑完）。

数据: docs/test/recall_queries_100.md（39 对话 + 61 文档）
指标（纯本地）: top1/3/5、MRR、nDCG、Recall@5/10/20、Context Precision、
每 query 耗时。输出 docs/test/EVAL_100_YYYYMMDD.md（按运行日期）。

2026-08-13（P1 意图感知 + 重排）:
- 查询集新增第 6 列 intent（与 classify_intent 类别集对齐）→ recall 按
  意图选融合配置（W1 后半: INTENT_PROFILES per-intent 权重/模式）。
- --compare 模式: 同一进程内跑 DM_RERANK=0（旧排序）vs 1（重排层）,
  输出对比表 + 按意图细分（doc 域 top1 提升的施工面）。
用法: .venv\\Scripts\\python.exe scripts/eval_100.py [--compare]
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


def _run(rerank_on: bool):
    """跑一遍完整评测; rerank_on 控制重排层开关（进程内环境翻转）。"""
    from collections import Counter
    from scripts.recall_goldset import load_goldset, build_service
    import scripts.doc_recall_bench as drb

    # setdefault: 保留默认行为（rerank_on=True → ON）, 同时允许消融脚本
    # 预置 DM_RERANK=0 跑"重排 OFF"对照（A18 消融驱动, 2026-08-16）。
    os.environ.setdefault("DM_RERANK", "1" if rerank_on else "0")
    queries = load_query_set("docs/test/recall_queries_100.md")
    gold = load_goldset()
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="vector_primary")
    doc_blocks = drb.load_blocks()
    print("文档块: %d" % len(doc_blocks))
    # 批量编码 + 磁盘缓存（2026-08-11: 首次 GPU/批量 embed, 二次秒级）
    drb.prepare_vectors(doc_blocks)
    # 文件级 expected → 节级块 id 展开（2026-08-12）
    file_to_ids = {}
    for b in doc_blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    # 文档域用同一个 service（向量懒计算, 块池换文档块）
    doc_service = build_service(doc_blocks, mode="vector_primary")

    stats = {"dialogue": {"n": 0, "top1": 0, "top3": 0, "top5": 0,
                          "mrr": 0.0, "ndcg": 0.0, "cp": 0.0,
                          "r5": 0, "r10": 0, "r20": 0, "time_ms": 0.0,
                          "pc": 0},
             "doc": dict.fromkeys(["n", "top1", "top3", "top5", "mrr",
                                   "ndcg", "cp", "r5", "r10", "r20",
                                   "time_ms", "pc"], 0.0)}
    # 按意图细分（2026-08-13, W1 验收）: 每意图 top1/3/5 命中数
    by_intent = {}   # intent -> {"n", "top1", "top3", "top5"}
    rows = []
    t_total = time.time()
    for qi in queries:
        exp_files = qi["expected"]
        intent = qi.get("intent") or "记忆召回"
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
        it = by_intent.setdefault(
            intent, {"n": 0, "top1": 0, "top3": 0, "top5": 0})
        it["n"] += 1
        t0 = time.time()
        # W1（2026-08-13）: 意图传入 recall → 按意图选融合配置/重排权重
        res = svc_use.recall(qi["query"], intent=intent, top_k=20,
                             use_hyde=False)
        s["time_ms"] += (time.time() - t0) * 1000
        # 方案 B 返回层（2026-08-14）: 锚点附带父文件摘要的覆盖数
        s["pc"] += sum(1 for h in res.hits[:5] if h.parent_context)
        ids = [h.id for h in res.hits]
        exp_set = set(exp)
        hit = [i + 1 for i, x in enumerate(ids[:20]) if x in exp_set]
        if hit:
            r = hit[0]
            if r == 1:
                s["top1"] += 1
                it["top1"] += 1
            if r <= 3:
                s["top3"] += 1
                it["top3"] += 1
            if r <= 5:
                s["top5"] += 1
                it["top5"] += 1
            if r <= 5:
                s["r5"] += 1
            if r <= 10:
                s["r10"] += 1
            if r <= 20:
                s["r20"] += 1
        mrr, ndcg = _mrr_ndcg(ids, exp_set, 5)
        s["mrr"] += mrr
        s["ndcg"] += ndcg
        detail = {
            "query": qi["query"], "tag": tag, "intent": intent,
            "fused_rank": None, "routes": {}, "top1_source": None,
            "cls": "A",
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
        relevant = 0
        num = 0.0
        for k, x in enumerate(ids[:5], 1):
            if x in exp_set:
                relevant += 1
                tp = sum(1 for j, y in enumerate(ids[:k], 1) if y in exp_set)
                num += tp / k
        s["cp"] += num / relevant if relevant else 0.0

    out = ["# 统一评测 100 条 — 意图感知 + 重排对比（%s）"
           % time.strftime("%Y-%m-%d"), "",
           f"- 数据: docs/test/recall_queries_100.md（100 条, 含 intent 列）",
           f"- 重排层: {'ON' if rerank_on else 'OFF（旧排序基线）'}",
           f"- 总耗时: {time.time() - t_total:.0f}s", ""]
    for tag, s in stats.items():
        n = s["n"] or 1
        out += ["## %s 域（%d 条）" % (tag, s["n"]), "",
                f"- top1: {s['top1']}/{s['n']} ({100.0*s['top1']/n:.1f}%)",
                f"- top3: {100.0*s['top3']/n:.1f}% | top5: {100.0*s['top5']/n:.1f}%",
                f"- MRR@5: {s['mrr']/n:.3f} | nDCG@5: {s['ndcg']/n:.3f}",
                f"- Recall@5: {100.0*s['r5']/n:.1f}% | @10: {100.0*s['r10']/n:.1f}% | @20: {100.0*s['r20']/n:.1f}%",
                f"- Context Precision@5: {s['cp']/n:.3f}",
                f"- 返回层 parent_context 覆盖: {s['pc']}/{s['n']*5} 个 top5 锚点带文件摘要",
                f"- 平均耗时: {s['time_ms']/n:.0f} ms/query", ""]
    out += ["## 按意图细分（W1 验收）", ""]
    for intent, it in sorted(by_intent.items()):
        n = it["n"] or 1
        out.append(
            f"- {intent}: n={it['n']}  top1={100.0*it['top1']/n:.1f}%  "
            f"top3={100.0*it['top3']/n:.1f}%  top5={100.0*it['top5']/n:.1f}%")
    out += ["", "## 诊断汇总（为什么）", ""]
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
            "- [%s/%s] fused=%s vec=%s bm25=%s spo=%s | vec%.0fms bm25%.0fms "
            "spo%.0fms | top1源=%s | %s" % (
                r["cls"], r["intent"], r["fused_rank"],
                r["routes"]["vector"]["best"],
                r["routes"]["bm25"]["best"],
                r["routes"]["spo"]["best"],
                r["routes"]["vector"]["ms"],
                r["routes"]["bm25"]["ms"],
                r["routes"]["spo"]["ms"],
                r["top1_source"] or "-", r["query"][:44]))
    return stats, by_intent, out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true",
                    help="同进程跑 rerank OFF/ON 两次并输出对比表")
    args = ap.parse_args()
    if not args.compare:
        _, _, out = _run(rerank_on=True)
        with open("docs/test/EVAL_100_%s.md" % time.strftime("%Y%m%d"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(out))
        print("\n".join(out))
        return
    off_stats, off_intent, off_lines = _run(rerank_on=False)
    on_stats, on_intent, on_lines = _run(rerank_on=True)
    head = ["# eval_100 — 重排层消融对比（2026-08-13）", "",
            "| 域 | 指标 | 旧排序(OFF) | 重排(ON) | Δ |", "|---|---|---|---|---|"]
    for tag in ("dialogue", "doc"):
        for metric, key in (("top1", "top1"), ("top3", "top3"),
                            ("MRR@5", "mrr"), ("nDCG@5", "ndcg")):
            a = off_stats[tag][key] / (off_stats[tag]["n"] or 1)
            b = on_stats[tag][key] / (on_stats[tag]["n"] or 1)
            if metric in ("MRR@5", "nDCG@5"):
                head.append(f"| {tag} | {metric} | {a:.3f} | {b:.3f} | {b-a:+.3f} |")
            else:
                head.append(
                    f"| {tag} | {metric} | {100*a:.1f}% | {100*b:.1f}% | "
                    f"{100*(b-a):+.1f}pp |")
    head += ["", "### 按意图 top1（OFF → ON）", ""]
    for intent in sorted(set(off_intent) | set(on_intent)):
        a = off_intent.get(intent, {"n": 0, "top1": 0})
        b = on_intent.get(intent, {"n": 0, "top1": 0})
        an = a["n"] or 1
        bn = b["n"] or 1
        head.append(
            f"- {intent}: {100.0*a['top1']/an:.1f}% → "
            f"{100.0*b['top1']/bn:.1f}% （n={b['n']}）")
    full = head + ["", "---", "", "## OFF 明细"] + off_lines[off_lines.index("## 逐条明细"):]
    full += ["", "---", "", "## ON 明细"] + on_lines[on_lines.index("## 逐条明细"):]
    with open("docs/test/EVAL_100_RERANK_COMPARE_%s.md"
              % time.strftime("%Y%m%d"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(full))
    print("\n".join(head))


if __name__ == "__main__":
    main()
