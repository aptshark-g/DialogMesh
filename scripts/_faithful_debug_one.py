# -*- coding: utf-8 -*-
"""recall_fact 单任务全链路调试（2026-08-13）: 上下文/回答/claims/判定。

用法: .venv/Scripts/python.exe scripts/_faithful_debug_one.py
"""
import sys, json, urllib.request, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

API = "http://127.0.0.1:8000"


def post(path, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(API + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main():
    from scripts.claim_eval import GatewayLLM, split_claims, judge_claims_batch
    from scripts.recall_goldset import load_goldset, build_service
    import scripts.doc_recall_bench as drb

    llm = GatewayLLM()
    q = "统一召回用了哪些算法，RRF 融合提升多少？"
    # 1. 上下文
    blocks = drb.load_blocks()
    drb.prepare_vectors(blocks)
    doc_svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in blocks],
        mode="vector_primary")
    res = doc_svc.recall(q, top_k=20, use_hyde=False)
    print("=== 上下文 top-20 ===")
    for i, h in enumerate(res.hits, 1):
        mark = " ★" if "RECALL_CAPABILITY" in h.id else ""
        print("  %d. %s%s" % (i, h.id[:80], mark))
    # 2. v3 回答
    sid = post("/v3/session")["session_id"]
    resp = post(f"/v3/session/{sid}/message", {"content": q})
    content = resp.get("content", "") or ""
    print("\n=== v3 回答 (%d 字符) ===" % len(content))
    print(content[:600])
    # 3. claims
    claims = split_claims(llm, content, q)
    print("\n=== claims (%d) ===" % len(claims))
    for c in claims:
        print("  -", c[:100])
    # 4. 判定
    doc_texts = {b["id"]: b["text"] for b in blocks}
    ctx = "\n".join((doc_texts.get(h.id) or h.text or "")
                    for h in res.hits[:20])
    verdicts = judge_claims_batch(llm, claims, ctx)
    print("\n=== 判定 ===")
    for c, v in zip(claims, verdicts):
        print("  %s | %s" % ("YES" if v else "NO ", c[:80]))


if __name__ == "__main__":
    main()
