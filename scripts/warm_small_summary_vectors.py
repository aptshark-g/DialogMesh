#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预热 small 策略文件摘要向量（2026-08-14, B 尾巴消融前置）。

small 摘要（qwen3.5-9b 生成, 已缓存 478 条）→ BGE 批量编码 →
落盘 doc_file_summaries_vectors.json（带 _strategy=small 标记）。
用法: .venv\\Scripts\\python.exe scripts/warm_small_summary_vectors.py
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.recall.doc_corpus import load_file_summaries

OUT = os.path.join("data", "recall_index",
                   "doc_file_summaries_vectors.json")


def main():
    summaries = load_file_summaries(strategy="small")
    print("small summaries:", len(summaries), flush=True)
    if not summaries:
        return 1
    from core.agent.compiler.semantic_encoder import get_encoder
    enc = get_encoder()
    docs = list(summaries.keys())
    texts = [summaries[d][:1000] for d in docs]
    t0 = time.time()
    vecs = enc.encode(texts, batch_size=32, normalize=True)
    out = {d: (v.tolist() if hasattr(v, "tolist") else list(v))
           for d, v in zip(docs, vecs)}
    out["_strategy"] = "small"
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"written {len(docs)} vectors -> {OUT} ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
