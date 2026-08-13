# -*- coding: utf-8 -*-
"""测量 pyo3 转换开销 vs 计算开销（2026-08-11）。"""
import os
import sys
import time

sys.path.insert(0, ".")


def main():
    import numpy as np
    from core.agent.recall.recall_rust_bridge import (
        get_recall_kernel, RustKernel)
    kernel = get_recall_kernel()  # 触发 .pyd 路径注入
    assert isinstance(kernel, RustKernel), "Rust 内核未激活"
    rng = np.random.default_rng(42)
    N, DIM = 10969, 1024
    vecs = rng.normal(size=(N, DIM)).astype(np.float64)
    query = rng.normal(size=DIM).astype(np.float64)
    flat = vecs.flatten().tolist()
    q = query.tolist()
    kernel = RustKernel()
    out = []

    # 1. 纯转换（list → 函数调用, 不计算）
    t0 = time.time()
    for _ in range(3):
        kernel.cosine_topk(flat, DIM, q, 10)
    total = (time.time() - t0) / 3
    out.append("含转换总耗时: %.1f ms" % (total * 1000))

    # 2. 小数据（10 块）: 转换固定成本 + 计算微小
    small = vecs[:10].flatten().tolist()
    t0 = time.time()
    for _ in range(10):
        kernel.cosine_topk(small, DIM, q, 5)
    small_t = (time.time() - t0) / 10
    out.append("10 块耗时（≈转换固定成本）: %.1f ms" % (small_t * 1000))

    # 3. f64 vs f32 计算对比（numpy 内, 纯计算）
    v32 = vecs.astype(np.float32)
    q32 = query.astype(np.float32)
    t0 = time.time()
    for _ in range(5):
        (v32 @ q32)
    t32 = (time.time() - t0) / 5
    t0 = time.time()
    for _ in range(5):
        (vecs @ query)
    t64 = (time.time() - t0) / 5
    out.append("numpy f32 点积: %.1f ms | f64: %.1f ms (f32 快 %.0f%%)" % (
        t32 * 1000, t64 * 1000, 100 * (1 - t32 / t64)))

    with open("docs/test/RUST_OVERHEAD_20260811.md", "w", encoding="utf-8") as f:
        f.write("# Rust 内核开销分析（2026-08-11）\n\n")
        f.write("\n".join("- " + line for line in out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
