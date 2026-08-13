# -*- coding: utf-8 -*-
"""C 类（检索缺口）6 条核查（2026-08-12）: 期望文件是否在语料、块概况。

用法: .venv/Scripts/python.exe scripts/_doc_c_class_check.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.doc_recall_bench as drb

def main():
    from scripts.query_set import load_query_set
    queries = load_query_set("docs/test/recall_queries_100.md")
    c_queries = []
    for q in queries:
        if q["expected"][0].startswith("goldset:"):
            continue
        if q["query"] in (
            "agentic 工具节点怎么让 LLM 自己调工具",
            "执行层监控 Hot Warm Cold 分别做什么",
            "蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据",
            "技能生命周期怎么做活性管理的",
            "第一版发布前还差哪些，前端绑定和量化测试优先级",
            "隐式关系候选怎么生成和核验，precision 多少",
        ):
            c_queries.append((q["query"],
                              [e.strip() for e in q["expected"][0].split(";")
                               if e.strip()]))
    blocks = drb.load_blocks()
    by_file = {}
    for b in blocks:
        by_file.setdefault(b["doc"], []).append(b)
    all_files = set(by_file)
    for q, files in c_queries:
        print("\nQ: %s" % q)
        for f in files:
            if f in by_file:
                bs = by_file[f]
                print("  %s  存在, %d 块, 首块: %s" % (
                    f, len(bs), bs[0]["id"][-40:]))
                for b in bs[:3]:
                    print("    - %s | %s" % (b["id"].split("#")[-1][:40],
                                             b["text"][:60].replace("\n", " ")))
            else:
                # 模糊找候选
                cands = [x for x in all_files if f.split("/")[-1][:20] in x]
                print("  %s  不在语料! 候选: %s" % (f, cands[:3]))
                # 若候选存在, 展示候选文件的块
                for c in cands[:1]:
                    bs = by_file.get(c, [])
                    print("    候选块数:", len(bs))


if __name__ == "__main__":
    main()
