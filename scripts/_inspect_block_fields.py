# -*- coding: utf-8 -*-
"""检查对话树块对象字段: 文本到底存哪（_raw_text / atomic_units / EDU）。"""
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

tm = DiscourseBlockTreeManager()
tm.feed(long_user, "cog_dialog")
print("blocks:", len(tm.blocks))
for bid, b in tm.blocks.items():
    print("\nblock", bid, "| name:", getattr(b, "name", "")[:40])
    print("  _raw_text:", repr(getattr(b, "_raw_text", ""))[:60])
    print("  atomic_units:", type(getattr(b, "atomic_units", None)).__name__,
          len(getattr(b, "atomic_units", []) or []))
    aus = getattr(b, "atomic_units", []) or []
    for u in aus[:2]:
        print("    unit fields:", [a for a in dir(u) if not a.startswith('_')][:12])
        print("    unit raw_text:", repr(getattr(u, "raw_text", ""))[:60])
        print("    unit text:", repr(getattr(u, "text", ""))[:60])
    # 所有非私有字段
    fields = {k: v for k, v in vars(b).items() if not k.startswith('_')}
    print("  public fields:", list(fields.keys()))
