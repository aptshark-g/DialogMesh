#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""伪相关反馈（PRF, Rocchio）探查（2026-08-16）:

query 向量 + bm25 top-k 块向量的质心 → 二次 vector 检索。验证 B 类
期望块（query-cos 0.43-0.51, 不在 vector top-100）能否被质心检索拉起。
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from scripts.recall_goldset import build_service  # noqa: E402
import scripts.doc_recall_bench as drb  # noqa: E402


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    byid = {b["id"]: b for b in blocks}
    cases = [
        ("agentic 工具节点怎么让 LLM 自己调工具",
         {"docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md",
          "docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md"}),
        ("决策事件有哪些 kind，strategy_switch 和 plan_gate 区别",
         {"docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md"}),
        ("执行迹和变更日志两个白盒视图各展示什么",
         {"docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md"}),
        ("隐式关系候选怎么生成和核验，precision 多少",
         {"docs/only/recall/CONTENT_TO_GRAPH_20260811.md",
          "docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md"}),
    ]
    for query, exp_docs in cases:
        exp_ids = {b["id"] for b in blocks if b["doc"] in exp_docs}
        print("=" * 78)
        print("[%s]" % query)
        base = svc._vector_anchors(query, 20)
        base_best = next(
            (i + 1 for i, h in enumerate(base) if h.id in exp_ids), None)
        print("  base vector top1=%s 期望块最好rank=%s" % (
            base[0].id[:40] if base else "-", base_best))
        # PRF: 原 query 向量 + bm25 top-3 块向量质心
        bm = svc._bm25_anchors(query, 5)
        vecs = []
        for h in bm[:3]:
            b = byid.get(h.id)
            if b and b.get("vector") is not None:
                vecs.append(np.asarray(b["vector"], dtype=np.float32))
        if not vecs:
            continue
        qv = np.asarray(svc._embed(query), dtype=np.float32)
        centroid = sum(vecs) / len(vecs)
        for alpha in (0.3, 0.5, 0.7):
            aug = qv * (1 - alpha) + centroid * alpha
            aug = aug / (np.linalg.norm(aug) + 1e-9)
            scores = [float(np.dot(aug, np.asarray(
                b.get("vector"), dtype=np.float32)))
                for b in blocks if b.get("vector") is not None]
            order = np.argsort(scores)[::-1]
            hit_rank = None
            for pos in range(20):
                if blocks[order[pos]]["id"] in exp_ids:
                    hit_rank = pos + 1
                    break
            print("  PRF alpha=%.1f: 期望块rank=%s" % (alpha, hit_rank))


if __name__ == "__main__":
    main()
