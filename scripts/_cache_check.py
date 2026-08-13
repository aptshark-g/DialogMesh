# -*- coding: utf-8 -*-
"""确认 G0 缓存命中: 第二次 ensure_global_blocks 是否秒级（2026-08-12）。"""
import os
import sys
import time

sys.path.insert(0, ".")


def main():
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    import scripts.doc_recall_bench as drb
    from scripts.recall_goldset import build_service
    doc_blocks = drb.load_blocks()
    drb.prepare_vectors(doc_blocks)
    svc = build_service(doc_blocks, mode="rrf")
    t0 = time.time()
    blocks = svc._ensure_global_blocks()
    dt = time.time() - t0
    print("第二次 ensure_global_blocks: %.1fs (%d 块)" % (dt, len(blocks)))
    # 缓存文件大小
    for f in ["data/recall_index/global.json"]:
        if os.path.exists(f):
            print("%s: %.1f MB" % (f, os.path.getsize(f) / 1024 / 1024))
    # 单 query BM25 单独计时
    svc.single_source = "bm25"
    t0 = time.time()
    r = svc.recall("执行层怎么分层", top_k=10, use_hyde=False)
    print("BM25-only recall: %.1fs hits=%d" % (time.time() - t0, len(r.hits)))
    svc.single_source = None
    t0 = time.time()
    r = svc.recall("执行层怎么分层", top_k=10, use_hyde=False)
    print("全路 recall: %.1fs hits=%d" % (time.time() - t0, len(r.hits)))


if __name__ == "__main__":
    main()
