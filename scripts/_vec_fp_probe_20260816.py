#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""vector 假阳性块内容探查（2026-08-16）:

对 q002/q052, 打印 vector top-5 的块 id/文本, 与期望块的 query-cos 对比。
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.recall_goldset import build_service  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    byid = {b["id"]: b for b in blocks}
    svc = build_service(blocks, mode="vector_primary")
    for qid, query in (
            ("q002", "agentic 工具节点怎么让 LLM 自己调工具"),
            ("q052", "隐式关系候选怎么生成和核验，precision 多少")):
        print("=" * 80)
        print("[%s] %s" % (qid, query))
        for i, h in enumerate(svc._vector_anchors(query, 5), 1):
            b = byid.get(h.id)
            text = (b.get("text") or "") if b else ""
            print("  #%d %s score=%.4f doc=%s" % (
                i, h.id[:52], h.score, (b or {}).get("doc", "?")))
            print("    %s" % text[:200].replace("\n", " "))


if __name__ == "__main__":
    main()
