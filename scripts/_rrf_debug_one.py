# -*- coding: utf-8 -*-
"""RRF 单 query 调试（2026-08-12）: 打印各源命中排名与融合分数。

用法: .venv/Scripts/python.exe scripts/_rrf_debug_one.py [query_index]
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service


def main():
    gold = load_goldset()
    # 扫描: 找 cap=0 命中 top1 但 cap=5 未命中的 query
    qi = int(sys.argv[1]) if len(sys.argv) > 1 else -1
    if qi >= 0:
        _debug_one(gold, qi)
        return
    for cap in (0, 5):
        svc = build_service(
            [{"id": b["id"], "text": b["text"],
              "session": b.get("session", ""),
              "vector": b.get("vector")}
             for b in gold["blocks"]], mode="rrf")
        svc.rrf_rank_cap = cap
        for qi2, q in enumerate(gold["queries"]):
            res = svc.recall(q["query"], top_k=20, use_hyde=False)
            exp = set(q["expected"])
            hit_rank = next(
                (i for i, h in enumerate(res.hits, 1) if h.id in exp), None)
            print("cap=%d q=%d rank=%s %s" % (
                cap, qi2, hit_rank, q["query"][:30]))


def _debug_one(gold, qi):
    q = gold["queries"][qi]
    print("query[%d]: %s" % (qi, q["query"]))
    print("expected:", q["expected"])
    for cap in (0, 5):
        svc = build_service(
            [{"id": b["id"], "text": b["text"],
              "session": b.get("session", ""),
              "vector": b.get("vector")}
             for b in gold["blocks"]], mode="rrf")
        svc.rrf_rank_cap = cap
        res = svc.recall(q["query"], top_k=20, use_hyde=False)
        print("\n--- cap=%d ---" % cap)
        for i, h in enumerate(res.hits[:10], 1):
            hit = "  <== EXPECTED" if h.id in q["expected"] else ""
            print("  #%d [%s] %.4f %s%s" % (
                i, h.source, h.score, h.id[:50], hit))
        # 期望块在各源内的排名
        print("  expected 各源内排名:")
        for h in res.hits:
            pass
        # 直接重算: 期望块出现在哪些源的哪些位置
        exp = set(q["expected"])
        from collections import defaultdict
        by_source = defaultdict(list)
        svc2 = build_service(
            [{"id": b["id"], "text": b["text"],
              "session": b.get("session", ""),
              "vector": b.get("vector")}
             for b in gold["blocks"]], mode="rrf")
        svc2.rrf_rank_cap = cap
        hot = svc2._ensure_blocks(None)
        cold = svc2._ensure_global_blocks()
        for tag, blocks in (("hot", hot), ("cold", cold)):
            for src, fn in (("vector", svc2._vector_anchors),
                            ("bm25", svc2._bm25_anchors),
                            ("spo", svc2._spo_anchors)):
                hs = fn(q["query"], 20, blocks=blocks)
                by_source["%s:%s" % (tag, src)] = hs
        for src, hs in by_source.items():
            for rank, h in enumerate(hs):
                if h.id in exp:
                    print("    %s rank=%d score=%.4f" % (
                        src, rank + 1, h.score))


if __name__ == "__main__":
    main()
