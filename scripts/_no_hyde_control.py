# -*- coding: utf-8 -*-
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from core.agent.recall.recall_service import RecallService
from recall_dialogue_test2 import parse_dialogue
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager

turns = parse_dialogue("data/dialogue_test2.txt")
tm = DiscourseBlockTreeManager()
for role, content in turns:
    if role == "user":
        try: tm.feed(content, "cog_dialog")
        except Exception: pass
sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
fed = 0
for sid, s in sessions.items():
    if fed >= 10: break
    for m in (s.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = str(m.get("content", "") or "")
            if c.strip():
                try: tm.feed(c.strip()[:200], "v3_" + sid[:8])
                except Exception: pass
    fed += 1
print("blocks:", len(tm.blocks))

MISS = [
    ("情绪的根源到底是什么", ["预期失衡", "惯性破坏"]),
    ("认知双网络模式是什么意思", ["DMN", "ECN", "默认模式网络", "执行控制"]),
    ("认知情绪模型里记忆点怎么影响判断", ["记忆点", "锚定"]),
]
svc = RecallService(engine=None, chunk_store=None, discourse=tm, llm=None)
svc.fuse_mode = "rrf"
print("=== NO HyDE (llm=None) ===")
for q, words in MISS:
    res = svc.recall(q, top_k=5, use_hyde=False, sid="cog_dialog")
    hits = [h for h in res.hits[:5] if any(w in h.text for w in words)]
    print("Q:", q, "->", "HIT top%d" % (res.hits.index(hits[0])+1) if hits else "MISS", "| top1:", res.hits[0].text[:30])
