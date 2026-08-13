# -*- coding: utf-8 -*-
"""列出当前 goldset 全部 query（2026-08-11, 清理确认）。"""
import json


def main():
    g = json.load(open("data/recall_goldset.json", encoding="utf-8"))
    out = []
    for i, qi in enumerate(g["queries"]):
        out.append("%3d [%s] %s -> %d块" % (
            i, qi["qid"], qi["query"][:60], len(qi["expected"])))
    with open("_all_queries.txt", "w", encoding="utf-8") as f:
        f.write("total=%d\n%s" % (len(g["queries"]), "\n".join(out)))
    print("done")


if __name__ == "__main__":
    main()
