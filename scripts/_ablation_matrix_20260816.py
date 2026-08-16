#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""doc 域融合消融矩阵（2026-08-16, A18 消融驱动）:

对每组开关配置跑 eval_100（复用 scripts/eval_100._run）, 只打印
doc/dialogue 的 top1/top3/MRR/nDCG 摘要。组:
  0  baseline     （当前: rerank ON）
  1  rerank OFF   （DM_RERANK=0）
  2  route_unique （DM_ROUTE_UNIQUE=1）
  3  vec_gate     （DM_VEC_GATE=1）
  4  unique+gate  （组合）
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GROUPS = [
    ("baseline", {}),
    ("rerank_off", {"DM_RERANK": "0"}),
    ("route_unique", {"DM_ROUTE_UNIQUE": "1"}),
    ("vec_gate", {"DM_VEC_GATE": "1"}),
    ("unique+gate", {"DM_ROUTE_UNIQUE": "1", "DM_VEC_GATE": "1"}),
]


def main():
    import scripts.eval_100 as ev
    for name, env in GROUPS:
        for k, v in env.items():
            os.environ[k] = v
        stats, by_intent, _ = ev._run(rerank_on=True)
        print("==== %s ====" % name)
        for tag in ("dialogue", "doc"):
            s = stats[tag]
            n = s["n"] or 1
            print("  %-8s top1=%.1f%% top3=%.1f%% MRR=%.3f nDCG=%.3f "
                  "R@5=%.1f%%" % (
                      tag, 100.0 * s["top1"] / n, 100.0 * s["top3"] / n,
                      s["mrr"] / n, s["ndcg"] / n, 100.0 * s["r5"] / n))
        for k in list(env):
            os.environ.pop(k, None)


if __name__ == "__main__":
    main()
