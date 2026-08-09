# -*- coding: utf-8 -*-
"""从真实 v3_sessions 生成召回黄金集（真实数据, 非手写）。"""
import json
import re
import hashlib


def clean(s):
    # 去掉测试污染的管线分析尾巴
    s = re.split(r"##\s*管线分析", s)[0].strip()
    return s


def chunk_text(text, maxlen=280):
    """闭环切块: 语法补全(代词) → EDU 闭环 → 相邻闭环合并到 maxlen。

    不切断语义闭环（EDU 边界才断）; 超长闭环保留完整（语义压缩后续接入,
    不机械截断 — 用户拍板: "抓闭环, 语义压缩实现长度统一, 不是强制切块"）。
    """
    try:
        from core.agent.discourse_block_tree.syntactic_decomposer import (
            SYNTACTIC_DECOMPOSER,
        )
        edus = SYNTACTIC_DECOMPOSER.decompose(text)
        pieces = []
        for e in edus:
            t = (getattr(e, "raw_text", "") or "").strip()
            if t:
                pieces.append(t)
    except Exception:
        # 兜底: 句号/段落边界（不按字符硬切）
        pieces = [p.strip() for p in re.split(
            r"(?<=[。！？!?；;])\s*|\n{2,}", text) if p.strip()]
    if not pieces:
        return []
    chunks = []
    buf = ""
    for p in pieces:
        if len(buf) + len(p) <= maxlen:
            buf += p + "。"
        else:
            if buf:
                chunks.append(buf)
            buf = p + "。" if len(p) <= maxlen else p  # 超长闭环保留完整
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if len(c.strip()) >= 20]


def main():
    sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
    pairs = []  # (sid, query, reply_text)
    for sid, s in sessions.items():
        msgs = s.get("messages") or s.get("history") or []
        pending_user = None
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = str(m.get("content", "") or "")
            if role == "user":
                pending_user = clean(content)
            elif role == "assistant" and pending_user and len(content) >= 120:
                pairs.append((sid, pending_user, content))
                pending_user = None

    blocks = []
    query_items = []
    block_counter = 0
    for sid, query, reply in pairs:
        chunks = chunk_text(reply)
        if not chunks:
            continue
        qid = "q" + hashlib.md5((sid + "|" + query).encode()).hexdigest()[:6]
        expected = []
        for ch in chunks:
            bid = "r%03d" % block_counter
            block_counter += 1
            blocks.append({"id": bid, "text": ch, "session": sid})
            expected.append(bid)
        query_items.append({"query": query[:100], "expected": expected,
                            "sid": sid, "qid": qid})

    print("pairs=%d blocks=%d queries=%d" % (len(pairs), len(blocks), len(query_items)))
    for qi in query_items[:20]:
        print("  [%s] %s -> %d blocks" % (qi["sid"], qi["query"][:50], len(qi["expected"])))

    out = {
        "meta": {
            "created": "2026-08-08",
            "source": "data/v3_sessions.json real dialogs (user query -> assistant reply chunks)",
            "note": "expected = all chunks of that reply; hit = any expected chunk in top-k",
        },
        "blocks": blocks,
        "queries": query_items,
    }
    with open("data/recall_goldset.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written data/recall_goldset.json")


if __name__ == "__main__":
    main()
