# -*- coding: utf-8 -*-
"""BM25 接 Rust 验证（2026-08-12）: 双内核等价 + 生产路径冒烟 + 性能。

用法: .venv/Scripts/python.exe scripts/_bm25_rust_verify.py
"""
import sys, time, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.recall.recall_rust_bridge import RustKernel, PythonKernel, get_recall_kernel


def main():
    kernel = get_recall_kernel()
    print("内核类型:", type(kernel).__name__)

    # ── 1. 双内核等价（同一稀疏索引）────────────────────────────
    docs = [(0, 1, 2), (1, 1, 1), (1, 2, 1), (2, 3, 3), (3, 1, 1), (3, 4, 2)]
    df = [(1, 3), (2, 1), (3, 1), (4, 1)]
    lens = [4.0, 3.0, 5.0, 4.0]
    avg = 4.0
    rs = RustKernel()
    py = PythonKernel()
    for q in ([1], [1, 2], [4], [1, 3]):
        r = sorted(rs.bm25_scores(docs, df, 4, q, 1.2, 0.75, lens, avg))
        p = sorted(py.bm25_scores(docs, df, 4, q, 1.2, 0.75, lens, avg))
        same = len(r) == len(p) and all(
            abs(a[1] - b[1]) < 1e-9 for a, b in zip(r, p))
        print("query=%s 等价=%s  rust=%s" % (q, same, r[:3]))
        if not same:
            print("  rust:", r)
            print("  py  :", p)
        assert same, "Rust/Python BM25 不一致!"

    # ── 2. 生产路径冒烟（15 块中文）─────────────────────────────
    from scripts.recall_goldset import build_service
    texts = [
        "DialogMesh 召回服务使用 BGE 向量与 BM25 混合锚点",
        "蓝图系统负责宏观规划, 执行层 tool_loop 做微观执行",
        "内容到图转换模块解析 Obsidian 双链并核验隐式关系",
        "持久化分层: 热内存、温文件、冷原文重建",
        "权限系统按 C1 到 C4 四级风险分级拦截链式命令",
        "网关聚合九家模型厂商并支持断路器与加权路由",
        "元认知仲裁监控任务图的健康度并介入异常回合",
        "二阶抽象提炼管道从行为链蒸馏启发式公理",
        "切分修复后结构块保留代码与 JSON 整体不截断",
        "Rust 内核用 PyBuffer 零拷贝实现批量余弦打分",
        "子图扩展采用 DAG 分层局部扩展并同步剪枝",
        "评测面板统一展示召回率与幻觉率等量化指标",
        "时序约束按文档新旧对召回结果做半衰期降权",
        "图导航 API 提供邻居、调用方与路径 BFS 查询",
        "推理空间调度器负责冷启动预热与优先级管理",
    ]
    svc = build_service(
        [{"id": "t%02d" % i, "text": t, "session": "s1"}
         for i, t in enumerate(texts)], mode="rrf")
    t0 = time.time()
    hits = svc._bm25_anchors("蓝图 执行层 tool_loop 微观执行", 3)
    dt = (time.time() - t0) * 1000
    print("冒烟: %.1fms hits=%d -> %s" % (dt, len(hits),
          [h.id for h in hits]))
    assert hits, "BM25 生产路径空结果!"

    # ── 3. 文档池性能（11489 块: 索引构建 + 单 query）──────────
    import scripts.doc_recall_bench as drb
    blocks = drb.load_blocks()
    print("文档块:", len(blocks))
    t0 = time.time()
    svc2 = build_service(
        [{"id": b["id"], "text": b["text"], "session": ""} for b in blocks],
        mode="rrf")
    svc2._ensure_blocks()
    idx = svc2._bm25_index(svc2._block_list)
    t_idx = time.time() - t0
    t0 = time.time()
    hits2 = svc2._bm25_anchors("蓝图 执行层 tool_loop 微观执行", 5)
    t_q1 = (time.time() - t0) * 1000
    t0 = time.time()
    svc2._bm25_anchors("蓝图 执行层 tool_loop 微观执行", 5)
    t_q2 = (time.time() - t0) * 1000
    t0 = time.time()
    svc2._bm25_anchors("评测 幻觉率 量化指标 面板", 5)
    t_q3 = (time.time() - t0) * 1000
    print("索引构建: %.1fs | query1: %.1fms | query2: %.1fms | query3: %.1fms hits=%d" % (
        t_idx, t_q1, t_q2, t_q3, len(hits2)))
    print("top5:", [h.id[:60] for h in hits2])


if __name__ == "__main__":
    main()
