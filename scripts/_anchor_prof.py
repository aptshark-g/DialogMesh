# -*- coding: utf-8 -*-
"""单 query 锚点耗时分布（2026-08-12）: vector/bm25/spo 各自耗时。"""
import logging
import os
import sys
import time

sys.path.insert(0, ".")


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    import scripts.doc_recall_bench as drb
    from scripts.recall_goldset import build_service
    doc_blocks = drb.load_blocks()
    drb.prepare_vectors(doc_blocks)
    svc = build_service(doc_blocks, mode="rrf")
    svc._ensure_global_blocks()
    q = "执行层怎么分层？tool_loop 和蓝图、元认知是什么关系"
    t0 = time.time()
    res = svc.recall(q, top_k=10, use_hyde=False)
    print("recall 总计: %.1fs hits=%d" % (time.time() - t0, len(res.hits)))


if __name__ == "__main__":
    main()
