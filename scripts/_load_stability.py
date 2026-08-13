# -*- coding: utf-8 -*-
"""load_blocks 稳定性核查: 两次调用块数/样本对比（2026-08-12）。"""
import sys

sys.path.insert(0, ".")


def main():
    import scripts.doc_recall_bench as drb
    b1 = drb.load_blocks()
    b2 = drb.load_blocks()
    ids1 = [b["id"] for b in b1]
    ids2 = [b["id"] for b in b2]
    out = []
    out.append("第一次: %d 块 | 第二次: %d 块" % (len(b1), len(b2)))
    out.append("id 集合相同: %s" % (set(ids1) == set(ids2)))
    only1 = set(ids1) - set(ids2)
    only2 = set(ids2) - set(ids1)
    out.append("仅第一次有: %d | 仅第二次有: %d" % (len(only1), len(only2)))
    for i in list(only1)[:5]:
        out.append("  only1: %s" % i[:80])
    for i in list(only2)[:5]:
        out.append("  only2: %s" % i[:80])
    # 检查 VEC_CACHE 的 id 前缀
    import json, os
    cache = json.load(open("scripts/.recall_vec_cache_v2.json", encoding="utf-8"))
    cids = set(cache.keys())
    out.append("缓存 id 数: %d | 与 b1 相同: %d | 与 b2 相同: %d" % (
        len(cids), len(cids & set(ids1)), len(cids & set(ids2))))
    with open("_stability.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
