# -*- coding: utf-8 -*-
"""缓存 key 匹配率核查（2026-08-12）: global.json vs 实际块 id。"""
import json
import os
import sys

sys.path.insert(0, ".")


def main():
    import scripts.doc_recall_bench as drb
    doc_blocks = drb.load_blocks()
    ids = [b["id"] for b in doc_blocks]
    print("实际块数: %d" % len(ids))
    # 缓存
    path = "data/recall_index/global.json"
    if not os.path.exists(path):
        print("缓存不存在!")
        return
    cache = json.load(open(path, encoding="utf-8"))
    cblocks = cache.get("blocks", {})
    print("缓存条目: %d" % len(cblocks))
    cids = set(cblocks.keys())
    matched = sum(1 for i in ids if i in cids)
    print("块 id 命中缓存: %d/%d (%.0f%%)" % (
        matched, len(ids), 100.0 * matched / max(1, len(ids))))
    # 缓存条目示例
    sample = list(cblocks.items())[:3]
    for k, v in sample:
        print("缓存 key: %s | spo=%s vec=%s" % (
            k[:60], bool(v.get("spo")), bool(v.get("vector"))))
    # 实际块 id 示例
    print("实际 id 示例:", [i[:60] for i in ids[:3]])
    # 不匹配的缓存条目（是否旧数据）
    stale = [k for k in cids if k not in set(ids)]
    print("缓存中有但实际无的条目: %d" % len(stale))
    if stale:
        print("  示例:", [k[:60] for k in list(stale)[:3]])


if __name__ == "__main__":
    main()
