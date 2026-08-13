# -*- coding: utf-8 -*-
"""核查 VEC_CACHE: 条目数 vs 实际块 id 匹配（2026-08-12）。"""
import json
import os
import sys

sys.path.insert(0, ".")


def main():
    import scripts.doc_recall_bench as drb
    doc_blocks = drb.load_blocks()
    ids = [b["id"] for b in doc_blocks]
    cache_path = os.path.join("scripts", ".recall_vec_cache_v2.json")
    out = []
    out.append("实际块: %d" % len(ids))
    if not os.path.exists(cache_path):
        out.append("缓存不存在")
        open("_vcache.txt", "w", encoding="utf-8").write("\n".join(out))
        return
    cache = json.load(open(cache_path, encoding="utf-8"))
    out.append("缓存条目: %d" % len(cache))
    matched = sum(1 for i in ids if i in cache)
    out.append("id 命中缓存: %d/%d" % (matched, len(ids)))
    sample = list(cache.items())[:3]
    for k, v in sample:
        out.append("key: %s | vec len: %s" % (
            k[:70], len(v) if isinstance(v, list) else "?"))
    with open("_vcache.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    # 回填验证: prepare_vectors 后 doc_blocks 带 vector 的数量
    drb.prepare_vectors(doc_blocks)
    with_vec = sum(1 for b in doc_blocks if b.get("vector"))
    out2 = "prepare_vectors 回填后带 vector: %d/%d" % (with_vec, len(doc_blocks))
    # 再跑一次 prepare_vectors（增量补全）看补多少
    drb.prepare_vectors(doc_blocks)
    with_vec2 = sum(1 for b in doc_blocks if b.get("vector"))
    out2 += "\n二次 prepare_vectors 后带 vector: %d/%d" % (
        with_vec2, len(doc_blocks))
    with open("_vcache2.txt", "w", encoding="utf-8") as f:
        f.write(out2)
    print(out2)
    print("done")


if __name__ == "__main__":
    main()
