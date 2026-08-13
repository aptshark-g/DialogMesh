#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""层3 变体评测 — 原查询 vs LLM 变体（同义/英文/口语化）鲁棒性对比。

复用 doc_recall_bench 的语料/服务/评估逻辑, 只换查询集:
  - 原查询集: docs/test/recall_queries.json (50)
  - 变体查询集: docs/test/recall_queries_variants.json (150 = 50x3)
对比指标: top1/top3/top5/MRR, 按变体类型分组。
"""
from __future__ import annotations
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from doc_recall_bench import (  # noqa: E402
    load_blocks, prepare_vectors, build_service, evaluate,
    load_external_queries, preindex_terms, coarse_candidates,
    FakeDiscourse, FakeBlock,
)

ORIG = os.path.join(ROOT, "docs", "test", "recall_queries.json")
VAR = os.path.join(ROOT, "docs", "test", "recall_queries_variants.json")

def main():
    print("[1/2] 构建语料 + 向量缓存...")
    blocks = load_blocks(0)
    prepare_vectors(blocks)
    top_c = int(os.environ.get("DM_TOP_C", "200"))
    if top_c > 0:
        preindex_terms(blocks)
    print(f"  语料: {len(blocks)} 块")

    print("[2/2] 跑分 (linear 融合, 全库扫描)...")
    svc = build_service(blocks, mode="linear", single=None)
    orig_qs = load_external_queries(ORIG)
    var_data = json.load(open(VAR, encoding="utf-8"))
    var_qs = [{
        "query": q["query"],
        "expected_docs": set(q.get("expected") or []),
        "level": q.get("level", "simple"),
        "variant_type": q.get("variant_type", "?"),
    } for q in var_data["queries"]]

    r_orig = evaluate(svc, orig_qs, top_k=5, blocks=blocks, top_c=top_c)
    print(f"  原查询: top1={r_orig['top1']}/{r_orig['total']} "
          f"({100.0*r_orig['top1']/max(r_orig['total'],1):.1f}%) "
          f"top3={r_orig['top3']} top5={r_orig['top5']} MRR={r_orig['mrr']:.3f}")

    # 变体按类型分组
    by_type = {}
    for q in var_qs:
        by_type.setdefault(q["variant_type"], []).append(q)
    r_var = {}
    for vt, qs in by_type.items():
        r = evaluate(svc, qs, top_k=5, blocks=blocks, top_c=top_c)
        r_var[vt] = r
        print(f"  [{vt}] n={r['total']}: top1={r['top1']}/{r['total']} "
              f"({100.0*r['top1']/max(r['total'],1):.1f}%) "
              f"top3={r['top3']} top5={r['top5']} MRR={r['mrr']:.3f}")

    # 全部变体合并
    r_all = evaluate(svc, var_qs, top_k=5, blocks=blocks, top_c=top_c)
    print(f"  [all 变体] n={r_all['total']}: top1={r_all['top1']}/{r_all['total']} "
          f"({100.0*r_all['top1']/max(r_all['total'],1):.1f}%) "
          f"top3={r_all['top3']} top5={r_all['top5']} MRR={r_all['mrr']:.3f}")

    # 落盘报告
    lines = [
        "# 层3 变体评测 — 召回鲁棒性（2026-08-10）", "",
        f"- 语料: {len(blocks)} 块（docs + docs/only 全量 md）",
        f"- 原查询: {r_orig['total']}（docs/test/recall_queries.json）",
        f"- 变体: {r_all['total']}（docs/test/recall_queries_variants.json, LLM 生成）",
        f"- 融合: linear（BGE+BM25+SPO+扩散, 粗筛 top_c={top_c}）", "",
        "## 对比表", "",
        "| 查询集 | n | top1 | top3 | top5 | MRR |",
        "|---|---|---|---|---|---|",
        f"| 原查询 | {r_orig['total']} | {100.0*r_orig['top1']/max(r_orig['total'],1):.1f}% | {r_orig['top3']} | {r_orig['top5']} | {r_orig['mrr']:.3f} |",
    ]
    for vt in ["zh_syn", "en", "casual"]:
        r = r_var.get(vt)
        if r:
            lines.append(
                f"| 变体[{vt}] | {r['total']} | {100.0*r['top1']/max(r['total'],1):.1f}% "
                f"| {r['top3']} | {r['top5']} | {r['mrr']:.3f} |")
    lines.append(
        f"| 变体[全部] | {r_all['total']} | {100.0*r_all['top1']/max(r_all['total'],1):.1f}% "
        f"| {r_all['top3']} | {r_all['top5']} | {r_all['mrr']:.3f} |")
    lines += ["", "## 结论占位（看数字后填）", ""]
    out = os.path.join(ROOT, "docs", "test", "DOC_RECALL_VARIANT_BENCH_20260810.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    try:
        svc.flush_index_cache()
    except Exception:
        pass
    print(f"  报告: {out}")

if __name__ == "__main__":
    main()
