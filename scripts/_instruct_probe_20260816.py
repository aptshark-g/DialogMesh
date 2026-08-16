#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BGE 查询指令前缀探查（2026-08-16）:

BGE-M3 检索协议: query 加指令前缀（zh: "为这个句子生成表示以用于检索
相关文章："; en: "Represent this sentence for searching relevant
passages:"), 文档不加。当前实现 query/文档同一编码, 无前缀 — 对称嵌入
对提问式 query 表现次优。本脚本验证加前缀后 B 类期望块的 vector rank。
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from core.agent.compiler.semantic_encoder import get_encoder  # noqa: E402

INSTR_ZH = "为这个句子生成表示以用于检索相关文章："
INSTR_EN = "Represent this sentence for searching relevant passages:"


def main():
    blocks = []
    import scripts.doc_recall_bench as drb
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    enc = get_encoder()
    cases = [
        ("q002", "agentic 工具节点怎么让 LLM 自己调工具",
         {"docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md"}),
        ("q033", "决策事件有哪些 kind，strategy_switch 和 plan_gate 区别",
         {"docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md"}),
        ("q044", "执行迹和变更日志两个白盒视图各展示什么",
         {"docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md"}),
        ("q052", "隐式关系候选怎么生成和核验，precision 多少",
         {"docs/only/recall/CONTENT_TO_GRAPH_20260811.md",
          "docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md"}),
    ]
    for qid, query, exp_docs in cases:
        exp_ids = {b["id"] for b in blocks if b["doc"] in exp_docs}
        print("=" * 78)
        print("[%s] %s" % (qid, query))
        vecs = np.stack([np.asarray(b["vector"], dtype=np.float32)
                         for b in blocks if b.get("vector") is not None])
        ids = [b["id"] for b in blocks if b.get("vector") is not None]
        for label, text in (("no-prefix", query),
                            ("zh-instr", INSTR_ZH + query),
                            ("en-instr", INSTR_EN + query)):
            qv = np.asarray(enc.encode([text], normalize=True)[0],
                            dtype=np.float32)
            sims = vecs @ qv
            order = np.argsort(sims)[::-1]
            rank = None
            for pos in range(30):
                if ids[order[pos]] in exp_ids:
                    rank = pos + 1
                    break
            print("  %-10s 期望块rank=%s (top1 sim=%.3f)" % (
                label, rank, float(sims[order[0]])))


if __name__ == "__main__":
    main()
