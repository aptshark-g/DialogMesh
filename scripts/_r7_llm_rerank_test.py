# -*- coding: utf-8 -*-
"""R7 原型: LLM 挑选器（候选看内容判断, 非扩展）。

流程: 纯召回 top-30 候选 → 候选文本给网关 LLM → LLM 挑 top5
对比: 纯召回 top5 / LLM 挑 top5（期望 = 公理核心词）。
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from core.agent.llm_providers.base import GenerateRequest
from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
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
    {"query": "为什么走神的时候想法特别多 专注的时候反而很空",
     "words": ["DMN", "ECN", "默认模式", "执行控制", "混沌"]},
    {"query": "坏情绪是不是因为现实和想的不一样",
     "words": ["预期失衡", "E_实", "E_内", "情绪核心"]},
    {"query": "一个人怎么看待自己 是不是看他在乎什么",
     "words": ["自我价值感", "稀缺性", "锚定集"]},
]

turns = parse_dialogue("data/dialogue_test2.txt")


def build_tree():
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
    return tm


def llm_score(llm, query, candidates):
    """候选 ≤15 → LLM 一次打分（编号: 分数 0-1）, 返回 (id, score) 排序。"""
    lines = []
    for i, (bid, text) in enumerate(candidates):
        lines.append("%d. %s" % (i + 1, text[:60]))
    prompt = (
        "问题: %s\n\n"
        "以下是候选内容（编号. 文本）。对每个候选输出与问题的相关度分数"
        "（0.0-1.0）, 格式: 编号:分数, 逗号分隔, 只输出分数列表:\n%s"
        % (query, "\n".join(lines))
    )
    try:
        res = llm.generate(GenerateRequest(
            prompt=prompt, max_tokens=128, temperature=0.1,
            timeout_ms=45000))
        text = res.text if res is not None else ""
        scores = {}
        for m in re.finditer(r"(\d+)\s*[:：]\s*([0-9.]+)", text):
            idx = int(m.group(1))
            score = float(m.group(2))
            if 1 <= idx <= len(candidates):
                scores[idx] = score
        if not scores:
            # 兜底: 输出顺序视为降序
            for i, (bid, _) in enumerate(candidates[:5], 1):
                scores[i] = 1.0 - i * 0.1
        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(candidates[i - 1][0], s) for i, s in ordered[:5]
                if 1 <= i <= len(candidates)]
    except Exception as e:
        print("  llm score err:", str(e)[:80])
        return []


def main():
    gw = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
    svc = RecallService(engine=None, chunk_store=None,
                        discourse=build_tree(), llm=None)
    svc.fuse_mode = "rrf"
    print("blocks:", len(svc._discourse.blocks) if svc._discourse else 0)

    base_hits = llm_hits = 0
    recall30 = 0
    for t in TESTS:
        res = svc.recall(t["query"], top_k=30, use_hyde=False, sid="cog_dialog")
        base5 = [h.id for h in res.hits[:5]]
        base_ok = any(any(w in h.text for w in t["words"])
                      for h in res.hits[:5])
        in30 = any(any(w in h.text for w in t["words"])
                   for h in res.hits[:30])
        recall30 += 1 if in30 else 0
        # 候选取前 30
        cands = [(h.id, h.text) for h in res.hits[:15]]
        picked = llm_score(gw, t["query"], cands)
        text_by_id = {h.id: h.text for h in res.hits[:15]}
        llm_ok = any(any(w in text_by_id.get(pid, "") for w in t["words"])
                     for pid, _s in picked)
        base_hits += 1 if base_ok else 0
        llm_hits += 1 if llm_ok else 0
        print("\nQ: %s" % t["query"])
        print("  期望在top30: %s" % ("YES" if in30 else "NO"))
        print("  纯召回top5: %s | LLM打分top5: %s"
              % ("HIT" if base_ok else "MISS",
                 "HIT" if llm_ok else "MISS"))
        if not base_ok and llm_ok:
            print("  LLM 救回, 选中:")
            for pid, _s in picked:
                if any(w in text_by_id.get(pid, "") for w in t["words"]):
                    print("    -", text_by_id[pid][:50])
    print("\n===== 期望在top30: %d/7 | 纯召回top5: %d/7 | LLM打分top5: %d/7 ====="
          % (recall30, base_hits, llm_hits))


if __name__ == "__main__":
    main()
