# -*- coding: utf-8 -*-
"""核对 doc 域 expected 块 id 与 load_blocks 产物 id 的匹配率（2026-08-12）。

用法: .venv/Scripts/python.exe scripts/_doc_eval_id_check.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.query_set import load_query_set
import scripts.doc_recall_bench as drb


def main():
    queries = load_query_set("docs/test/recall_queries_100.md")
    doc_qs = [q for q in queries
              if not q["expected"][0].startswith("goldset:")]
    blocks = drb.load_blocks()
    ids = set(b["id"] for b in blocks)
    print("doc queries:", len(doc_qs), "| blocks:", len(blocks))
    total_exp = 0
    missing = []
    for q in doc_qs:
        for e in q["expected"][0].split(";"):
            e = e.strip()
            if not e:
                continue
            total_exp += 1
            if e not in ids:
                missing.append((q["query"][:30], e))
    print("expected 总数:", total_exp, "| 缺失:", len(missing))
    for q, e in missing[:15]:
        print("  MISS", q, "->", e[:100])
    # 抽样: 若缺失来自文件名不存在, 列出文件侧候选
    if missing:
        import re
        sample = missing[0][1].split("#")[0]
        cands = [b["id"] for b in blocks if sample in b["id"]]
        print("样例候选:", sample)
        for c in cands[:8]:
            print("   ", c[:120])


if __name__ == "__main__":
    main()
