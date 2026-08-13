# -*- coding: utf-8 -*-
"""召回各路线耗时剖析（2026-08-12）: 定位 doc 域 15s/query 的构成。

用法: .venv/Scripts/python.exe scripts/_recall_route_timing.py
"""
import sys, time, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.doc_recall_bench as drb
from scripts.recall_goldset import build_service


def main():
    blocks = drb.load_blocks()
    print("文档块:", len(blocks))
    drb.prepare_vectors(blocks)
    print("向量准备完成")
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in blocks],
        mode="rrf")
    t0 = time.time()
    svc._ensure_blocks()
    svc._ensure_global_blocks()
    print("块池初始化: %.1fs" % (time.time() - t0))

    q = "蓝图 执行层 tool_loop 微观执行 是怎么接线的"
    for label, fn in (
        ("vector", lambda: svc._vector_anchors(q, 5)),
        ("bm25", lambda: svc._bm25_anchors(q, 5)),
        ("spo", lambda: svc._spo_anchors(q, 5)),
    ):
        t0 = time.time()
        hits = fn()
        t1 = time.time() - t0
        t0 = time.time()
        hits2 = fn()
        t2 = time.time() - t0
        print("%s: 首次 %.1fms | 二次 %.1fms | hits=%d | top=%s" % (
            label, t1 * 1000, t2 * 1000, len(hits),
            [h.id[:40] for h in hits[:2]]))

    for i in range(3):
        t0 = time.time()
        res = svc.recall(q, top_k=20, use_hyde=False)
        print("recall() 全链路 #%d: %.1fms hits=%d" % (
            i + 1, (time.time() - t0) * 1000, len(res.hits)))
    res = svc.recall(q, top_k=20, use_hyde=False)
    for h in res.hits[:5]:
        print("  [%s %.2f] %s" % (h.source, h.score, h.id[:60]))


if __name__ == "__main__":
    main()
