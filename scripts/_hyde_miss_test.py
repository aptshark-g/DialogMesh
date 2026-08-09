# -*- coding: utf-8 -*-
"""HyDE 真网关重测 3 条 MISS（云端 LLM 扩展能否救回语义题）。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
from core.agent.recall.recall_service import RecallService
from recall_dialogue_test2 import parse_dialogue
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager

gw = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
print("gateway health:", gw.health_check())

turns = parse_dialogue("data/dialogue_test2.txt")
tm = DiscourseBlockTreeManager()
for role, content in turns:
    if role == "user":
        try:
            tm.feed(content, "cog_dialog")
        except Exception as e:
            print("feed err:", str(e)[:60])

sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
fed = 0
for sid, s in sessions.items():
    if fed >= 10:
        break
    for m in (s.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = str(m.get("content", "") or "")
            if c.strip():
                try:
                    tm.feed(c.strip()[:200], "v3_" + sid[:8])
                except Exception:
                    pass
    fed += 1
print("blocks:", len(tm.blocks))

MISS = [
    ("情绪的根源到底是什么", ["预期失衡", "惯性破坏"]),
    ("认知双网络模式是什么意思", ["DMN", "ECN", "默认模式网络", "执行控制"]),
    ("认知情绪模型里记忆点怎么影响判断", ["记忆点", "锚定"]),
]

svc = RecallService(engine=None, chunk_store=None, discourse=tm, llm=gw)
svc.fuse_mode = "rrf"
for q, words in MISS:
    res = svc.recall(q, top_k=5, use_hyde=True, sid="cog_dialog")
    print("\nQ:", q)
    print("expanded:", res.expanded_queries)
    for h in res.hits[:5]:
        hit = any(w in h.text for w in words)
        print("  [%s] %.3f %s %s" % (
            h.source.split(":")[-1], h.fused(), "HIT" if hit else "-",
            h.text[:40]))
