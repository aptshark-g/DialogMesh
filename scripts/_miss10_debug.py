# -*- coding: utf-8 -*-
"""清理后 R@10 miss 分析（2026-08-11）: 实际召回 vs 期望块语义。"""
import sys

sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset, build_service


def main():
    gold = load_goldset()
    blocks = {b["id"]: b["text"] for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
         for b in gold["blocks"]], mode="rrf")
    out = []
    for qi in gold["queries"]:
        res = svc.recall(qi["query"], top_k=10, use_hyde=False)
        hit10 = any(h.id in qi["expected"] for h in res.hits[:10])
        if hit10:
            continue
        out.append("Q: %s (期望 %d 块)" % (qi["query"][:60], len(qi["expected"])))
        out.append("  期望块样例: %s" % blocks.get(qi["expected"][0], "?")[:90].replace("\n", " "))
        for h in res.hits[:3]:
            out.append("  实际[%s]: %s" % (h.id, blocks.get(h.id, "?")[:90].replace("\n", " ")))
        out.append("")
    with open("_miss10.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) or "无 miss")
    print("done")


if __name__ == "__main__":
    main()
