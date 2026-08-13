# -*- coding: utf-8 -*-
"""task 意图 query 构成分析（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset


ZONE_FALLBACK = {
    "ATOMIC": "task", "PRECISION": "task",
    "EXPLORE": "query", "ABYSS": "discussion",
    "PSYCHE": "discussion", "MIXED": "query",
}


def main():
    from core.agent.pcr_router_v2 import PCRRouterV2
    gold = load_goldset()
    out = []
    for qi in gold["queries"]:
        try:
            zone = PCRRouterV2.route(qi["query"]).zone
        except Exception:
            zone = "MIXED"
        if ZONE_FALLBACK.get(zone) == "task":
            out.append("[%s] %s -> %d块" % (
                zone, qi["query"][:55], len(qi["expected"])))
    with open("_task_queries.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done, n=%d" % len(out))


if __name__ == "__main__":
    main()
