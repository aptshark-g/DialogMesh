#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""隐式关系候选 LLM 核验（2026-08-11）。

抽样 implicit_edge_candidates.json → 网关判定（真/假关系 + 类型）→
precision 统计。核验通过 → inferred_verified 边（带核验依据）。

用法: .venv\\Scripts\\python.exe scripts/verify_implicit_edges.py --n 12
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GW = "http://127.0.0.1:8080"
VAULT = r"C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design"


def llm_judge(prompt: str, max_tokens: int = 128) -> str:
    # 重试机制（2026-08-11）: 网关偶发空返回（finish=length）, 重试 3 次
    for attempt in range(3):
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            text = d["choices"][0]["message"].get("content") or ""
            if text.strip():
                return text
        except Exception:
            pass
        time.sleep(1.0 + attempt)
    return ""


def load_summaries() -> dict:
    out = {}
    for fp in glob.glob(os.path.join(VAULT, "*.md")):
        name = os.path.splitext(os.path.basename(fp))[0]
        text = open(fp, encoding="utf-8").read()
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        out[name] = re.sub(r"^#+\s*", "", first)[:120]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="抽样核验数")
    args = ap.parse_args()
    data = json.load(open("data/implicit_edge_candidates.json", encoding="utf-8"))
    cands = data["candidates"][:args.n] if args.n else data["candidates"]
    summaries = load_summaries()

    results = []
    for c in cands:
        prompt = (
            "判断两篇文档是否存在真实语义关系（共享主题/依赖/引用/扩展）。"
            "只输出: YES 关系类型 或 NO。关系类型限: related_to/extends/refines/"
            "implements/discusses。\n\n"
            f"文档A [{c['source']}]: {summaries.get(c['source'], c['source_summary'])}\n"
            f"文档B [{c['target']}]: {summaries.get(c['target'], c['target_summary'])}"
        )
        raw = llm_judge(prompt, max_tokens=128)
        verdict = raw.strip().upper()
        is_rel = verdict.startswith("YES")
        rel_type = ""
        if is_rel and len(verdict.split()) > 1:
            rel_type = verdict.split()[1].lower()
        results.append({**c, "verdict": verdict[:40], "is_relation": is_rel,
                        "rel_type": rel_type})
        print("%s <-> %s: %s" % (c["source"][:35], c["target"][:35], verdict[:40]))
        time.sleep(0.4)

    n = len(results)
    yes = sum(1 for r in results if r["is_relation"])
    print("核验 %d: 真关系 %d (precision %.0f%%)" % (
        n, yes, 100.0 * yes / max(1, n)))
    types = {}
    for r in results:
        if r["rel_type"]:
            types[r["rel_type"]] = types.get(r["rel_type"], 0) + 1
    print("关系类型分布:", types)
    out = {"n": n, "precision": yes / max(1, n), "results": results}
    with open("docs/test/IMPLICIT_EDGE_VERIFY_20260811.json", "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written: docs/test/IMPLICIT_EDGE_VERIFY_20260811.json")
    # 核验通过的候选 → inferred_verified 边落盘（2026-08-11）
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    store = UnifiedGraphStore(os.path.join("data", "unified_graph.db"))
    store.open()
    added = 0
    for r in results:
        if not r.get("is_relation"):
            continue
        store.save_edge(
            edge_type="inferred", domain="vault_docs",
            source_id=f"vault:{r['source']}", target_id=f"vault:{r['target']}",
            data={"source_kind": "inferred_verified",
                  "rel_type": r.get("rel_type", ""),
                  "similarity": r.get("similarity")},
            weight=0.6)
        added += 1
    store.close()
    print("inferred_verified 边落盘: %d" % added)


if __name__ == "__main__":
    main()
