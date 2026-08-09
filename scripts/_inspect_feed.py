# -*- coding: utf-8 -*-
"""检查长文本 feed 进对话树后块的实际内容（定位公理丢失原因）。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from recall_dialogue_test2 import parse_dialogue
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager

turns = parse_dialogue("data/dialogue_test2.txt")
long_user = None
for role, content in turns:
    if role == "user" and len(content) > 1000:
        long_user = content
        break
print("long user len:", len(long_user))

tm = DiscourseBlockTreeManager()
res = tm.feed(long_user, "cog_dialog")
print("feed returned:", res)
print("blocks:", len(tm.blocks))
for bid, b in tm.blocks.items():
    raw = getattr(b, "_raw_text", "") or ""
    name = getattr(b, "name", "")
    print("\nblock", bid)
    print("  name:", name[:60])
    print("  raw len:", len(raw))
    print("  raw head:", raw[:80])
    print("  raw tail:", raw[-80:] if raw else "")
