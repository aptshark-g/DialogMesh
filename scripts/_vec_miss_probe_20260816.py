#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探查 vector 完全漏检的 B 类 miss（2026-08-16）:

对 q002/q033/q044/q052: 找出 bm25 rank-1 块, 打印其文本、doc/path、
嵌入窗口（doc_title|节标题+内容前 3000 字）是否覆盖查询词、以及该块
与 query 的真实余弦分（对比 vector top-1 的分）。
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
    doc_blocks = drb.load_blocks()
    print("文档块: %d" % len(doc_blocks))
    drb.prepare_vectors(doc_blocks)
    doc_service = build_service(doc_blocks, mode="vector_primary")
    byid = {b["id"]: b for b in doc_blocks}
    queries = {
        "q002": "agentic 工具节点怎么让 LLM 自己调工具",
        "q033": "决策事件有哪些 kind，strategy_switch 和 plan_gate 区别",
        "q044": "执行迹和变更日志两个白盒视图各展示什么",
        "q052": "隐式关系候选怎么生成和核验，precision 多少",
        "q059": "PCR zone 和意图分类怎么映射到召回策略",
    }
    for qid, query in queries.items():
        print("=" * 80)
        print("[%s] %s" % (qid, query))
        import numpy as np
        from core.agent.compiler.semantic_encoder import get_encoder
        enc = get_encoder()
        qv = np.asarray(enc.encode([query], normalize=True)[0],
                        dtype=np.float32)
        vec = doc_service._vector_anchors(query, 5)
        print("vector top-1: %s score=%.4f" % (vec[0].id[:18], vec[0].score))
        bm = doc_service._bm25_anchors(query, 5)
        for i, h in enumerate(bm[:3], 1):
            b = byid.get(h.id)
            text = (b.get("text") or "") if b else ""
            bv = np.asarray(b.get("vector"), dtype=np.float32) if b and (
                b.get("vector") is not None) else None
            sim = float(qv @ bv) if bv is not None else None
            print("  bm25 #%d: %s score=%.4f doc=%s  query-cos=%.4f" % (
                i, h.id[:18], h.score, (b or {}).get("doc", "?"),
                sim if sim is not None else -1))
            print("    text[:260]: %s" % text[:260].replace("\n", " "))
            for tok in ("agentic", "决策事件", "strategy_switch", "执行迹",
                        "变更日志", "隐式关系", "precision", "PCR zone"):
                if tok in text:
                    print("    [tok] %r 在块文本中" % tok)
        # 检查该块是否被嵌入（向量非全零）
        b = byid.get(bm[0].id) if bm else None
        if b is not None and b.get("vector") is not None:
            import numpy as np
            v = np.asarray(b["vector"], dtype=np.float32)
            print("    bm25 #1 块向量 norm=%.4f nnz=%d" % (
                float(np.linalg.norm(v)), int((v != 0).sum())))
        print()
    # q059 专项: 期望文档的切块与各路线命中
    print("=" * 80)
    print("[q059 专项] RECALL_MAINSTREAM_GAP 切块情况")
    query = queries["q059"]
    target = "docs/only/recall/RECALL_MAINSTREAM_GAP_20260811.md"
    t_blocks = [b for b in doc_blocks if b.get("doc") == target]
    print("期望文档块数: %d" % len(t_blocks))
    for b in t_blocks:
        print("- id=%s text[:120]: %s" % (b["id"][:18],
                                          (b.get("text") or "")[:120].replace(
                                              "\n", " ")))
    if t_blocks:
        exp = {b["id"] for b in t_blocks}
        for src, fn in (("vector", doc_service._vector_anchors),
                        ("bm25", doc_service._bm25_anchors),
                        ("spo", doc_service._spo_anchors)):
            hs = fn(query, 40)
            best = next((i for i, h in enumerate(hs, 1) if h.id in exp), None)
            print("%-6s 期望块最高 rank=%s" % (src, best))
        res = doc_service.recall(query, top_k=20, use_hyde=False,
                                 intent="记忆召回")
        ids = [h.id for h in res.hits]
        hit = next((i + 1 for i, x in enumerate(ids) if x in exp), None)
        print("fused 命中 rank=%s" % hit)


if __name__ == "__main__":
    main()
