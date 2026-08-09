# -*- coding: utf-8 -*-
"""真实对话召回测试: 把一段问答式对话喂进对话树,
query = assistant 题目（豆包题）, 期望命中 = 紧随其后的 user 回答块。

用法:
  python scripts/recall_dialogue_test.py data/dialogue_test.txt [--sid test_dialog]

对话文件格式（每行一条, role 前缀）:
  user: 你的回答...
  assistant: 题目/判定...
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_dialogue(path):
    """解析对话文件 → [(role, content)]"""
    turns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for prefix in ("user:", "assistant:", "assistant：", "user："):
                if line.startswith(prefix):
                    role = "user" if prefix.startswith("user") else "assistant"
                    content = line[len(prefix):].strip()
                    if content:
                        turns.append((role, content))
                    break
    return turns


def build_tree(turns, sid):
    """喂 user 消息进对话树; 返回 (tm, user_block_map: user_idx -> [block_ids])。"""
    from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
    tm = DiscourseBlockTreeManager()
    user_block_map = {}
    user_idx = 0
    for role, content in turns:
        if role == "user":
            res = tm.feed(content, sid)
            bids = []
            if res is not None and getattr(res, "block_ids", None):
                bids = list(res.block_ids)
            user_block_map[user_idx] = {"query": content, "block_ids": bids}
            user_idx += 1
    return tm, user_block_map


def mix_v3_sessions(tm, count=8):
    """把 v3_sessions 的前 count 个会话也喂进树（干扰池, 冷路径用）。"""
    import json
    sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
    fed = 0
    for sid, s in sessions.items():
        if fed >= count:
            break
        msgs = s.get("messages") or s.get("history") or []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "user":
                c = str(m.get("content", "") or "")
                if c.strip():
                    try:
                        tm.feed(c.strip()[:200], "v3_" + sid[:8])
                    except Exception:
                        pass
        fed += 1
    return tm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="对话文件路径")
    ap.add_argument("--sid", default="test_dialog")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--scope", default="session", choices=["session", "global"])
    ap.add_argument("--mix-v3", type=int, default=0,
                    help="混入 N 个 v3_sessions 会话作干扰池（冷路径）")
    args = ap.parse_args()

    turns = parse_dialogue(args.path)
    print("parsed %d turns" % len(turns))
    tm, user_map = build_tree(turns, args.sid)
    if args.mix_v3 > 0:
        tm = mix_v3_sessions(tm, args.mix_v3)
    print("discourse blocks: %d" % len(tm.blocks))

    from core.agent.recall.recall_service import RecallService
    svc = RecallService(engine=None, chunk_store=None, discourse=tm, llm=None)
    svc.fuse_mode = "rrf"

    # 测试对: assistant 题目(query) → 紧随其后的 user 回答块(期望)
    tests = []
    user_idx = 0
    for role, content in turns:
        if role == "user":
            user_idx += 1
        elif role == "assistant" and user_idx < len(user_map):
            expect = user_map[user_idx].get("block_ids") or []
            if expect:
                tests.append({"query": content, "expect": expect})

    t0 = time.time()
    hits1 = hits5 = 0
    for t in tests:
        res = svc.recall(t["query"], top_k=args.top_k, use_hyde=False,
                         sid=args.sid if args.scope == "session" else None)
        ids = [h.id for h in res.hits]
        for i, bid in enumerate(ids, 1):
            if bid in t["expect"]:
                if i == 1:
                    hits1 += 1
                hits5 += 1
                break
    dt = time.time() - t0
    total = len(tests)
    print("scope=%s rrf top%d: top1=%d/%d (%.1f%%) top%d=%d/%d (%.1f%%)  %.2fs  (%d blocks)"
          % (args.scope, args.top_k, hits1, total, 100.0 * hits1 / total,
             args.top_k, hits5, total, 100.0 * hits5 / total, dt, len(tm.blocks)))


if __name__ == "__main__":
    main()
