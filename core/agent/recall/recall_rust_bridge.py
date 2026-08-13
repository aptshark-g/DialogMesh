# -*- coding: utf-8 -*-
"""recall_rs Rust 内核桥 — Rust 优先 + Python 回退（RECALL_RUST_DESIGN §三）。

与 persistence rust_bridge 同款模式: 检测 .pyd 编译产物, 有则 Rust 计算,
无则回退 Python（行为等价, 验收: 同测试集 py/rs 双实现一致）。

用法:
    from core.agent.recall.recall_rust_bridge import get_recall_kernel
    kernel = get_recall_kernel()   # → RustKernel | PythonKernel | None
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_RUST_AVAILABLE = None
_KERNEL = None


def _check_rust() -> bool:
    """检测 dialogmesh_recall 是否可导入（.pyd 编译产物）。"""
    global _RUST_AVAILABLE
    if _RUST_AVAILABLE is not None:
        return _RUST_AVAILABLE
    try:
        import importlib.util
        spec = importlib.util.find_spec("dialogmesh_recall")
        if spec is not None:
            _RUST_AVAILABLE = True
            logger.info("recall Rust kernel ACTIVE")
            return True
    except Exception:
        pass
    # 本地构建产物
    pyd_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "recall_rs", "target", "release")
    if os.path.isdir(pyd_dir):
        for f in os.listdir(pyd_dir):
            if f.startswith("dialogmesh_recall") and f.endswith((".pyd", ".so")):
                sys_path = os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                os.environ.setdefault("PYTHONPATH", "")
                import sys
                if pyd_dir not in sys.path:
                    sys.path.insert(0, pyd_dir)
                try:
                    import importlib
                    importlib.invalidate_caches()
                    importlib.import_module("dialogmesh_recall")
                    _RUST_AVAILABLE = True
                    logger.info("recall Rust kernel ACTIVE (local build)")
                    return True
                except Exception as e:
                    logger.debug("recall rust import failed: %s", e)
    _RUST_AVAILABLE = False
    return False


class RustKernel:
    """Rust 计算内核（cosine_topk / bm25 / coarse）。"""

    def __init__(self):
        import dialogmesh_recall as dr
        self._dr = dr

    def cosine_topk(self, vecs, dim: int, query, k: int) -> List[Tuple[int, float]]:
        return self._dr.cosine_topk(list(vecs), dim, list(query), k)

    def cosine_topk_bytes(self, data: bytes, dim: int,
                          query_bytes: bytes, k: int) -> List[Tuple[int, float]]:
        """零拷贝: numpy.tobytes() 直读（2026-08-11 优化, 省 list 转换）。"""
        return self._dr.cosine_topk_bytes(data, dim, query_bytes, k)

    def cosine_topk_buffer(self, vecs, dim: int, query, k: int
                           ) -> List[Tuple[int, float]]:
        """PyBuffer: numpy 数组直接提取（真零拷贝, 2026-08-11）。"""
        return self._dr.cosine_topk_buffer(vecs, dim, query, k)

    def bm25_scores(self, docs, df, n_docs, query_terms, k1, b,
                    doc_lens, avg_len) -> List[Tuple[int, float]]:
        return self._dr.bm25_scores(
            list(docs), list(df), n_docs, list(query_terms),
            k1, b, list(doc_lens), avg_len)

    def coarse_candidates(self, query_terms, docs) -> List[int]:
        return self._dr.coarse_candidates(list(query_terms), list(docs))


class PythonKernel:
    """Python 回退实现（行为等价, 慢）。"""

    def cosine_topk(self, vecs, dim: int, query, k: int) -> List[Tuple[int, float]]:
        import numpy as np
        arr = np.asarray(vecs, dtype=float).reshape(-1, dim)
        q = np.asarray(query, dtype=float)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        scores = arr @ q / (np.linalg.norm(arr, axis=1) * qn)
        idx = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in idx]

    def bm25_scores(self, docs, df, n_docs, query_terms, k1, b,
                    doc_lens, avg_len) -> List[Tuple[int, float]]:
        df_map = dict(df)
        agg = {}
        for doc, term, tf in docs:
            if term in query_terms:
                agg.setdefault(doc, []).append((term, tf))
        out = []
        for doc, terms in agg.items():
            norm = (doc_lens[doc] if doc < len(doc_lens) else avg_len) / max(avg_len, 1e-12)
            s = 0.0
            for term, tf in terms:
                df_t = df_map.get(term, 0)
                idf = math.log((n_docs - df_t + 0.5) / (df_t + 0.5) + 1.0)
                s += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * norm))
            out.append((doc, s))
        return out

    def coarse_candidates(self, query_terms, docs) -> List[int]:
        qset = set(query_terms)
        by_doc = {}
        for doc, term in docs:
            by_doc.setdefault(doc, []).append(term)
        return sorted(d for d, ts in by_doc.items() if any(t in qset for t in ts))


def get_recall_kernel() -> Optional[Any]:
    """Rust 优先; 未编译回退 PythonKernel（行为等价）。"""
    global _KERNEL
    if _KERNEL is not None:
        return _KERNEL
    if _check_rust():
        _KERNEL = RustKernel()
    else:
        _KERNEL = PythonKernel()
    return _KERNEL
