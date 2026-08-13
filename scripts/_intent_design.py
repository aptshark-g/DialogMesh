# -*- coding: utf-8 -*-
"""查设计: 意图分类 → 召回 的接线设计（2026-08-11）。"""
import glob
import re


def main():
    files = (glob.glob("docs/only/recall/*.md")
             + glob.glob("docs/only/intent/*.md")
             + glob.glob("docs/only/llm_cognitive/*.md"))
    out = []
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
        except Exception:
            continue
        for m in re.finditer(
                r".{80}(意图.{0,60}(召回|检索|锚点)|召回.{0,60}意图|intent.{0,60}recall|recall.{0,60}intent).{80}",
                text, re.S):
            seg = re.sub(r"\s+", " ", m.group(0)).strip()
            out.append("== %s\n%s" % (f, seg[:300]))
    with open("_intent_design.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(out) or "无匹配")
    print("done")


if __name__ == "__main__":
    main()
