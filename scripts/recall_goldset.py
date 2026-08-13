# -*- coding: utf-8 -*-
"""召回黄金集跑分: 现状(线性) vs RRF 融合 vs 规则增强(同义归一)。

用法: python scripts/recall_goldset.py [--mode linear|rrf|norm] [--top-k 5]
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeBlock:
    def __init__(self, bid, text, session=None):
        self.block_id = bid
        self._raw_text = text
        self._session_id = session or ""
        self.vector = None       # 预编码向量透传（2026-08-11）
        self.summary = ""        # 摘要透传（两级粒度）
        self.parent_id = None
        self.child_ids = []
        self.status = "active"
        self.atomic_units = []


class FakeDiscourse:
    def __init__(self, blocks):
        self.blocks = {b.block_id: b for b in blocks}


def load_goldset(path="data/recall_goldset.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_service(blocks, mode="vector_primary", single=None):
    from core.agent.recall.recall_service import RecallService
    fakes = []
    for b in blocks:
        fb = FakeBlock(b["id"], b["text"], b.get("session"))
        fb.vector = b.get("vector")
        fb.summary = b.get("summary", "")
        fakes.append(fb)
    # W4（2026-08-13）: bench 平铺块按 session 建顺序链 — 生产 discourse
    # 树有 parent/child 结构, 评测应同构, 否则 recall() 内 _diffuse
    # 空转, 上下文永远只有裸锚点（Faithfulness 误判幻觉的根因之一）。
    by_sess = {}
    for fb in fakes:
        by_sess.setdefault(fb._session_id or "_", []).append(fb)
    for members in by_sess.values():
        for i, fb in enumerate(members):
            if i > 0:
                fb.parent_id = members[i - 1].block_id
            if i + 1 < len(members):
                fb.child_ids = [members[i + 1].block_id]
    discourse = FakeDiscourse(fakes)
    svc = RecallService(engine=None, chunk_store=None, discourse=discourse, llm=None)
    # 2026-08-12: env 优先（DM_FUSION 消融开关）— 构造后覆写会吞掉
    # __init__ 里的 env 覆盖, 导致消融无效。
    svc.fuse_mode = os.environ.get("DM_FUSION", mode)
    svc.single_source = single
    return svc


def hit_rank(service, query, expected, top_k, sid=None):
    res = service.recall(query, top_k=top_k, use_hyde=False, sid=sid)
    ids = {h.id for h in res.hits}
    best_rank = None
    for i, h in enumerate(res.hits, 1):
        if h.id in expected:
            best_rank = i
            break
    return best_rank


def random_baseline(gold, top_k, scope="global"):
    """理论随机基线: 每个 query 随机抽 top_k 块, 期望块命中的概率。
    global: 用全局块数; session: 用该 query 所属会话的块数（池小则基线高）。
    """
    if scope == "session":
        from collections import defaultdict
        sess_blocks = defaultdict(int)
        for b in gold["blocks"]:
            sess_blocks[b.get("session", "")] += 1
    hits = 0
    for qi in gold["queries"]:
        if scope == "session":
            pool = sess_blocks.get(qi.get("sid", ""), 0)
        else:
            pool = len(gold["blocks"])
        p_hit = 1.0 - (1.0 - len(qi["expected"]) / max(pool, 1)) ** top_k
        hits += p_hit
    return hits / len(gold["queries"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="vector_primary",
                    choices=["linear", "rrf", "norm", "vector_primary"])
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--single", default=None,
                    choices=["vector", "bm25", "spo", "hyde", "assoc"])
    ap.add_argument("--scope", default="global", choices=["global", "session"])
    args = ap.parse_args()

    gold = load_goldset()
    svc = build_service(gold["blocks"], args.mode, args.single)
    t0 = time.time()
    hits1 = hits3 = hits5 = 0
    misses = []
    for qi in gold["queries"]:
        sid = qi.get("sid") if args.scope == "session" else None
        rank = hit_rank(svc, qi["query"], qi["expected"], args.top_k, sid=sid)
        if rank is None:
            misses.append((qi["query"][:40], len(qi["expected"])))
            continue
        if rank <= 1:
            hits1 += 1
        if rank <= 3:
            hits3 += 1
        if rank <= 5:
            hits5 += 1
    dt = time.time() - t0
    total = len(gold["queries"])
    label = f"{args.scope}:{args.mode}" + (f"+single:{args.single}" if args.single else "")
    print("scope=%s mode=%s top1=%d/%d (%.1f%%) top3=%d/%d (%.1f%%) top5=%d/%d (%.1f%%)  random=%.1f%%  %.2fs"
          % (args.scope, args.mode,
             hits1, total, 100.0 * hits1 / total,
             hits3, total, 100.0 * hits3 / total,
             hits5, total, 100.0 * hits5 / total,
             100.0 * random_baseline(gold, 5, args.scope), dt))
    if misses:
        print("misses:")
        for q, n in misses[:12]:
            print("  - %s (expected %d blocks)" % (q, n))


if __name__ == "__main__":
    main()
