# -*- coding: utf-8 -*-
"""query 意图 miss 分析: 实际召回 vs 期望块（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset, build_service


ZONE_FALLBACK = {
    "ATOMIC": "task", "PRECISION": "task",
    "EXPLORE": "query", "ABYSS": "discussion",
    "PSYCHE": "discussion", "MIXED": "query",
}


def main():
    from core.agent.pcr_router_v2 import PCRRouterV2
    gold = load_goldset()
    blocks = {b["id"]: b["text"] for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
         for b in gold["blocks"]], mode="rrf")
    out = []
    shown = 0
    for qi in gold["queries"]:
        try:
            zone = PCRRouterV2.route(qi["query"]).zone
        except Exception:
            zone = "MIXED"
        if ZONE_FALLBACK.get(zone) != "query":
            continue
        res = svc.recall(qi["query"], top_k=10, use_hyde=False)
        hit10 = any(h.id in qi["expected"] for h in res.hits[:10])
        if hit10:
            continue
        out.append("Q: %s" % qi["query"][:60])
        out.append("  期望块: %s" % qi["expected"][:4])
        for h in res.hits[:4]:
            txt = blocks.get(h.id, "?")[:80].replace("\n", " ")
            out.append("  实际[%s]: %s" % (h.id, txt))
        out.append("")
        shown += 1
        if shown >= 10:
            break
    with open("_query_miss.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) or "无 miss")
    print("done, shown=%d" % shown)


if __name__ == "__main__":
    main()
