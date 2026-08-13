#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""精细化消融评测 — 逐层加看增益（2026-08-10）。

链路分层（用户拍板, 消融实验）:
  L0 粗召回基线: RRF 融合 top-k（本地, 快）
  L1 +子图扩展: SubgraphCompiler.compile_from_anchors（图搜索, 概念补齐）
  L2 +LLM 选择: LLM 拿"问题+子图内容"筛选最相关（完整精细化）

输出每层 top1 命中率 + 延迟, 量化每项真实贡献。
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service
from core.agent.recall.recall_service import format_anchors
from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler

GW = "http://127.0.0.1:8080"


def llm_filter(query: str, material: str, top_n: int = 1) -> list:
    """LLM 拿完整材料（问题+子图/锚点内容）筛选, 返回命中的块 id 前缀序号。"""
    prompt = (
        f"以下是检索到的相关资料（编号行）。判断哪条与查询最相关, "
        f"只输出编号, 逗号分隔, 最多{top_n}个:\n"
        f"查询: {query}\n\n{material}"
    )
    text = ""
    for _attempt in range(3):
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
    return [int(x) for x in text.replace(",", " ").split() if x.strip().isdigit()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--n", type=int, default=15)
    args = ap.parse_args()

    gold = load_goldset()
    queries = gold["queries"][:args.n]
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    svc = build_service(blocks, mode="rrf")
    sc = SubgraphCompiler(engine=None)

    stats = {"L0": 0, "L1": 0, "L2": 0}
    times = {"L0": [], "L1": [], "L2": []}
    detail = []
    for qi in queries:
        q, expected = qi["query"], set(qi["expected"])
        row = {"query": q[:35]}
        # L0 粗召回
        t0 = time.time()
        res = svc.recall(q, top_k=args.top_k, use_hyde=False)
        hits = res.hits[:args.top_k]
        times["L0"].append((time.time() - t0) * 1000)
        row["L0"] = bool(hits and hits[0].id in expected)
        stats["L0"] += row["L0"]
        # L1 +子图扩展（锚点条目路; 无事件/图数据时退化为锚点补齐）
        t0 = time.time()
        ctx = sc.compile_from_anchors(hits, max_anchors=8)
        material = sc.assemble_prompt(ctx)
        times["L1"].append((time.time() - t0) * 1000)
        # L1 判定: 期望块的文本是否进入子图内容（图搜索把正确内容拉进来）
        expected_texts = {b["id"]: b["text"][:80] for b in blocks
                          if b["id"] in expected}
        ctx_text = " ".join(e.content for e in ctx.entries)
        row["L1_ctx"] = any(t and t[:40] in ctx_text
                            for t in expected_texts.values())
        row["L1"] = row["L0"]  # 子图是扩展, 不改粗召回 top1 本身
        stats["L1"] += row["L1"]
        # L2 +LLM 用子图材料筛选
        t0 = time.time()
        picked = llm_filter(q, material, top_n=1)
        times["L2"].append((time.time() - t0) * 1000)
        # L2 判定: LLM 选中的子图条目内容是否与期望块文本重叠
        picked_ok = False
        if picked:
            entries = list(ctx.entries)
            idx = picked[0] - 1
            if 0 <= idx < len(entries):
                e = entries[idx]
                picked_text = e.content[:80]
                picked_ok = any(t and t[:40] in picked_text
                                for t in expected_texts.values())
        row["L2"] = picked_ok
        stats["L2"] += picked_ok
        detail.append(row)
        print(f"  {row['query']}: L0={'Y' if row['L0'] else 'n'} "
              f"L1_ctx={'Y' if row['L1_ctx'] else 'n'} "
              f"L2={'Y' if row['L2'] else 'n'}")

    total = len(queries)
    print(f"\n=== 消融评测 (黄金集前 {total}, top-{args.top_k}) ===")
    for k in ["L0", "L1", "L2"]:
        t = times[k]
        print(f"{k}: top1={stats[k]}/{total} ({100.0*stats[k]/total:.1f}%) "
              f"延迟 avg={sum(t)/len(t):.0f}ms")
    print(f"\nL1 子图上下文含期望块: {sum(1 for r in detail if r['L1_ctx'])}/{total} "
          f"({100.0*sum(1 for r in detail if r['L1_ctx'])/total:.1f}%)")

    out = "docs/test/REFINE_ABLATION_20260810.md"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"top_k": args.top_k, "n": total, "stats": stats,
                   "times": {k: {"avg_ms": sum(v)/len(v) if v else 0} for k, v in times.items()},
                   "detail": detail}, f, ensure_ascii=False, indent=1)
    print(f"详情: {out}")


if __name__ == "__main__":
    main()
