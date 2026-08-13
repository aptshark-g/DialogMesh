#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""recall_rs Rust vs Python 性能对比（2026-08-11, 验收门槛）。

模拟全库余弦 top-k（10969 块 × 1024 维）: py vs rs 数字一致 + 时间对比。
用法: .venv\\Scripts\\python.exe scripts/recall_rust_bench.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.recall.recall_rust_bridge import (
    get_recall_kernel, RustKernel, PythonKernel, _check_rust)


def main():
    import numpy as np
    rng = np.random.default_rng(42)
    N, DIM = 10969, 1024
    vecs = rng.normal(size=(N, DIM)).astype(np.float64)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    query = rng.normal(size=DIM).astype(np.float64)
    query /= np.linalg.norm(query)
    K = 10

    rust_on = _check_rust()
    print("Rust 内核: %s" % ("ACTIVE" if rust_on else "回退 Python"))
    flat = vecs.flatten().tolist()
    q = query.tolist()

    # Rust
    if rust_on:
        kernel = RustKernel()
        t0 = time.time()
        rs = kernel.cosine_topk(flat, DIM, q, K)
        t_rs = time.time() - t0
        print("Rust cosine_topk: %.1f ms" % (t_rs * 1000))
        rs_ids = [i for i, _ in rs]

    # Python（numpy 向量化, 最接近生产实现）
    kernel_py = PythonKernel()
    t0 = time.time()
    ps = kernel_py.cosine_topk(flat, DIM, q, K)
    t_py = time.time() - t0
    print("Python cosine_topk: %.1f ms" % (t_py * 1000))
    py_ids = [i for i, _ in ps]

    if rust_on:
        same = rs_ids == py_ids
        print("结果一致: %s" % same)
        print("提速: %.0fx" % (t_py / t_rs))
        # 一致性断言（验收门槛: py/rs 行为等价）
        assert same, "py/rs top-k 不一致!"


if __name__ == "__main__":
    main()
