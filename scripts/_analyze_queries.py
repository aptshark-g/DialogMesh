# -*- coding: utf-8 -*-
"""分析 goldset query 构成（临时诊断）: 短 query / 指代 query / 期望分布。"""
import json
import re


def main():
    g = json.load(open("data/recall_goldset.json", encoding="utf-8"))
    qs = g["queries"]
    short_q = [q for q in qs if len(q["query"].strip()) <= 4]
    pronoun_q = [q for q in qs if re.match(
        r"^(继续|然后|那|这|嗯|好|可以|行|对|是|hi|test|hello|在吗|我|你|现在)",
        q["query"].strip())]
    exp1 = [q for q in qs if len(q["expected"]) == 1]
    exp_multi = [q for q in qs if len(q["expected"]) > 5]
    out = []
    out.append("总 query: %d" % len(qs))
    out.append("<=4字符短 query: %d" % len(short_q))
    out.append("指代/上下文依赖 query: %d" % len(pronoun_q))
    out.append("单块期望: %d | 多块期望(>5): %d" % (len(exp1), len(exp_multi)))
    out.append("短 query 示例: %s" % [q["query"] for q in short_q[:10]])
    out.append("指代 query 示例: %s" % [q["query"] for q in pronoun_q[:10]])
    with open("_analyze_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
