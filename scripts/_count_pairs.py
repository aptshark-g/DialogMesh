# -*- coding: utf-8 -*-
"""统计 v3_sessions 可提取 query 量（2026-08-11, 目标 100 条）。"""
import json
import re


def main():
    sessions = json.load(open("data/v3_sessions.json", encoding="utf-8"))
    pairs = []
    for sid, s in sessions.items():
        msgs = s.get("messages") or s.get("history") or []
        pending = None
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = str(m.get("content", "") or "")
            if role == "user":
                pending = re.split(r"##\s*管线分析", content)[0].strip()
            elif role == "assistant" and pending and len(content) >= 120:
                pairs.append((sid, pending, content))
                pending = None
    out = []
    out.append("总 (user→reply) 对: %d" % len(pairs))
    # 去重后
    seen = set()
    uniq = []
    for sid, q, r in pairs:
        qn = q.strip()[:60]
        if qn in seen:
            continue
        seen.add(qn)
        uniq.append((sid, q, r))
    out.append("去重后: %d" % len(uniq))
    # 排除噪音（乱码/hello world/问候）
    noise = 0
    clean = []
    for sid, q, r in uniq:
        if q.count("?") / max(1, len(q)) > 0.3:
            noise += 1
            continue
        if re.search(r"hello\s*world|helloworld", q, re.I):
            noise += 1
            continue
        if q.lower() in ("hi", "hello", "test", "你好", "在吗", "嗯", "好", "ok", "继续"):
            noise += 1
            continue
        clean.append((sid, q, r))
    out.append("清噪音后: %d" % len(clean))
    out.append("噪音: %d" % noise)
    with open("_pairs_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
        f.write("\n\n前 30 条:")
        for sid, q, r in clean[:30]:
            f.write("\n  [%s] %s" % (sid[:8], q[:60]))
    print("done")


if __name__ == "__main__":
    main()
