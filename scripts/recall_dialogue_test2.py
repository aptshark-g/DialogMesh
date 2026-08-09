# -*- coding: utf-8 -*-
"""连贯高干扰对话召回测试（用户: "这个召回难度应该很大"）。

新对话（辩证法 → 心流/DMN/ECN → 认知-情绪模型公理化）闭环切块,
query = 事后重述（模拟几小时后提问, 非对话原题）,
期望命中 = 块文本包含核心词（语义归一才有机会, 词法易命中"看起来像"的错块）。
池子 = 本对话全部块 + v3_sessions 干扰（冷路径）。
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 事后重述 query → 期望核心词（命中判定: 召回块文本包含任一核心词）
TESTS = [
    {"query": "情绪的根源到底是什么",
     "expect_words": ["预期失衡", "惯性破坏"]},
    {"query": "辩证法和逻辑自指是不是同一个东西",
     "expect_words": ["自指", "罗素悖论"]},
    {"query": "为什么倒着走路会打断走神",
     "expect_words": ["向后走", "向后走路", "平衡"]},
    {"query": "心流和元认知监控的区别",
     "expect_words": ["心流", "伪心流", "元认知监控"]},
    {"query": "认知双网络模式是什么意思",
     "expect_words": ["DMN", "ECN", "默认模式网络", "执行控制"]},
    {"query": "总观效应是什么 宇航员",
     "expect_words": ["总观效应", "宇航员"]},
    {"query": "认知情绪模型里记忆点怎么影响判断",
     "expect_words": ["记忆点", "锚定"]},
    {"query": "为什么人和朋友会越来越脱节",
     "expect_words": ["脱节", "向下兼容", "认知大厦"]},
    {"query": "条件收敛重排为什么可以得出任意值",
     "expect_words": ["条件收敛", "重排", "反直觉"]},
    {"query": "流体智力影响注意力和带宽吗",
     "expect_words": ["流体智力", "带宽"]},
]


def chunk_by_edu(text, maxlen=280):
    """EDU 闭环切块（不切断语义闭环）。"""
    from core.agent.discourse_block_tree.syntactic_decomposer import (
        SYNTACTIC_DECOMPOSER,
    )
    try:
        edus = SYNTACTIC_DECOMPOSER.decompose(text)
        pieces = [getattr(e, "raw_text", "").strip() for e in edus]
        pieces = [p for p in pieces if p]
    except Exception:
        pieces = [text]
    chunks, buf = [], ""
    for p in pieces:
        if len(buf) + len(p) <= maxlen:
            buf += p + "。"
        else:
            if buf:
                chunks.append(buf)
            buf = p + "。" if len(p) <= maxlen else p
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if len(c.strip()) >= 20]


def parse_dialogue(path):
    turns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for prefix in ("user:", "assistant:"):
                if line.startswith(prefix):
                    role = "user" if prefix == "user:" else "assistant"
                    content = line[len(prefix):].strip()
                    if content:
                        turns.append((role, content))
                    break
    return turns


def main():
    path = "data/dialogue_test2.txt"
    turns = parse_dialogue(path)
    print("turns:", len(turns))

    # 只喂 user 消息进对话树（块 = 用户回答/提问, 含大量术语）
    from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
    tm = DiscourseBlockTreeManager()
    for role, content in turns:
        if role == "user":
            try:
                tm.feed(content, "cog_dialog")
            except Exception as e:
                print("feed err:", str(e)[:60])
    print("discourse blocks:", len(tm.blocks))

    # 干扰池: v3_sessions 前 10 会话
    import json
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
    print("total blocks (with interference):", len(tm.blocks))

    from core.agent.recall.recall_service import RecallService
    svc = RecallService(engine=None, chunk_store=None, discourse=tm, llm=None)
    svc.fuse_mode = "rrf"

    t0 = time.time()
    for t in TESTS:
        res = svc.recall(t["query"], top_k=5, use_hyde=False, sid="cog_dialog")
        hits = res.hits[:5]
        hit_texts = [h.text for h in hits]
        matched = [i + 1 for i, ht in enumerate(hit_texts)
                   if any(w in ht for w in t["expect_words"])]
        top_text = hit_texts[0][:50] if hit_texts else ""
        print("\nQ: %s" % t["query"])
        print("  命中位次: %s | top1: %s" % (matched if matched else "MISS", top_text))
        for h in hits[:3]:
            print("   - [%s] %.3f %s" % (h.source.split(":")[-1], h.fused(), h.text[:45]))
    print("\n%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
