#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""链路详情 dump — 从问题到每层召回内容（2026-08-10）。

输出 docs/test/REFINE_CHAIN_DUMP_20260810.md:
  每条 query: 问题 → L0 粗召回 top-10（id/source/score/摘要）
             → L1 子图 entries（domain/content/confidence/source）
             → LLM 收到的完整 prompt → LLM 返回 → 命中判定
"""
from __future__ import annotations
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service
from core.agent.recall.recall_service import format_anchors
from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler

GW = "http://127.0.0.1:8080"


def llm_raw(query: str, material: str) -> tuple:
    prompt = (
        f"以下是检索到的相关资料（编号行）。判断哪条与查询最相关, "
        f"只输出编号, 逗号分隔, 最多1个:\n"
        f"查询: {query}\n\n{material}"
    )
    text, latency = "", 0.0
    for _attempt in range(3):
        t0 = time.time()
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
        latency += (time.time() - t0) * 1000
        if text.strip():
            break
        time.sleep(1)
    return prompt, text, latency


def main():
    gold = load_goldset()
    queries = gold["queries"][:8]
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    svc = build_service(blocks, mode="rrf")
    sc = SubgraphCompiler(engine=None)

    lines = ["# 精细化链路详情 — 问题 → 每层召回内容（2026-08-10）", "",
             f"- 语料: goldset {len(blocks)} 块 / query {len(queries)} 条", ""]
    for qi in queries:
        q, expected = qi["query"], set(qi["expected"])
        lines += [f"---", "", f"## Q: {q}", f"- 期望块: {sorted(expected)}", ""]
        # L0 粗召回
        res = svc.recall(q, top_k=10, use_hyde=False)
        lines += ["### L0 粗召回 top-10（RRF 融合）", ""]
        for i, h in enumerate(res.hits[:10], 1):
            mark = "✓" if h.id in expected else " "
            lines.append(f"{i}{mark} **{h.id}** [{h.source} {h.fused():.2f}] "
                         f"{(h.text or '').replace(chr(10), ' ')[:150]}")
        lines += [""]
        # L1 子图
        t0 = time.time()
        ctx = sc.compile_from_anchors(res.hits[:10], max_anchors=8)
        lines += [f"### L1 子图扩展（{time.time()-t0:.0f}ms, "
                  f"{len(ctx.entries)} entries, budget={ctx.budget}）", ""]
        expected_texts = {b["id"]: b["text"][:80] for b in blocks
                          if b["id"] in expected}
        for i, e in enumerate(ctx.entries, 1):
            hit_mark = ""
            for tid, txt in expected_texts.items():
                if txt and txt[:40] in e.content:
                    hit_mark = f" ✓≈{tid}"
                    break
            lines.append(f"{i}{hit_mark} [{e.domain} {e.confidence:.2f} src={e.source}] "
                         f"{e.content.replace(chr(10), ' ')[:200]}")
            for cr in e.cross_refs[:3]:
                lines.append(f"    ^ref: {cr.get('target_domain','?')}.{cr.get('target_event_id','')} = {cr.get('note','')[:60]}")
        lines += [""]
        # LLM prompt + 返回
        material = sc.assemble_prompt(ctx)
        prompt, text, lat = llm_raw(q, material)
        lines += [f"### L2 LLM 收到的完整 prompt（{lat:.0f}ms）", "",
                  "```", prompt, "```", "",
                  f"### LLM 返回: `{text}`", "",
                  "---", ""]

    out = "docs/test/REFINE_CHAIN_DUMP_20260810.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"written: {out} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
