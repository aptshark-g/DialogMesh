# -*- coding: utf-8 -*-
"""eval_100 小样本诊断: 3 query 实测各环节耗时, 外推全量（2026-08-12）。"""
import os
import sys
import time

sys.path.insert(0, ".")


def main():
    import scripts.doc_recall_bench as drb
    from scripts.recall_goldset import build_service

    # 1. 文档块加载 + 预编码计时
    t0 = time.time()
    doc_blocks = drb.load_blocks()
    t_load = time.time() - t0
    print("load_blocks: %.1fs (%d 块)" % (t_load, len(doc_blocks)))
    t0 = time.time()
    drb.prepare_vectors(doc_blocks)
    t_vec = time.time() - t0
    print("prepare_vectors: %.1fs" % t_vec)

    # 2. service 构建 + 首次 ensure_global 计时（SPO 提取）
    t0 = time.time()
    svc = build_service(doc_blocks, mode="rrf")
    t_build = time.time() - t0
    print("build_service: %.1fs" % t_build)
    t0 = time.time()
    blocks = svc._ensure_global_blocks()
    t_ensure = time.time() - t0
    print("ensure_global_blocks(首次, SPO): %.1fs (%d 块)" % (
        t_ensure, len(blocks)))

    # 3. 单 query recall 计时（3 条文档 query）
    queries = ["执行层怎么分层？tool_loop 和蓝图、元认知是什么关系",
               "内容怎么转化成图，Obsidian 双链和 frontmatter 怎么利用",
               "存储分层 H/W/C/A 怎么升降，阈值多少"]
    for q in queries:
        t0 = time.time()
        res = svc.recall(q, top_k=20, use_hyde=False)
        dt = time.time() - t0
        print("recall(%.30s): %.2fs hits=%d" % (q, dt, len(res.hits)))


if __name__ == "__main__":
    main()
