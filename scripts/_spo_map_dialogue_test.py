# -*- coding: utf-8 -*-
"""关系类型映射在"词面不相干"对话上的验证（SPO 单路对照）。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from core.agent.recall.recall_service import RecallService
from recall_dialogue_test2 import parse_dialogue
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager

TESTS = [
    {"query": "那个情绪为什么有时候会突然很难受",
     "words": ["预期失衡", "惯性破坏", "情绪指数"]},
    {"query": "人为什么会对同一件事越来越没感觉",
     "words": ["边际效益", "边际情绪", "递减"]},
    {"query": "为什么我老是记住那些特别刺激的事情",
     "words": ["记忆点", "锚定", "情绪峰值"]},
    {"query": "脑子里的两个模式怎么来回切换",
     "words": ["DMN", "ECN", "认知双网络", "默认模式网络", "执行控制"]},
    {"query": "坏情绪是不是因为现实和想的不一样",
     "words": ["预期失衡", "E_实", "E_内", "情绪核心"]},
]

turns = parse_dialogue("data/dialogue_test2.txt")
tm = DiscourseBlockTreeManager()
for role, content in turns:
    if role == "user":
        try:
            tm.feed(content, "cog_dialog")
        except Exception:
            pass
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

svc = RecallService(engine=None, chunk_store=None, discourse=tm, llm=None)
svc.fuse_mode = "rrf"
svc.single_source = "spo"

hits = 0
for t in TESTS:
    res = svc.recall(t["query"], top_k=5, use_hyde=False, sid="cog_dialog")
    rank = None
    for i, h in enumerate(res.hits[:5], 1):
        if any(w in h.text for w in t["words"]):
            rank = i
            break
    if rank:
        hits += 1
    print("  [%s] %s" % ("top%d" % rank if rank else "MISS", t["query"][:22]))
print("=> SPO 单路 top5: %d/%d" % (hits, len(TESTS)))
