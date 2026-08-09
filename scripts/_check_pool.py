# -*- coding: utf-8 -*-
"""检查对话树池子里是否含公理术语（验证 feed 截断是否导致期望块缺失）。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from recall_dialogue_test2 import parse_dialogue
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager

KEYWORDS = ["预期失衡", "惯性破坏", "记忆点", "锚定", "公理", "Em", "情绪指数"]

turns = parse_dialogue("data/dialogue_test2.txt")
print("turns:", len(turns))
# 第 10 轮 user 消息长度
for i, (role, content) in enumerate(turns):
    if role == "user":
        print("turn", i, "user len:", len(content), "| head:", content[:50])

# 方式1: 截断 400 喂
tm1 = DiscourseBlockTreeManager()
for role, content in turns:
    if role == "user":
        try:
            tm1.feed(content[:400], "cog_dialog")
        except Exception:
            pass
def block_text(b):
    return (getattr(b, "_raw_text", "") or " ".join(
        getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
    )).strip()

# 方式1: 截断 400 喂（HyDE 测试实际用的方式）
print("\n-- truncated-400 feed --")
print("blocks:", len(tm1.blocks))
alltext1 = " ".join(block_text(b) for b in tm1.blocks.values())
print("total chars:", len(alltext1))
for k in KEYWORDS:
    print("  %s: %s" % (k, k in alltext1))

# 方式2: 完整喂（不截断）
tm2 = DiscourseBlockTreeManager()
for role, content in turns:
    if role == "user":
        try:
            tm2.feed(content, "cog_dialog")
        except Exception:
            pass
print("\n-- full feed --")
print("blocks:", len(tm2.blocks))
alltext2 = " ".join(block_text(b) for b in tm2.blocks.values())
print("total chars:", len(alltext2))
for k in KEYWORDS:
    print("  %s: %s" % (k, k in alltext2))
