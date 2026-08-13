#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生产路径真实对比: _vector_anchors Rust vs Python（2026-08-11）。

同一 goldset 块池, 同一 query, 只切换 Rust 内核开关, 测 _vector_anchors
真实耗时（含 embed 缓存命中后的纯打分路径）。
用法: .venv\\Scripts\\python.exe scripts/recall_prod_bench.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from scripts.recall_goldset import load_goldset, build_service
    from core.agent.recall.recall_rust_bridge import _check_rust, _RUST_AVAILABLE
    gold = load_goldset()
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    queries = [q["query"] for q in gold["queries"][:10]]
    rust_on = _check_rust()
    print("Rust 内核: %s" % ("ACTIVE" if rust_on else "回退 Python"))

    svc = build_service(blocks, mode="rrf")
    # 预热: 全量 embed（首跑慢, 不计时）
    svc._ensure_global_blocks()
    for q in queries[:2]:
        svc._vector_anchors(q, 10)

    # 计时（缓存命中后的纯打分路径）
    t0 = time.time()
    for q in queries:
        svc._vector_anchors(q, 10)
    t_rs = (time.time() - t0) / len(queries)
    print("_vector_anchors（%s）: %.1f ms/query" % (
        "Rust" if rust_on else "Python", t_rs * 1000))

    # 禁用 Rust 对比（强制 Python 路径）
    import core.agent.recall.recall_service as rs_mod
    from core.agent.recall.recall_service import RecallHit
    orig = rs_mod.RecallService._vector_anchors

    def py_vector(self, query, top_k, blocks=None):
        """临时 Python 版（不接 Rust）: 原逻辑逐块余弦 + 完整 hit 构造。"""
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        qv = self._embed(query)
        scored = []
        for b in blocks:
            bid = b["id"]
            ev = self._embeddings.get(bid)
            if ev is None:
                cached_vec = b.get("vector")
                if cached_vec is not None and len(cached_vec) == len(qv):
                    ev = cached_vec
                    self._embeddings[bid] = ev
            if ev is None:
                score_text = (b.get("summary") or "").strip() or b["text"]
                ev = self._embed(score_text)
                if ev is None:
                    continue
                self._embeddings[bid] = ev
            if ev is None:
                continue
            sim = self._cosine(qv, ev)
            if sim > 0.3:
                scored.append((sim, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for sim, b in scored[:top_k]:
            hits.append(RecallHit(
                id=b["id"], text=b["text"][:200], source="vector",
                score=sim, confidence=self._confidence("vector"),
                temperature=b["temperature"],
                path=b.get("path") or [],
                created_at=b.get("created_at"),
            ))
        return hits

    try:
        rs_mod.RecallService._vector_anchors = py_vector
        svc2 = build_service(blocks, mode="rrf")
        svc2._ensure_global_blocks()
        for q in queries[:2]:
            svc2._vector_anchors(q, 10)
        t0 = time.time()
        for q in queries:
            svc2._vector_anchors(q, 10)
        t_py = (time.time() - t0) / len(queries)
        print("_vector_anchors（Python 逐块）: %.1f ms/query" % (t_py * 1000))
        if rust_on:
            print("生产路径提速: %.1fx" % (t_py / t_rs))
    finally:
        rs_mod.RecallService._vector_anchors = orig


if __name__ == "__main__":
    main()
