# -*- coding: utf-8 -*-
"""Context Recall 单条调试（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.claim_eval import GatewayLLM, split_claims, judge_claim
from scripts.recall_goldset import load_goldset, build_service


def main():
    llm = GatewayLLM()
    gold = load_goldset()
    blocks = {b["id"]: b["text"] for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": b.get("session", "")}
         for b in gold["blocks"]], mode="rrf")
    qi = gold["queries"][0]
    res = svc.recall(qi["query"], top_k=5, use_hyde=False)
    ctx = "\n".join((h.text or "")[:200] for h in res.hits[:5])
    reference = "\n".join(blocks.get(e, "") for e in qi["expected"])
    out = []
    out.append("Q: %s" % qi["query"])
    out.append("CTX len=%d: %s" % (len(ctx), ctx[:300]))
    out.append("REF len=%d: %s" % (len(reference), reference[:300]))
    claims = split_claims(llm, reference)
    out.append("claims=%d" % len(claims))
    # 直接看 LLM 拆分原始返回
    from scripts.claim_eval import GW
    import urllib.request, json as _json
    prompt = (
        "把下面的文本拆成独立的原子事实陈述（claims）。每条一行, "
        "用编号开头如 1. 2. 3.。只输出 claims, 不要解释:\n\n" + reference[:3000]
    )
    body = _json.dumps({
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024, "temperature": 0.0,
    }).encode("utf-8")
    req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        d = _json.loads(resp.read().decode("utf-8"))
    raw = d["choices"][0]["message"].get("content") or ""
    out.append("LLM 原始返回 (%d 字符): %r" % (len(raw), raw[:500]))
    for c in claims[:5]:
        r = judge_claim(llm, c, ctx)
        out.append("  claim: %s -> %s" % (c[:50], r))
    with open("_claim_dbg.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
