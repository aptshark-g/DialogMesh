# -*- coding: utf-8 -*-
"""Rust 内核细粒度剖析: 转换 vs 计算, 单线程 vs rayon（2026-08-11）。"""
import os
import sys
import time

sys.path.insert(0, ".")


def main():
    import numpy as np
    from core.agent.recall.recall_rust_bridge import get_recall_kernel, RustKernel
    kernel = get_recall_kernel()
    assert isinstance(kernel, RustKernel)
    rng = np.random.default_rng(1)
    N, DIM = 378, 1024
    vecs = rng.normal(size=(N, DIM)).astype(np.float64)
    q = rng.normal(size=DIM).astype(np.float64)
    out = []

    # 1. PyBuffer 零拷贝版（2026-08-11 优化后）
    t0 = time.time()
    for _ in range(20):
        kernel.cosine_topk_buffer(vecs, DIM, q, 10)
    total = (time.time() - t0) / 20
    out.append("Rust PyBuffer 零拷贝: %.3f ms" % (total * 1000))

    # 2. 转换本身（Python 侧 list 构造）
    t0 = time.time()
    for _ in range(20):
        _ = vecs.flatten().tolist()
    conv = (time.time() - t0) / 20
    out.append("numpy→list 转换: %.2f ms" % (conv * 1000))

    # 3. numpy 全向量化（生产 Python 真实路径: 一次矩阵乘）
    qn = np.linalg.norm(q)
    t0 = time.time()
    for _ in range(50):
        sims = vecs @ q / (np.linalg.norm(vecs, axis=1) * qn)
    np_t = (time.time() - t0) / 50
    out.append("numpy 矩阵乘: %.3f ms" % (np_t * 1000))

    # 4. Python 逐块（_cosine 循环, 生产原路径）
    t0 = time.time()
    for _ in range(5):
        for v in vecs:
            _ = float(v @ q / (np.linalg.norm(v) * qn))
    loop_t = (time.time() - t0) / 5
    out.append("Python 逐块循环: %.2f ms" % (loop_t * 1000))

    with open("docs/test/RUST_PROF_20260811.md", "w", encoding="utf-8") as f:
        f.write("# Rust 内核剖析（378 块, 2026-08-11）\n\n")
        f.write("\n".join("- " + line for line in out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
