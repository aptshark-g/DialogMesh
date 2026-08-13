# -*- coding: utf-8 -*-
"""召回确定性核查（2026-08-12）: 同 query 同服务跑 3 次, 融合顺序是否稳定。

用法: .venv/Scripts/python.exe scripts/_recall_determinism_check.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service


def main():
    gold = load_goldset()
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="rrf")
    flipped = 0
    for qi in gold["queries"]:
        orders = []
        for _ in range(3):
            res = svc.recall(qi["query"], top_k=20, use_hyde=False)
            orders.append(tuple(h.id for h in res.hits[:5]))
        if len(set(orders)) > 1:
            flipped += 1
            print("不稳定: %s" % qi["query"][:40])
            for o in orders:
                print("   ", [i[:30] for i in o[:3]])
    print("39 条中不稳定:", flipped)


if __name__ == "__main__":
    main()
