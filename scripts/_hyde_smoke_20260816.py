#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""真 HyDE 冒烟（2026-08-16）: B 类 miss 上用 HyDE K=3 + 门控对比。
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
    os.environ["DM_HYDE"] = "1"
    os.environ["DM_HYDE_K"] = "3"
    os.environ["DM_HYDE_GATE"] = "1"
    from core.agent.api.v3_session_api import _GatewayLLMAdapter
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(blocks, mode="vector_primary")
    svc._llm = _GatewayLLMAdapter()
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    cases = [
        ("agentic 工具节点怎么让 LLM 自己调工具",
         ["docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md",
          "docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md"]),
        ("决策事件有哪些 kind，strategy_switch 和 plan_gate 区别",
         ["docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md"]),
        ("执行迹和变更日志两个白盒视图各展示什么",
         ["docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md"]),
        ("隐式关系候选怎么生成和核验，precision 多少",
         ["docs/only/recall/CONTENT_TO_GRAPH_20260811.md",
          "docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md"]),
    ]
    for query, exp_files in cases:
        exp = set()
        for e in exp_files:
            exp |= file_to_ids.get(e, set())
        res = svc.recall(query, intent="记忆召回", top_k=20, use_hyde=True)
        rank = next((i + 1 for i, h in enumerate(res.hits)
                     if h.id in exp), None)
        hyde_n = sum(1 for h in res.hits if h.source == "hyde")
        print("fused_rank=%s hyde_top20=%d | %s" % (
            rank, hyde_n, query[:30]))


if __name__ == "__main__":
    main()
