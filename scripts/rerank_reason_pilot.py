#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""推理精排试点 — qwen3.5-9b thinking ON + 方面覆盖协议（2026-08-14）。

假设（用户提出）: 推理模型的优势是训练中学到的"上下文隐性意图",
与 BM25（词面）/ SPO（语法约束）正交。协议: 问题拆方面 → 候选逐条
判覆盖 → 选覆盖最多且无矛盾的候选。

链路: 融合 top-5（fused 已很强, LLM 只在窄窗内判断, 不替换排序）→
llama.cpp server（--reasoning on --reasoning-budget 256）→ 对比
fused / CE / LLM 单选（历史试点）。

用法: .venv\\Scripts\\python.exe scripts/rerank_reason_pilot.py \
      [--n 61] [--base http://127.0.0.1:1235] [--model qwen35]
输出: docs/test/RERANK_REASON_PILOT_YYYYMMDD.md
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


def llm_pick(base_url: str, model: str, query: str, candidates: list,
             timeout_s: float = 60.0) -> tuple:
    """方面覆盖协议: 返回 (编号, 思考摘要, 延迟ms)。编号 0 = 解析失败。"""
    lines = []
    for i, c in enumerate(candidates, 1):
        line = f"{i}. [{c['doc']}] {c['text']}"
        if c.get("parent"):
            line += f" | 文件摘要: {c['parent']}"
        lines.append(line)
    prompt = (
        "问题往往由若干方面组成。对每个候选判断它覆盖了问题的哪些方面, "
        "选出覆盖方面最多、且与问题没有矛盾的候选。\n"
        "要求: 简短推理后, 最后单独一行只输出编号。\n\n"
        f"问题: {query}\n\n候选:\n" + "\n".join(lines)
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.0,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = (msg.get("reasoning_content") or "")[:120]
        m = re.search(r"(\d+)", content)
        idx = int(m.group(1)) if m else 0
        if not (1 <= idx <= len(candidates)):
            idx = 0
        return idx, reasoning.replace("\n", " "), (time.time() - t0) * 1000
    except Exception as e:
        return 0, f"ERR {str(e)[:60]}", (time.time() - t0) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=61)
    ap.add_argument("--base", default="http://127.0.0.1:1235")
    ap.add_argument("--model", default="qwen35")
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
    n = n_fused = n_llm = n_parse_fail = 0
    t_llm = []
    for qi in queries:
        exp_files = qi["expected"]
        if not exp_files or exp_files[0].startswith("goldset:"):
            continue
        if n >= args.n:
            break
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
        res = svc.recall(qi["query"], intent=intent, top_k=5,
                         use_hyde=False)
        hits = res.hits[:5]
        fused_ok = bool(hits) and hits[0].id in exp
        candidates = [{
            "doc": (h.path[0] if h.path else h.id.split("#")[0])[:60],
            "text": (h.text or "").replace("\n", " ")[:200],
            "parent": (h.parent_context or "")[:150],
        } for h in hits]
        picked, reason, dt = llm_pick(args.base, args.model,
                                      qi["query"], candidates)
        picked_ok = (1 <= picked <= len(hits)
                     and hits[picked - 1].id in exp)
        n += 1
        n_fused += fused_ok
        n_llm += picked_ok
        n_parse_fail += picked == 0
        t_llm.append(dt)
        rows.append({
            "query": qi["query"][:40], "fused": fused_ok,
            "llm": picked_ok, "pick": picked, "reason": reason,
            "ms": round(dt),
        })
        print(f"[{n}] fused={fused_ok} llm={picked_ok} pick={picked} "
              f"{dt:.0f}ms | {qi['query'][:28]}", flush=True)

    out = [
        "# 推理精排试点 — doc 域（%s）" % time.strftime("%Y-%m-%d"), "",
        f"- 模型: {args.model} ({args.base}, thinking ON + 预算受限)",
        f"- 协议: 方面覆盖（问题拆方面 → 候选判覆盖 → 选覆盖最多无矛盾）",
        f"- 链路: 融合 top-5 窄窗 + LLM 判断（不替换排序）", "",
        "## 汇总", "",
        f"- 运行: {n} 条 doc 查询",
        f"- fused top1: {n_fused}/{n} ({100.0*n_fused/max(n,1):.1f}%)",
        f"- **推理 LLM top1: {n_llm}/{n} "
        f"({100.0*n_llm/max(n,1):.1f}%)**",
        f"- 上行（fused miss → LLM 中）: "
        f"{sum(1 for r in rows if not r['fused'] and r['llm'])}",
        f"- 下行（fused 中 → LLM 拆）: "
        f"{sum(1 for r in rows if r['fused'] and not r['llm'])}",
        f"- 解析失败: {n_parse_fail}",
        f"- 平均 LLM 延迟: {sum(t_llm)/max(len(t_llm),1):.0f} ms/query", "",
        "## 逐条（含思考摘要）", "",
    ]
    for r in rows:
        out.append(
            f"- fused={r['fused']} llm={r['llm']} pick={r['pick']} "
            f"{r['ms']}ms | {r['query']}")
        out.append(f"    思考: {r['reason']}")
    report = "\n".join(out)
    path = "docs/test/RERANK_REASON_PILOT_%s.md" % time.strftime("%Y%m%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + "\n".join(out[:14]))
    print("\nwritten:", path)


if __name__ == "__main__":
    main()
