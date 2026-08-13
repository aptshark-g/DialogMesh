# -*- coding: utf-8 -*-
"""从真实 v3_sessions 生成召回黄金集（真实数据, 非手写）。"""
import json
import os
import re
import sys
import hashlib

# 脚本直接运行时 sys.path 缺项目根 → core 包导入失败（2026-08-11 修复）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def clean(s):
    # 去掉测试污染的管线分析尾巴
    s = re.split(r"##\s*管线分析", s)[0].strip()
    return s


def is_noise_query(q):
    """评测噪音 query 过滤（2026-08-11, 用户拍板清理）:
    ① 乱码（? 密集） ② hello world 竞态族（多会话同内容, 期望块标注竞态）
    ③ 纯问候/测试。这些 query 召回内容其实是对的, 但"期望=那次会话"的
    标注无法判定 → 混入会低估真实能力。
    """
    q = q.strip()
    if not q:
        return True
    # ① 乱码: ? 占比高
    if q.count("?") / max(1, len(q)) > 0.3:
        return True
    # ② hello world 竞态族
    if re.search(r"hello\s*world|helloworld", q, re.I):
        return True
    # ③ 纯问候/测试
    if q.lower() in ("hi", "hello", "test", "你好", "在吗", "嗯", "好", "ok", "继续"):
        return True
    return False


def chunk_text(text, maxlen=280):
    """生产链路切块（2026-08-11 修复）: 调注册工具 chunk_document。

    此前绕开注册链路自己硬写按句切分 → markdown 结构（---/###/代码块）
    被吞进块, 上下文不闭环、内容残缺。现在走 DocumentIngestionPipeline
    的 parser+注册工具（与生产一致）, 结构节点各自成块, 噪音过滤。
    """
    try:
        # 确保 builtin 工具注册执行（否则 chunk_document 未注册 → fallback）
        import core.agent.tools.builtin  # noqa: F401
        from core.agent.tools.registry import ToolRegistry
        r = ToolRegistry.execute("chunk_document", text=text,
                                 max_chunk_size=maxlen)
        if r.success and r.data:
            return [c for c in r.data.get("chunks", []) if c]
        print("  [goldset] chunk_document not ok: success=%s err=%s"
              % (r.success, getattr(r, "error", "?")[:80]))
        return []
    except Exception as e:
        print("  [goldset] chunk_document failed: %s" % e)
        # 兜底: 段落边界（不按字符硬切）
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


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
    seen_queries = set()  # 同内容 query 去重（2026-08-11: 重复会话稀释评测）
    for sid, query, reply in pairs:
        if is_noise_query(query):
            continue
        q_norm = query.strip()[:60]
        if q_norm in seen_queries:
            continue
        seen_queries.add(q_norm)
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
