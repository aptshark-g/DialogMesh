# -*- coding: utf-8 -*-
"""召回率低的根因分解（2026-08-11）。

分解维度:
  1. 单路 vs 融合: 每路独立命中数 / 融合后命中数（融合增益）
  2. 单块 vs 多块期望: 期望块数对 top1 的影响
  3. R@20 漏网 query 构成（真正找不到的）
  4. query 长度影响
"""
import sys

sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset, build_service
from scripts.memory_bench import is_context_query


def main():
    gold = load_goldset()
    queries = [q for q in gold["queries"] if not is_context_query(q["query"])]
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    n = len(queries)
    out = []
    out.append("coarse 层 query: %d / blocks: %d" % (n, len(blocks)))

    # 1. 单路 vs 融合
    svc = build_service(blocks, mode="rrf")
    single_hits = {s: 0 for s in ("vector", "bm25", "spo")}
    fused_hits5 = 0
    miss20 = []
    for qi in queries:
        exp = set(qi["expected"])
        for s in single_hits:
            svc.single_source = s
            res = svc.recall(qi["query"], top_k=5, use_hyde=False)
            if any(h.id in exp for h in res.hits[:5]):
                single_hits[s] += 1
        svc.single_source = None
        res = svc.recall(qi["query"], top_k=20, use_hyde=False)
        if any(h.id in exp for h in res.hits[:5]):
            fused_hits5 += 1
        if not any(h.id in exp for h in res.hits[:20]):
            miss20.append(qi)
    out.append("单路 R@5: " + ", ".join(
        "%s=%d(%.0f%%)" % (s, v, 100.0 * v / n) for s, v in single_hits.items()))
    out.append("融合 R@5: %d (%.0f%%)" % (fused_hits5, 100.0 * fused_hits5 / n))
    union = set()
    for s in single_hits:
        union.add(s)
    out.append("单路最大值: %.0f%% (融合应 >= 单路最大)" % (
        100.0 * max(single_hits.values()) / n))

    # 2. 单块 vs 多块期望
    exp1 = [q for q in queries if len(q["expected"]) == 1]
    expm = [q for q in queries if len(q["expected"]) > 3]
    out.append("单块期望: %d | 多块期望(>3): %d" % (len(exp1), len(expm)))
    svc.single_source = None
    for label, sub in (("单块", exp1), ("多块", expm)):
        if not sub:
            continue
        t1 = sum(1 for qi in sub
                 if svc.recall(qi["query"], top_k=5, use_hyde=False).hits
                 and svc.recall(qi["query"], top_k=5, use_hyde=False).hits[0].id
                 in qi["expected"])
        out.append("  %s期望 top1: %.0f%% (%d/%d)" % (
            label, 100.0 * t1 / len(sub), t1, len(sub)))

    # 3. R@20 漏网
    out.append("R@20 漏网: %d" % len(miss20))
    for qi in miss20:
        out.append("  [%s] %s -> %d块" % (
            qi["qid"], qi["query"][:50], len(qi["expected"])))

    # 4. query 长度影响
    short_q = [q for q in queries if len(q["query"]) <= 8]
    long_q = [q for q in queries if len(q["query"]) >= 20]
    out.append("短 query(<=8字): %d | 长 query(>=20字): %d" % (
        len(short_q), len(long_q)))

    with open("_root_cause.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
