#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PRF 全量消融（2026-08-16, A18）: alpha/fb 参数网格。
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GROUPS = [
    ("baseline", {}),
    ("prf_a0.5_fb3", {"DM_PRF": "1", "DM_PRF_ALPHA": "0.5",
                      "DM_PRF_FB": "3"}),
    ("prf_a0.7_fb3", {"DM_PRF": "1", "DM_PRF_ALPHA": "0.7",
                      "DM_PRF_FB": "3"}),
    ("prf_a0.5_fb5", {"DM_PRF": "1", "DM_PRF_ALPHA": "0.5",
                      "DM_PRF_FB": "5"}),
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
