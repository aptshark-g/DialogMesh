#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""质量筛选评测 — 推理 LLM 判断"召回内容能否回答"（2026-08-14）。

位置: 命中告一段落后, 子图/执行层之前的质量筛选闸门。推理模型
（qwen3.5-9b, thinking ON + 预算）拿"问题 + 召回锚点 + 父摘要",
判断能否回答; 不能 → 触发子图扩展/精确查阅/询问（生产决策点）。

标签（黄金集近似）: 期望块 ∈ 召回 top-5 → "能"; 否则 "不能"。
指标: 判断准确率 + 缺口检测（召回不足时 LLM 应说不能）。

用法: .venv\\Scripts\\python.exe scripts/answerability_pilot.py \
      [--n 61] [--base http://127.0.0.1:1235] [--model qwen35]
输出: docs/test/ANSWERABILITY_PILOT_YYYYMMDD.md
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


def judge(base_url: str, model: str, query: str, material: str,
          timeout_s: float = 60.0) -> tuple:
    """返回 (能回答: bool|None, 理由摘要, 延迟ms)。None = 解析失败。"""
    prompt = (
        "下面是一次检索召回的资料。判断这些资料是否足以回答用户问题。\n"
        "规则: 资料包含问题答案的核心信息 → 输出 能; "
        "资料缺失关键信息/只沾边 → 输出 不能。\n"
        "要求: 简短推理后, 最后一行只输出两个字: 能 或 不能。\n\n"
        f"问题: {query}\n\n召回资料:\n{material}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 900,
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
        reasoning = (msg.get("reasoning_content") or "")[:100]
        m = re.search(r"(能|不能)", content)
        ans = None
        if m:
            ans = m.group(1) == "能"
        return ans, reasoning.replace("\n", " "), (time.time() - t0) * 1000
    except Exception as e:
        return None, f"ERR {str(e)[:60]}", (time.time() - t0) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=61)
    ap.add_argument("--base", default="http://127.0.0.1:1235")
    ap.add_argument("--model", default="qwen35")
    args = ap.parse_args()

    queries = load_query_set("docs/test/recall_queries_100.md")
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])

    rows = []
    n = n_pos = n_judge_pos = 0
    tp = fp = tn = fn = 0
    t_all = []
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
        res = svc.recall(qi["query"],
                         intent=qi.get("intent") or "记忆召回",
                         top_k=5, use_hyde=False)
        label = any(h.id in exp for h in res.hits[:5])
        parts = []
        for i, h in enumerate(res.hits[:5], 1):
            parts.append(f"{i}. [{h.path[0] if h.path else '?'}] "
                         f"{(h.text or '')[:150]}")
            if h.parent_context:
                parts.append(f"   文件摘要: {h.parent_context[:120]}")
        material = "\n".join(parts)
        ans, reason, dt = judge(args.base, args.model,
                                qi["query"], material)
        t_all.append(dt)
        n += 1
        n_pos += label
        n_judge_pos += ans is True
        if ans is True and label:
            tp += 1
        elif ans is True and not label:
            fp += 1
        elif ans is False and label:
            fn += 1
        elif ans is False and not label:
            tn += 1
        rows.append((qi["query"][:36], label, ans, reason, round(dt)))
        print(f"[{n}] label={'能' if label else '不能'} "
              f"judge={ans} {dt:.0f}ms | {qi['query'][:26]}", flush=True)

    acc = (tp + tn) / max(n, 1)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    out = [
        "# 质量筛选评测 — 推理 LLM 可答性判断（%s）" % time.strftime("%Y-%m-%d"),
        "",
        f"- 模型: {args.model} ({args.base}, thinking ON + 预算)",
        f"- 输入: 问题 + top-5 锚点 + 父摘要 | 标签: 期望 ∈ top-5",
        f"- 平均延迟: {sum(t_all)/max(len(t_all),1):.0f} ms/query", "",
        "## 汇总", "",
        f"- 运行: {n} | 标签'能回答': {n_pos} | 判断'能': {n_judge_pos}",
        f"- 判断准确率: {100.0*acc:.1f}%",
        f"- '能'判断 precision: {100.0*prec:.1f}% | recall: {100.0*rec:.1f}%",
        f"- 缺口检测（标签'不能' 且 判断'不能'）: {tn} 条", "",
        "## 逐条", "",
    ]
    for q, label, ans, reason, dt in rows:
        out.append(f"- label={'能' if label else '不能'} "
                   f"judge={ans} {dt}ms | {q}")
        out.append(f"    思考: {reason}")
    report = "\n".join(out)
    path = "docs/test/ANSWERABILITY_PILOT_%s.md" % time.strftime("%Y%m%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + "\n".join(out[:14]))
    print("\nwritten:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
