#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LLM 精排试点 — doc 域 top1 40%+ 目标（2026-08-14）。

设计口径（用户拍板）: LLM 不做"凭直觉打分", 而是拿"问题 + 召回内容"
做筛选。链路: 粗召回（现状不动）→ 融合 top-15 候选（带方案 B
parent_context 文件摘要 + path）→ LLM 选最相关 1 条 → 与 fused top1
对比。

指标: fused top1 vs LLM top1（doc 61 条）; 上行（fused miss 但 LLM 中）/
下行（fused 中但 LLM 拆）; 期望块未进候选（检索缺口, LLM 无法救）;
平均延迟。

用法:
  .venv\\Scripts\\python.exe scripts/llm_rerank_pilot.py [--n 8] \
      [--base http://127.0.0.1:1234] [--model qwen/qwen3.5-9b]

输出: docs/test/LLM_RERANK_PILOT_YYYYMMDD.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set
from scripts.recall_goldset import build_service
import scripts.doc_recall_bench as drb


def llm_pick_one(base_url: str, model: str, query: str,
                 candidates: list, timeout_ms: int = 60000) -> int:
    """LLM 筛选: 问题 + 候选内容 → 最相关 1 条编号（1-based）。

    返回 0 表示解析失败/空。失败时重试 1 次。
    """
    lines = []
    for i, c in enumerate(candidates, 1):
        line = f"{i}. [{c['doc']}] {c['text']}"
        if c.get("parent"):
            line += f" | 文件摘要: {c['parent']}"
        lines.append(line)
    prompt = (
        "根据问题判断下面哪条资料与问题最相关。\n"
        "要求: 只输出一个编号（如 7）, 不要输出其他文字。\n\n"
        f"问题: {query}\n\n"
        "候选资料:\n" + "\n".join(lines)
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16,
        "temperature": 0.0,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as r:
                d = json.loads(r.read().decode("utf-8"))
            text = (d.get("choices") or [{}])[0].get("message", {}).get(
                "content") or ""
            m = re.search(r"(\d+)", text)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= len(candidates):
                    return idx
        except Exception as e:
            last_err = str(e)[:120]
            time.sleep(1)
            continue
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="只跑前 n 条 doc 查询")
    ap.add_argument("--base", default="http://127.0.0.1:1234")
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--top-k", type=int, default=15, help="给 LLM 的候选数")
    args = ap.parse_args()

    queries = load_query_set("docs/test/recall_queries_100.md")
    blocks = drb.load_blocks()
    print("doc blocks:", len(blocks), flush=True)
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    rows = []
    n_run = n_fused_top1 = n_llm_top1 = n_upside = n_downside = n_gap = 0
    n_llm_parse_fail = 0
    llm_ms = []
    for qi in queries:
        exp_files = qi["expected"]
        if not exp_files or exp_files[0].startswith("goldset:"):
            continue  # 只跑 doc 域
        if args.n and n_run >= args.n:
            break
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
        intent = qi.get("intent") or "记忆召回"
        res = svc.recall(qi["query"], intent=intent, top_k=20,
                         use_hyde=False)
        hits = res.hits[:args.top_k]
        fused_top1_ok = bool(hits) and hits[0].id in exp_set
        # 期望块是否在候选内（不在 = 检索缺口, LLM 无法救）
        exp_in_cand = any(h.id in exp_set for h in res.hits)

        candidates = [{
            "id": h.id,
            "doc": (h.path[0] if h.path else h.id.split("#")[0])[:60],
            "text": (h.text or "").replace("\n", " ")[:120],
            "parent": (h.parent_context or "")[:100],
        } for h in hits]
        t0 = time.time()
        picked = llm_pick_one(args.base, args.model, qi["query"], candidates)
        dt_ms = (time.time() - t0) * 1000
        llm_ms.append(dt_ms)
        picked_id = candidates[picked - 1]["id"] if picked else None
        llm_top1_ok = picked_id is not None and picked_id in exp_set
        if picked == 0:
            n_llm_parse_fail += 1

        n_run += 1
        n_fused_top1 += fused_top1_ok
        n_llm_top1 += llm_top1_ok
        n_upside += (not fused_top1_ok) and llm_top1_ok
        n_downside += fused_top1_ok and (not llm_top1_ok)
        n_gap += (not exp_in_cand)
        rows.append({
            "query": qi["query"][:44], "intent": intent,
            "fused_top1": fused_top1_ok, "llm_top1": llm_top1_ok,
            "fused_rank": next((i + 1 for i, h in enumerate(res.hits)
                                if h.id in exp_set), None),
            "picked": picked, "picked_id": (picked_id or "")[:52],
            "exp_in_cand": exp_in_cand,
            "llm_ms": round(dt_ms),
            "top1_src": (res.hits[0].source if res.hits else "-"),
        })
        print(f"[{n_run}/{sum(1 for q in queries if not q['expected'] or not q['expected'][0].startswith('goldset:'))}] "
              f"fused={fused_top1_ok} llm={llm_top1_ok} rank={rows[-1]['fused_rank']} "
              f"{dt_ms:.0f}ms | {qi['query'][:30]}", flush=True)

    out = [
        "# LLM 精排试点 — doc 域（%s）" % time.strftime("%Y-%m-%d"), "",
        f"- 模型: {args.model} ({args.base}) | 候选数: {args.top_k}",
        f"- 总耗时: {sum(llm_ms)/1000:.0f}s | 平均 LLM 延迟: "
        f"{sum(llm_ms)/max(len(llm_ms),1):.0f} ms/query", "",
        "## 汇总", "",
        f"- 运行: {n_run} 条 doc 查询",
        f"- fused top1: {n_fused_top1}/{n_run} "
        f"({100.0*n_fused_top1/max(n_run,1):.1f}%)",
        f"- LLM top1: {n_llm_top1}/{n_run} "
        f"({100.0*n_llm_top1/max(n_run,1):.1f}%)",
        f"- 上行（fused miss → LLM 中）: {n_upside}",
        f"- 下行（fused 中 → LLM 拆）: {n_downside}",
        f"- 期望块未进候选（检索缺口, LLM 无法救）: {n_gap}",
        f"- LLM 解析失败: {n_llm_parse_fail}", "",
        "## 逐条", "",
    ]
    for r in rows:
        out.append(
            f"- fused={r['fused_top1']} llm={r['llm_top1']} "
            f"rank={r['fused_rank']} pick={r['picked']} "
            f"gap={not r['exp_in_cand']} {r['llm_ms']}ms "
            f"[{r['top1_src']}] | {r['query']}")
    report = "\n".join(out)
    path = "docs/test/LLM_RERANK_PILOT_%s.md" % time.strftime("%Y%m%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)
    print("\nwritten:", path)


if __name__ == "__main__":
    main()
