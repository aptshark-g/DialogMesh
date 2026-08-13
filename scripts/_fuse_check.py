# -*- coding: utf-8 -*-
"""融合负增益排查: 单路 vs 融合逐 query 对比（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset, build_service
from scripts.memory_bench import is_context_query


def main():
    gold = load_goldset()
    queries = [q for q in gold["queries"] if not is_context_query(q["query"])]
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    svc = build_service(blocks, mode="rrf")
    out = []
    lost = 0
    for qi in queries:
        exp = set(qi["expected"])
        # 单路 vector top5
        svc.single_source = "vector"
        v5 = {h.id for h in svc.recall(qi["query"], top_k=5, use_hyde=False).hits}
        svc.single_source = None
        # 融合 top5
        f5 = {h.id for h in svc.recall(qi["query"], top_k=5, use_hyde=False).hits}
        if v5.intersection(exp) and not f5.intersection(exp):
            lost += 1
            out.append("vector命中但融合丢失: [%s] %s" % (
                qi["qid"], qi["query"][:45]))
            out.append("  vector top5: %s" % sorted(v5)[:8])
            out.append("  fused top5: %s" % sorted(f5)[:8])
    out.insert(0, "vector R@5 命中但融合丢失的 query: %d" % lost)
    with open("_fuse_check.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done, lost=%d" % lost)


if __name__ == "__main__":
    main()
