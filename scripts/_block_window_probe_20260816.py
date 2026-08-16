#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B 类 miss 的嵌入窗口覆盖探查（2026-08-16）:

对 q002/q033/q044/q052 的 bm25 命中块: 打印块文本长度、嵌入窗口
（doc_title|heading\\n前3000字）是否覆盖关键查询词、以及"只嵌关键段"
的 query-cos 对比。验证"长块稀释"假设。
"""
from __future__ import annotations

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402
from core.agent.compiler.semantic_encoder import get_encoder  # noqa: E402


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    byid = {b["id"]: b for b in blocks}
    enc = get_encoder()
    cases = [
        ("q002", "agentic 工具节点怎么让 LLM 自己调工具", [
            "docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md",
        ]),
        ("q052", "隐式关系候选怎么生成和核验，precision 多少", [
            "docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md",
        ]),
    ]
    for qid, query, docs in cases:
        qv = np.asarray(enc.encode([query], normalize=True)[0],
                        dtype=np.float32)
        print("=" * 80)
        print("[%s] %s" % (qid, query))
        for doc in docs:
            for b in [x for x in blocks if x.get("doc") == doc][:3]:
                text = b.get("text") or ""
                window = ("%s | %s\n%s" % (b.get("doc_title") or "",
                                           b.get("heading") or "",
                                           text))[:3000]
                bv = np.asarray(b.get("vector"), dtype=np.float32)
                full_cos = float(qv @ bv)
                # 只嵌文本前 500 字（更聚焦）
                wv = np.asarray(enc.encode(
                    [window[:500]], normalize=True)[0], dtype=np.float32)
                short_cos = float(qv @ wv)
                print("  %s" % b["id"][:60])
                print("    len=%d  window_len=%d  full_cos=%.4f  "
                      "short500_cos=%.4f" % (
                          len(text), len(window), full_cos, short_cos))
                for tok in ("agentic", "隐式关系", "precision"):
                    if tok in window[:3000]:
                        print("    [window有] %r" % tok)


if __name__ == "__main__":
    main()
