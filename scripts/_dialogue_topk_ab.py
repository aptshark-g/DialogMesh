# -*- coding: utf-8 -*-
"""RRF rank_cap 消融（2026-08-12）: 验证"每源排名上限"对 top1 的影响。

用法: .venv/Scripts/python.exe scripts/_dialogue_topk_ab.py [cap] [domain]
  cap=0/5/10/15, domain=dialogue|doc（默认 dialogue）
"""
import sys, os, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.recall_goldset import load_goldset, build_service
import scripts.doc_recall_bench as drb


def run_dialogue(gold, cap, top_k=20):
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="rrf")
    svc.rrf_rank_cap = cap
    if os.environ.get("SINGLE_POOL"):
        svc._ensure_global_blocks = lambda: []
    top1 = top5 = 0
    for qi in gold["queries"]:
        exp = set(qi["expected"])
        res = svc.recall(qi["query"], top_k=top_k, use_hyde=False)
        for i, h in enumerate(res.hits[:20], 1):
            if h.id in exp:
                if i == 1:
                    top1 += 1
                if i <= 5:
                    top5 += 1
                break
    return top1, top5


def run_doc(blocks, cap, top_k=20):
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in blocks], mode="rrf")
    svc.rrf_rank_cap = cap
    if os.environ.get("SINGLE_POOL"):
        svc._ensure_global_blocks = lambda: []
    file_to_ids = {}
    for b in blocks:
        file_to_ids.setdefault(b["doc"], set()).add(b["id"])
    from scripts.query_set import load_query_set
    queries = load_query_set("docs/test/recall_queries_100.md")
    top1 = top5 = 0
    n = 0
    for qi in queries:
        exp_raw = qi["expected"][0]
        if exp_raw.startswith("goldset:"):
            continue
        exp = set()
        for e in exp_raw.split(";"):
            e = e.strip()
            if not e:
                continue
            exp.update(file_to_ids.get(e, {e}))
        n += 1
        res = svc.recall(qi["query"], top_k=top_k, use_hyde=False)
        for i, h in enumerate(res.hits[:20], 1):
            if h.id in exp:
                if i == 1:
                    top1 += 1
                if i <= 5:
                    top5 += 1
                break
    return top1, top5, n


def main():
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    domain = sys.argv[2] if len(sys.argv) > 2 else "dialogue"
    t0 = time.time()
    if domain == "doc":
        blocks = drb.load_blocks()
        drb.prepare_vectors(blocks)
        t1, t5, n = run_doc(blocks, cap)
        print("doc   cap=%2d  top1=%d/%d (%.1f%%)  top5=%d (%.1f%%)  %.1fs" % (
            cap, t1, n, 100.0 * t1 / n, t5, 100.0 * t5 / n, time.time() - t0))
    else:
        gold = load_goldset()
        t1, t5 = run_dialogue(gold, cap)
        n = len(gold["queries"])
        print("dialog cap=%2d  top1=%d/%d (%.1f%%)  top5=%d (%.1f%%)  %.1fs" % (
            cap, t1, n, 100.0 * t1 / n, t5, 100.0 * t5 / n, time.time() - t0))


if __name__ == "__main__":
    main()
