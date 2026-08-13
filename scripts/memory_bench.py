#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""记忆评测 — 检索准确率 + 幻觉率（2026-08-10, RAGAS 口径修正版）。

补测试缺口（用户清单）:
  记忆检索准确率 / RAG 幻觉率

指标（RAGAS 标准, docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md）:
  - Context Precision: 加权平均（分母=相关项数, 非固定 k）— 检索排序质量
  - Context Recall: 参考 claim 级判定（LLM）— 记忆检索准确率正解
  - 幻觉率 = 1 - Faithfulness（回复 claim 级判定, 与召回无关率区分）

用法:
  .venv\\Scripts\\python.exe scripts/memory_bench.py --top-k 5 --mode linear
"""
from __future__ import annotations
import argparse, json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import (  # noqa: E402
    load_goldset, build_service, hit_rank, random_baseline,
)


def context_precision(service, qi, top_k, sid=None):
    """RAGAS Context Precision: Σ(P@k × v_k) / 相关项总数。

    只对命中的相关块位置加权: 相关块越靠前分越高, 分母是相关项数。
    """
    res = service.recall(qi["query"], top_k=top_k, use_hyde=False, sid=sid)
    expected = set(qi["expected"])
    relevant = 0
    numerator = 0.0
    for k, h in enumerate(res.hits[:top_k], 1):
        is_rel = h.id in expected
        if is_rel:
            relevant += 1
            tp = sum(1 for j, hh in enumerate(res.hits[:k], 1)
                     if hh.id in expected)
            numerator += tp / k
    if relevant == 0:
        return 0.0
    return numerator / relevant


def mrr(service, qi, top_k, sid=None):
    """MRR: 首个相关块排名倒数（无命中 = 0）。多块期望公平度量。"""
    res = service.recall(qi["query"], top_k=top_k, use_hyde=False, sid=sid)
    expected = set(qi["expected"])
    for k, h in enumerate(res.hits[:top_k], 1):
        if h.id in expected:
            return 1.0 / k
    return 0.0


def ndcg(service, qi, top_k, sid=None):
    """nDCG@k: 位置对数衰减（DCG / IDCG）。多相关块时前移加分。"""
    import math
    res = service.recall(qi["query"], top_k=top_k, use_hyde=False, sid=sid)
    expected = set(qi["expected"])
    rel = [1.0 if h.id in expected else 0.0 for h in res.hits[:top_k]]
    if not any(rel):
        return 0.0
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
    ideal = sorted(rel, reverse=True)
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def recall_at(service, qi, k, sid=None):
    """Recall@k: 任一期望块进 top-k（宽松口径, 对标业界"召回率 90%"展示）。"""
    res = service.recall(qi["query"], top_k=k, use_hyde=False, sid=sid)
    return 1.0 if any(h.id in qi["expected"] for h in res.hits[:k]) else 0.0


# 情景再现层 query（指代/上下文依赖/画像/问候）: 粗召回无上下文测不了,
# 归 subgraph 事件溯源评测（2026-08-11 用户拍板分层）。
PRONOUN_RE = __import__("re").compile(
    r"^(继续|然后|那|这|嗯|好|可以|行|对|是|hi|test|hello|在吗|我|你|现在|没|有|再|就|把|给|它|他|她|做|来)")


def is_context_query(query: str) -> bool:
    return bool(PRONOUN_RE.match(query.strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--mode", default="linear", choices=["linear", "rrf"])
    ap.add_argument("--layer", default="coarse",
                    choices=["coarse", "scene", "all"])
    args = ap.parse_args()

    gold = load_goldset()
    queries = gold["queries"]
    # 用 goldset 的块构造 service（保持与 recall_goldset 同环境）
    blocks = gold.get("blocks") or []
    if not blocks:
        # 从 queries 的 expected 提取块文本（goldset 存储格式兼容）
        blocks = []
        for qi in queries:
            for eid in qi.get("expected", []):
                txt = qi.get("_blocks", {}).get(eid, "")
                if txt:
                    blocks.append({"id": eid, "text": txt})
    svc = build_service(blocks, mode=args.mode)
    top_k = args.top_k
    if args.layer == "coarse":
        queries = [q for q in queries if not is_context_query(q["query"])]
    elif args.layer == "scene":
        queries = [q for q in queries if is_context_query(q["query"])]

    hits1 = hits3 = hits5 = 0
    cp_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    recall_sums = {k: 0.0 for k in (5, 10, 20)}
    per_query = []
    for qi in queries:
        rank = hit_rank(svc, qi["query"], qi["expected"], top_k)
        if rank == 1:
            hits1 += 1
        if rank and rank <= 3:
            hits3 += 1
        if rank and rank <= 5:
            hits5 += 1
        p = context_precision(svc, qi, top_k)
        m = mrr(svc, qi, top_k)
        d = ndcg(svc, qi, top_k)
        cp_sum += p
        mrr_sum += m
        ndcg_sum += d
        for k in recall_sums:
            recall_sums[k] += recall_at(svc, qi, k)
        r5 = recall_at(svc, qi, 5)
        per_query.append({"query": qi["query"][:50], "rank": rank,
                          "context_precision": round(p, 3),
                          "mrr": round(m, 3), "ndcg": round(d, 3),
                          "recall5": int(r5)})

    total = len(queries)
    rb = random_baseline(gold, top_k)
    avg_cp = cp_sum / max(total, 1)
    avg_mrr = mrr_sum / max(total, 1)
    avg_ndcg = ndcg_sum / max(total, 1)
    avg_recall = {k: s / max(total, 1) for k, s in recall_sums.items()}
    print(f"=== 记忆评测 (黄金集 {total} query/{args.layer}层, {args.mode} 融合, top-{top_k}) ===")
    print(f"检索准确率: top1={hits1}/{total} ({100.0*hits1/total:.1f}%) "
          f"top3={hits3} top5={hits5} (随机基线 {100.0*rb:.1f}%)")
    print(f"Context Precision@{top_k} (RAGAS 加权): {avg_cp:.3f}")
    print(f"MRR@{top_k}: {avg_mrr:.3f} | nDCG@{top_k}: {avg_ndcg:.3f}")
    print("Recall@k: " + " | ".join(
        f"@{k}={100.0*v:.1f}%" for k, v in avg_recall.items()))
    print(f"注: 幻觉率(Faithfulness) 需 LLM claim 判定, 走 v3 回复评测")

    out = "docs/test/MEMORY_BENCH_20260810.md"
    report = [
        "# 记忆评测 — 检索准确率 + 幻觉率（2026-08-10）", "",
        f"- 数据: data/recall_goldset.json（{total} query / {len(blocks)} 块）",
        f"- 层: {args.layer}（coarse=粗召回 / scene=情景再现 / all=全部）",
        f"- 融合: {args.mode}; top-{top_k}", "",
        "## 指标", "",
        f"| 指标 | 值 | 随机基线 |",
        f"|---|---|---|",
        f"| top1 命中率 | {100.0*hits1/total:.1f}% | {100.0*rb:.1f}% |",
        f"| top3 命中率 | {100.0*hits3/total:.1f}% | - |",
        f"| top5 命中率 | {100.0*hits5/total:.1f}% | - |",
        f"| Context Precision@{top_k} | {avg_cp:.3f} | - |",
        f"| MRR@{top_k} | {avg_mrr:.3f} | - |",
        f"| nDCG@{top_k} | {avg_ndcg:.3f} | - |",
        f"| Recall@5 | {100.0*avg_recall[5]:.1f}% | - |",
        f"| Recall@10 | {100.0*avg_recall[10]:.1f}% | - |",
        f"| Recall@20 | {100.0*avg_recall[20]:.1f}% | - |",
        "", "## 幻觉率（Faithfulness, 待 LLM claim 判定）", "",
        "- 定义: 回复中被检索上下文支持的 claim 占比（RAGAS）",
        "- 需在 v3 任务评测里对回复逐条拆 claim 判定, 与召回无关率区分",
        "- 待接入: agent_bench.py 扩展（回复 → claims → 上下文支持判定）",
        "",
        "## 说明", "",
        "- Context Precision: 相关块越靠前分越高（分母=相关项数）",
        "- 口径依据: docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md",
        "- 与 DOC_RECALL_BENCH 互补: 那是文档域 top1 命中, 这是会话域",
        "- 复跑: `.venv\\Scripts\\python.exe scripts/memory_bench.py --mode rrf`",
        "",
    ]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"报告: {out}")


if __name__ == "__main__":
    main()
