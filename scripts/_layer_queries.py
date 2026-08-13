# -*- coding: utf-8 -*-
"""评测分层分析: 粗召回层 vs 情景再现层（指代/上下文依赖）。"""
import json
import re


PRONOUN_RE = re.compile(
    r"^(继续|然后|那|这|嗯|好|可以|行|对|是|hi|test|hello|在吗|我|你|现在|没|有|再|就|把|给|它|他|她|做|来)")


def main():
    g = json.load(open("data/recall_goldset.json", encoding="utf-8"))
    qs = g["queries"]
    ctx = [q for q in qs if PRONOUN_RE.match(q["query"].strip())]
    clean = [q for q in qs if q not in ctx]
    out = []
    out.append("总 query: %d" % len(qs))
    out.append("上下文依赖候选（情景再现层）: %d" % len(ctx))
    out.append("信息量足候选（粗召回层）: %d" % len(clean))
    out.append("")
    out.append("=== 情景再现层 ===")
    for q in ctx:
        out.append("  [%s] %s -> %d块 sid=%s" % (
            q["qid"], q["query"][:45], len(q["expected"]), q.get("sid", "")))
    out.append("")
    out.append("=== 粗召回层（前 15） ===")
    for q in clean[:15]:
        out.append("  [%s] %s -> %d块" % (
            q["qid"], q["query"][:45], len(q["expected"])))
    with open("_layer_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
