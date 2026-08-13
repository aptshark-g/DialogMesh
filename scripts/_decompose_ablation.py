# -*- coding: utf-8 -*-
"""parallel_decompose 开/关消融（真实 LLM, 2026-08-11）。

coarse 层 63 query: 开关关（现状, 无 LLM）vs 开关开（LLM 分解 3 子问题,
并行全路召回）→ 对比 Recall@5/10/20 + top1。
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GW = "http://127.0.0.1:8080"

from scripts.recall_goldset import load_goldset, build_service
from scripts.memory_bench import is_context_query


class GatewayLLM:
    """网关直连 LLM（_expand_questions 用 chat 接口）。"""

    def chat(self, messages):
        prompt = messages[0]["content"]
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256, "temperature": 0.3,
        }).encode("utf-8")
        req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        return d["choices"][0]["message"].get("content") or ""


def recall_k(svc, qi, k):
    res = svc.recall(qi["query"], top_k=k, use_hyde=True)
    return 1.0 if any(h.id in qi["expected"] for h in res.hits[:k]) else 0.0


def top1_hit(svc, qi):
    res = svc.recall(qi["query"], top_k=5, use_hyde=True)
    return 1.0 if res.hits and res.hits[0].id in qi["expected"] else 0.0


def main():
    gold = load_goldset()
    queries = [q for q in gold["queries"] if not is_context_query(q["query"])]
    blocks = [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
              for b in gold["blocks"]]
    print("coarse queries: %d" % len(queries))

    # 开关关（现状）
    svc_off = build_service(blocks, mode="rrf")
    stats_off = {"top1": 0.0, "r5": 0.0, "r10": 0.0, "r20": 0.0}
    t0 = time.time()
    for qi in queries:
        stats_off["top1"] += top1_hit(svc_off, qi)
        stats_off["r5"] += recall_k(svc_off, qi, 5)
        stats_off["r10"] += recall_k(svc_off, qi, 10)
        stats_off["r20"] += recall_k(svc_off, qi, 20)
    n = len(queries)
    print("开关关: top1=%.1f%% R@5=%.1f%% R@10=%.1f%% R@20=%.1f%% (%.0fs)" % (
        100 * stats_off["top1"] / n, 100 * stats_off["r5"] / n,
        100 * stats_off["r10"] / n, 100 * stats_off["r20"] / n,
        time.time() - t0))

    # 开关开（LLM 分解）
    svc_on = build_service(blocks, mode="rrf")
    svc_on._llm = GatewayLLM()
    svc_on.parallel_decompose = True
    svc_on.decompose_subqueries = 3
    svc_on.decompose_max_workers = 4
    stats_on = {"top1": 0.0, "r5": 0.0, "r10": 0.0, "r20": 0.0}
    t0 = time.time()
    for qi in queries:
        stats_on["top1"] += top1_hit(svc_on, qi)
        stats_on["r5"] += recall_k(svc_on, qi, 5)
        stats_on["r10"] += recall_k(svc_on, qi, 10)
        stats_on["r20"] += recall_k(svc_on, qi, 20)
    print("开关开: top1=%.1f%% R@5=%.1f%% R@10=%.1f%% R@20=%.1f%% (%.0fs)" % (
        100 * stats_on["top1"] / n, 100 * stats_on["r5"] / n,
        100 * stats_on["r10"] / n, 100 * stats_on["r20"] / n,
        time.time() - t0))


if __name__ == "__main__":
    main()
