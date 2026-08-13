# -*- coding: utf-8 -*-
"""C 类 6 条深查（2026-08-12）: 期望文件块在向量/BM25 全量排名中的位置。

用法: .venv/Scripts/python.exe scripts/_doc_c_rank_deep.py
"""
import sys, os, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import build_service
from scripts.query_set import load_query_set
import scripts.doc_recall_bench as drb

C_QUERY_TERMS = [
    "agentic 工具节点怎么让 LLM 自己调工具",
    "执行层监控 Hot Warm Cold 分别做什么",
    "蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据",
    "技能生命周期怎么做活性管理的",
    "第一版发布前还差哪些，前端绑定和量化测试优先级",
    "隐式关系候选怎么生成和核验，precision 多少",
]


def main():
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in blocks], mode="rrf")
    hot = svc._ensure_blocks()
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    queries = load_query_set("docs/test/recall_queries_100.md")
    for q in queries:
        if not q["query"] in C_QUERY_TERMS:
            continue
        exp_files = [e.strip() for e in q["expected"][0].split(";")
                     if e.strip()]
        exp_ids = set()
        for f in exp_files:
            exp_ids.update(file_to_ids.get(f, {f}))
        print("\nQ: %s" % q["query"])
        # 向量全量排名（不截断）
        t0 = time.time()
        vh = svc._vector_anchors(q["query"], len(hot), blocks=hot)
        vrank = next((i for i, h in enumerate(vh, 1) if h.id in exp_ids), None)
        vtop = [h.id for h in vh[:5]]
        print("  vector 全量 %d 块: 期望文件首现 rank=%s (%.0fms)" % (
            len(vh), vrank, (time.time() - t0) * 1000))
        # BM25 全量排名
        t0 = time.time()
        bh = svc._bm25_anchors(q["query"], len(hot), blocks=hot)
        brank = next((i for i, h in enumerate(bh, 1) if h.id in exp_ids), None)
        print("  bm25   全量 %d 块: 期望文件首现 rank=%s (%.0fms)" % (
            len(bh), brank, (time.time() - t0) * 1000))
        # 期望文件的前 3 块标题 + 该文件所有块在向量 top-100 里的分布
        exp_blocks = [b for b in blocks if b["id"] in exp_ids]
        print("  期望文件 %d 块, 标题样例:" % len(exp_blocks))
        for b in exp_blocks[:3]:
            print("    -", (b["id"].split("#")[-1] or "file")[:36], "|",
                  b["text"][:50].replace("\n", " "))
        print("  向量 top-10 块:")
        for h in vh[:10]:
            print("    %d [%.3f] %s" % (vh.index(h) + 1, h.score,
                                        h.id.split("#")[-1][:36]))


if __name__ == "__main__":
    main()
