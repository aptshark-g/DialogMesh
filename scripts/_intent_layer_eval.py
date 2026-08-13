# -*- coding: utf-8 -*-
"""意图分层评测（2026-08-11）: PCR zone → intent_category 分层跑现状 Recall@k。

目的: 用户"根据意图调整召回方案, 先测试" — 先看各意图现状差异,
数据说话再定调参, 防小样本过拟合。
"""
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
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    svc = build_service(blocks, mode="rrf")
    layers = {}
    for qi in gold["queries"]:
        try:
            zone = PCRRouterV2.route(qi["query"]).zone
        except Exception:
            zone = "MIXED"
        intent = ZONE_FALLBACK.get(zone, "query")
        layers.setdefault(intent, []).append(qi)

    out = []
    out.append("意图分层（PCR zone → intent_category, 82 query）:")
    for intent, qs in sorted(layers.items(), key=lambda kv: -len(kv[1])):
        r5 = r10 = t1 = 0
        for qi in qs:
            res = svc.recall(qi["query"], top_k=10, use_hyde=False)
            hit10 = any(h.id in qi["expected"] for h in res.hits[:10])
            hit5 = any(h.id in qi["expected"] for h in res.hits[:5])
            t1 += bool(res.hits and res.hits[0].id in qi["expected"])
            r5 += hit5
            r10 += hit10
        n = len(qs)
        out.append("  %-12s n=%-3d top1=%.0f%% R@5=%.0f%% R@10=%.0f%%" % (
            intent, n, 100.0 * t1 / n, 100.0 * r5 / n, 100.0 * r10 / n))
    # zone 分布
    zones = {}
    for qi in gold["queries"]:
        try:
            z = PCRRouterV2.route(qi["query"]).zone
        except Exception:
            z = "MIXED"
        zones[z] = zones.get(z, 0) + 1
    out.append("zone 分布: %s" % dict(sorted(zones.items(), key=lambda kv: -kv[1])))
    with open("_intent_eval.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
