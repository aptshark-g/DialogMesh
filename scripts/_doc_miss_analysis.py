# -*- coding: utf-8 -*-
"""doc 域 61 条逐条归因（2026-08-12）: 融合排名 vs 各路线内最佳排名。

分类:
  A 融合命中（rank<=20 且文件匹配）
  B 期望块在某路线 top-20 但被融合挤出（融合问题）
  C 期望块在任何路线 top-20 都没有（检索缺口）
输出 docs/test/DOC_MISS_ANALYSIS_20260812.md

用法: .venv/Scripts/python.exe scripts/_doc_miss_analysis.py
"""
import sys, os, time, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import build_service
from scripts.query_set import load_query_set
import scripts.doc_recall_bench as drb


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in blocks], mode="rrf")
    svc._ensure_blocks()
    svc._ensure_global_blocks()
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    queries = load_query_set("docs/test/recall_queries_100.md")
    doc_qs = [q for q in queries
              if not q["expected"][0].startswith("goldset:")]
    print("doc queries:", len(doc_qs))

    rows = []
    t0_all = time.time()
    for qi in doc_qs:
        q = qi["query"]
        exp_files = [e.strip() for e in qi["expected"][0].split(";") if e.strip()]
        exp_ids = set()
        for f in exp_files:
            exp_ids.update(file_to_ids.get(f, {f}))
        t0 = time.time()
        res = svc.recall(q, top_k=20, use_hyde=False)
        fused_rank = next(
            (i for i, h in enumerate(res.hits, 1) if h.id in exp_ids), None)
        # 各路线内最佳排名（hot 池）
        hot = svc._block_list
        route_best = {}
        for src, fn in (("vector", svc._vector_anchors),
                        ("bm25", svc._bm25_anchors),
                        ("spo", svc._spo_anchors)):
            hs = fn(q, 20, blocks=hot)
            best = next((i for i, h in enumerate(hs, 1) if h.id in exp_ids),
                        None)
            route_best[src] = best
        cls = ("A" if fused_rank is not None else
               "B" if any(v is not None for v in route_best.values()) else "C")
        rows.append({
            "query": q, "files": exp_files,
            "fused_rank": fused_rank, "route_best": route_best,
            "cls": cls, "ms": (time.time() - t0) * 1000,
            "n_exp_sections": len(exp_ids),
        })
        print("  [%s] rank=%s vec=%s bm25=%s spo=%s | %.0fms | %s" % (
            cls, fused_rank, route_best["vector"], route_best["bm25"],
            route_best["spo"], (time.time() - t0) * 1000, q[:34]))

    by_cls = {}
    for r in rows:
        by_cls.setdefault(r["cls"], []).append(r)
    print("\n分类: A(融合命中)=%d  B(在路线内但被挤出)=%d  C(检索缺口)=%d"
          % (len(by_cls.get("A", [])), len(by_cls.get("B", [])),
             len(by_cls.get("C", []))))
    print("总耗时 %.0fs | 平均 %.0fms/query" % (
        time.time() - t0_all,
        (time.time() - t0_all) / len(doc_qs) * 1000))

    out = ["# doc 域 61 条逐条归因（2026-08-12）", "",
           "- 窗口 top-20; A=融合命中 B=路线内命中但融合挤出 C=检索缺口",
           "- 平均 %.0f ms/query" % ((time.time() - t0_all) / len(doc_qs) * 1000),
           ""]
    for r in rows:
        out.append("- [%s] rank=%s | vec=%s bm25=%s spo=%s | %s" % (
            r["cls"], r["fused_rank"], r["route_best"]["vector"],
            r["route_best"]["bm25"], r["route_best"]["spo"], r["query"]))
    with open("docs/test/DOC_MISS_ANALYSIS_20260812.md", "w",
              encoding="utf-8") as f:
        f.write("\n".join(out))
    print("written: docs/test/DOC_MISS_ANALYSIS_20260812.md")


if __name__ == "__main__":
    main()
