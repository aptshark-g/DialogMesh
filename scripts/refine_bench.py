#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""精细化评测 — 粗召回 top-k → LLM 选择精排（2026-08-10）。

分层记录（用户拍板）: 粗召回（本地）vs 精细化（图搜索+LLM 选择）。
本脚本量化 LLM 选择的增益:
  - 粗召回: top1/top3/top5 命中率（黄金集）
  - LLM 精排: 粗召回 top-k → LLM 从候选挑最相关 → top1 命中率对比
  - 选择耗时（对比生成 ~20s, 选择应快得多）

用法:
  .venv\\Scripts\\python.exe scripts/refine_bench.py --top-k 10 --n 20
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service
from core.agent.recall.recall_service import RecallService, format_anchors

GW = "http://127.0.0.1:8080"


def llm_select(query: str, result, top_n: int = 1) -> list:
    """LLM 从候选锚点中挑最相关的 top_n。

    输入用 format_anchors（设计锚点格式: [source fused] <path> 摘要）——
    粗召回只给锚点, 真实内容由执行层精确查阅（RECALL_EXECUTION_BRIDGE）。
    """
    cand_text = format_anchors(result, max_chars=1800, max_hits=10)
    prompt = (
        f"以下是检索候选锚点, 判断哪个编号与查询最相关。"
        f"只输出编号, 逗号分隔, 最多{top_n}个:\n"
        f"查询: {query}\n\n{cand_text}"
    )
    text = ""
    for _attempt in range(3):  # 网关偶发空 content → 重试
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 128, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        text = d["choices"][0]["message"].get("content") or ""
        if text.strip():
            break
        time.sleep(1)
    nums = [int(x) for x in text.replace(",", " ").split() if x.strip().isdigit()]
    return [i - 1 for i in nums if 1 <= i <= 10][:top_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10, help="粗召回候选数")
    ap.add_argument("--n", type=int, default=20, help="评测 query 数（黄金集 40 条中取前 n）")
    args = ap.parse_args()

    gold = load_goldset()
    queries = gold["queries"][:args.n]
    blocks = [{"id": b["id"], "text": b["text"]} for b in (gold.get("blocks") or [])]
    # goldset blocks 结构确认
    if not blocks:
        blocks = []
        seen = set()
        for qi in gold["queries"]:
            for eid in qi.get("expected", []):
                if eid not in seen:
                    seen.add(eid)
                    blocks.append({"id": eid, "text": qi.get("_blocks", {}).get(eid, eid)})
    svc = build_service(blocks, mode="rrf")

    coarse_top1 = 0
    refine_top1 = 0
    select_times = []
    detail = []
    for qi in queries:
        q = qi["query"]
        expected = set(qi["expected"])
        res = svc.recall(q, top_k=args.top_k, use_hyde=False)
        hits = res.hits[:args.top_k]
        # 粗召回 top1
        if hits and hits[0].id in expected:
            coarse_top1 += 1
        # LLM 选择
        t0 = time.time()
        picked = llm_select(q, res, top_n=1)
        select_ms = (time.time() - t0) * 1000
        select_times.append(select_ms)
        picked_id = hits[picked[0]].id if picked else None
        if picked_id and picked_id in expected:
            refine_top1 += 1
        detail.append({
            "query": q[:40], "coarse_top1_hit": hits[0].id in expected if hits else False,
            "llm_picked_hit": bool(picked_id and picked_id in expected),
            "llm_select_ms": round(select_ms, 0),
        })
        print(f"  {q[:35]}... coarse_top1={'Y' if detail[-1]['coarse_top1_hit'] else 'n'} "
              f"llm_top1={'Y' if detail[-1]['llm_picked_hit'] else 'n'} ({select_ms:.0f}ms)")

    total = len(queries)
    print(f"\n=== 精细化评测 (黄金集前 {total} query, top-{args.top_k}) ===")
    print(f"粗召回 top1 命中: {coarse_top1}/{total} ({100.0*coarse_top1/total:.1f}%)")
    print(f"LLM 精排 top1 命中: {refine_top1}/{total} ({100.0*refine_top1/total:.1f}%)")
    print(f"LLM 选择延迟: avg={sum(select_times)/len(select_times):.0f}ms "
          f"p50={sorted(select_times)[len(select_times)//2]:.0f}ms")
    print(f"增益: +{100.0*(refine_top1-coarse_top1)/max(total,1):.1f}pp (绝对)")

    out = "docs/test/REFINE_BENCH_20260810.md"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"top_k": args.top_k, "n": total,
                   "coarse_top1": coarse_top1, "refine_top1": refine_top1,
                   "avg_select_ms": sum(select_times)/len(select_times) if select_times else 0,
                   "detail": detail}, f, ensure_ascii=False, indent=1)
    print(f"详情: {out}")


if __name__ == "__main__":
    main()
