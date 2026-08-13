#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Claim 级评测 — Context Recall + Faithfulness（2026-08-11, RAGAS 口径）。

标准: docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md
  Context Recall = 被检索上下文支持的参考 claim 数 / 参考 claim 总数
  Faithfulness   = 响应中被检索上下文支持的 claim 数 / 响应 claim 总数
  幻觉率 = 1 - Faithfulness

LLM claim 级判定（走 8080 网关）:
  1. 参考答案/回复 → LLM 拆 claims（每行一条）
  2. 每条 claim → LLM 判定: 能否从检索上下文推出（yes/no + 依据）

用法:
  .venv\\Scripts\\python.exe scripts/claim_eval.py --mode recall --top-k 10
  .venv\\Scripts\\python.exe scripts/claim_eval.py --mode faithful --n 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from scripts.recall_goldset import load_goldset, build_service

GW = "http://127.0.0.1:8080"


class GatewayLLM:
    def chat(self, prompt: str, max_tokens: int = 512) -> str:
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            # 2026-08-13: 提取/判定任务关思考 — deepseek-v4 推理模式会把
            # 思维链写进 content 且吃光 max_tokens（finish=length 空返回）;
            # {"type":"disabled"} 后 1.2s 返回干净条目。
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        return d["choices"][0]["message"].get("content") or ""


def split_claims(llm: GatewayLLM, text: str, question: str = "") -> list:
    """LLM 把文本拆成原子 claims（RAGAS 口径, 2026-08-13 升级）。

    RAGAS StatementGenerator 对齐: ① 带原问题（claims 无歧义）;
    ② 逐句拆解且禁止代词（消解指代）; ③ 严格提取禁止生成。
    """
    import re
    chunks = []
    # 按段落边界切块（保留上下文, 不按字符硬切）
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    buf = ""
    for p in paras:
        if len(buf) + len(p) > 600 and buf:
            chunks.append(buf)
            buf = p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf:
        chunks.append(buf)

    claims = []
    for chunk in chunks[:6]:
        prompt = (
            "给定问题和回答，逐句拆解回答中的每个句子，得到一条或多条"
            "完全可理解的原子事实陈述（claims）。要求: "
            "① 严格只提取回答中已明确陈述的事实，禁止概括、推断、补充任何"
            "回答中没有的内容; ② 每条陈述不得使用代词（把 它/这/其 等替换"
            "为具体指代对象）; ③ 每条一行，用编号开头如 1. 2. 3.; "
            "④ 跳过代码块; ⑤ 表格: 把每一行转成一条自然语言事实句"
            "（如“内容召回算法族使用 TF-IDF 和 BM25 做文本匹配”），"
            "禁止输出竖线/表头/分隔行; ⑥ 公式: 跳过公式本身，只提取"
            "公式前后的解释句; ⑦ 禁止输出 markdown 符号（###、|、\\[ 等）; "
            "⑧ 禁止任何解释、推理、思考过程或英文输出，只输出中文事实条目。\n\n"
            f"问题: {question or '(未提供)'}\n\n"
            f"回答:\n{chunk}"
        )
        # 2026-08-13: deepseek-v4-flash 对密集输出任务随机空返回
        # （实测 1200 字符/mt2048 与 400 字符/mt768 都偶发空）→
        # chunk<=600 + mt=1024 + 空结果重试 2 次。
        raw = ""
        for _attempt in range(3):
            raw = llm.chat(prompt, max_tokens=1024)
            if raw.strip():
                break
        # 跳过 ``` 围栏（代码块不是 claim）
        in_fence = False
        for line in raw.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = line.strip()
            # 2026-08-13: 过滤泄漏的推理/元信息行（模型偶发把思考混进
            # 输出: 英文句、提示词回声、自我指涉）。
            if _is_meta_noise(line):
                continue
            m = re.match(r"^\d+[.、)\s]+(.+)$", line)
            if m:
                claims.append(m.group(1).strip())
            elif line and not line.startswith(("claims", "事实")):
                claims.append(line)
    return claims[:20]


def _is_meta_noise(line: str) -> bool:
    """判断 claim 行是否为模型推理/提示词回声（2026-08-13）。"""
    if not line:
        return True
    # 英文行（模型思考通常输出英文）
    if any("a" <= ch.lower() <= "z" for ch in line) and len(
            [ch for ch in line if "a" <= ch.lower() <= "z"]) > 8:
        return True
    noise_markers = (
        "应输出", "请提供", "提供更多", "当前存在一个", "让我们",
        "Let", "we need", "User asks", "把下面的", "只输出", "跳过代码",
        "原子事实", "claims", "Claim", "每行", "编号开头", "禁止",
        "逐句", "代词", "完全可理解",
    )
    return any(m in line for m in noise_markers)


def judge_claim(llm: GatewayLLM, claim: str, context: str) -> bool:
    """判定单条 claim 能否从检索上下文推出。"""
    prompt = (
        "判断下面的陈述是否可以从提供的上下文中推出。"
        "只回答 YES 或 NO:\n\n"
        f"陈述: {claim}\n\n"
        f"上下文:\n{context}"
    )
    # 2026-08-13: max_tokens 提到 512 — 网关对 <256 有截断空返回
    # 边界（handoff 环境坑 2）, 128 在长上下文判定时偶发空 → 误判 NO。
    raw = llm.chat(prompt, max_tokens=512).strip().upper()
    # 兼容 "YES" / "YES, ..." / 中文"是" 开头判定; 防思考前缀干扰
    first = raw.split("\n")[0].strip() if raw else ""
    return first.startswith("YES") or first.startswith("是") or "YES" in first[:10]


def judge_claims_batch(llm: GatewayLLM, claims: list, context: str,
                       batch_size: int = 6) -> list:
    """批量判定（2026-08-11 提速）: 一次 LLM 调用判多条 claims。

    格式: 每行 "编号: YES/NO"。空/未判定 → 单条重试 2 次取多数。
    返回 [bool, ...] 与 claims 同序。
    """
    import re
    results = [None] * len(claims)
    for start in range(0, len(claims), batch_size):
        batch = claims[start:start + batch_size]
        numbered = "\n".join(
            "%d. %s" % (i + 1, c[:120]) for i, c in enumerate(batch))
        prompt = (
            "逐条判断下列陈述是否可以从提供的上下文中推出。"
            "每行输出 '编号: YES' 或 '编号: NO'。只输出判定:\n\n"
            f"陈述:\n{numbered}\n\n"
            f"上下文:\n{context[:15000]}"
        )
        raw = llm.chat(prompt, max_tokens=512)
        votes = {i: [] for i in range(len(batch))}
        for line in raw.splitlines():
            line = line.strip()
            m = re.match(r"^(\d+)\s*[:：.\-]\s*(YES|NO|是|否)", line, re.I)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(batch):
                    votes[idx].append(
                        m.group(2).upper().startswith(("YES", "是")))
        for i in range(len(batch)):
            if votes[i]:
                results[start + i] = max(
                    set(votes[i]), key=votes[i].count)
    # 空判定单条重试（最多 2 轮）
    for retry in range(2):
        pending = [i for i, r in enumerate(results) if r is None]
        if not pending:
            break
        for i in pending:
            results[i] = judge_claim(llm, claims[i], context)
    return [bool(r) for r in results]


def context_recall(queries, svc, top_k, llm, max_n=10):
    """Context Recall: 参考回复拆 claims → 检索上下文能否支持。"""
    total_claims = 0
    supported = 0
    per_q = []
    for qi in queries[:max_n]:
        res = svc.recall(qi["query"], top_k=top_k, use_hyde=False)
        # 判定上下文必须完整（2026-08-11 修复: 截断会导致误判）
        from scripts.recall_goldset import load_goldset
        gold = load_goldset()
        blocks = {b["id"]: b["text"] for b in gold["blocks"]}
        ctx = "\n".join(blocks.get(h.id, h.text or "") for h in res.hits[:top_k])
        # 参考 = 期望块拼接（goldset 的 reference）
        reference = "\n".join(blocks.get(e, "") for e in qi["expected"])
        if not reference.strip():
            continue
        claims = split_claims(llm, reference, qi["query"])
        if not claims:
            continue
        # 批量判定（2026-08-11 提速: 一次判 6 条, 空则单条重试）
        verdicts = judge_claims_batch(llm, claims, ctx)
        q_supported = sum(1 for v in verdicts if v)
        time.sleep(0.3)  # 网关过载保护（限流已关, 仍防上游限速）
        total_claims += len(claims)
        supported += q_supported
        per_q.append({"query": qi["query"][:40], "claims": len(claims),
                      "supported": q_supported})
        print("  [%s] claims=%d supported=%d" % (
            qi["query"][:30], len(claims), q_supported))
    cr = supported / total_claims if total_claims else 0.0
    return cr, total_claims, supported, per_q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="recall", choices=["recall", "faithful"])
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()

    llm = GatewayLLM()
    if args.mode == "recall":
        gold = load_goldset()
        svc = build_service(
            [{"id": b["id"], "text": b["text"],
              "session": b.get("session", ""),
              "vector": b.get("vector")}
             for b in gold["blocks"]], mode="vector_primary")
        print("=== Context Recall (top-%d, %d query) ===" % (args.top_k, args.n))
        cr, total, supported, per_q = context_recall(
            gold["queries"], svc, args.top_k, llm, args.n)
        print("Context Recall: %.3f (%d/%d claims)" % (cr, supported, total))
        out = {"mode": "context_recall", "top_k": args.top_k,
               "context_recall": cr, "claims_total": total,
               "claims_supported": supported, "per_query": per_q}
        with open("docs/test/CLAIM_RECALL_20260811.json", "w",
                  encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("written: docs/test/CLAIM_RECALL_20260811.json")
    else:
        run_faithfulness(llm, args.n)


def run_faithfulness(llm: GatewayLLM, n: int = 5):
    """Faithfulness（幻觉率 = 1 - F）: v3 任务回复拆 claims → 上下文支持判定。

    标准（RAGAS）: F = 响应中被检索上下文支持的 claim 数 / 响应 claim 总数。
    检索上下文 = 该 query 的粗召回 top-k（与 v3 链路同源）。

    2026-08-13 修复:
      ① 上下文必须用**全文** — RecallHit.text 只有 200 字符截断, 碎片
        上下文导致判定器找不到支撑（全任务低分的最大工件）。
      ② 接地池按任务选 — 事实型任务（文档知识）用文档语料池, 对话型
        任务用 goldset 池; 池错配 = 无支撑假阴性。
    """
    import urllib.request
    API = "http://127.0.0.1:8000"
    # 2026-08-13: 任务改为"记忆内"话题 — 原 3 任务里 2 个（DI/质数代码）
    # 不在 DialogMesh 记忆（goldset 181 块）中, agent 用参数知识作答,
    # RAGAS 口径正确判为幻觉（F=0）但作为能力展示失真。记忆内任务
    # 才能测"回复是否基于检索上下文"（goldset 有用户登录系统/代码审查/
    # hello.py 等块）。
    TASKS = {
        "simple": ("帮我规划一个用户登录系统，包含注册、JWT认证、密码找回。",
                   "goldset"),
        "code": ("写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。",
                 "goldset"),
        "explain": ("帮我规划一个代码审查任务。", "goldset"),
        # 2026-08-13: 措辞用评测集已验证的 phrasing — "DialogMesh 的...
        # 服务"措辞使答案块跌到向量 rank ~10000（措辞脆弱性, P1 HyDE
        # 查询扩展的实锤）; 用已验证措辞测忠实度本身。
        "recall_fact": ("统一召回用了哪些算法，RRF 融合提升多少？", "doc"),
    }
    gold = load_goldset()
    gold_blocks = {b["id"]: b["text"] for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="vector_primary")
    # 文档语料池（事实型任务接地源）
    import scripts.doc_recall_bench as drb
    doc_blocks = drb.load_blocks()
    drb.prepare_vectors(doc_blocks)
    doc_texts = {b["id"]: b["text"] for b in doc_blocks}
    doc_svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in doc_blocks],
        mode="vector_primary")

    def post(path, data=None):
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(API + path, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    print("=== Faithfulness (n=%d 任务) ===" % n)
    total_claims = 0
    supported = 0
    per_task = []
    tasks = list(TASKS.items())[:n]
    for task_name, (query, pool) in tasks:
        sid = post("/v3/session")["session_id"]
        resp = post(f"/v3/session/{sid}/message", {"content": query})
        content = resp.get("content", "") or ""
        if not content.strip():
            per_task.append({"task": task_name, "error": "empty reply"})
            print("  [%s] 空回复" % task_name)
            continue
        # 检索上下文（与 v3 链路同源: 粗召回 top-k, 2026-08-13 用全文）
        svc_use = doc_svc if pool == "doc" else svc
        texts_map = doc_texts if pool == "doc" else gold_blocks
        # 2026-08-13: top_k 10→20 — 答案块常排在 fused 11-20（如
        # RECALL_CAPABILITY 对"统一召回用了哪些算法"在 13 名）,
        # top-10 上下文覆盖不到 → 判定假阴性。
        res = svc_use.recall(query, top_k=20, use_hyde=False)
        ctx = "\n".join(
            (texts_map.get(h.id) or h.text or "") for h in res.hits[:20])
        claims = split_claims(llm, content, query)
        if not claims:
            per_task.append({"task": task_name, "error": "no claims"})
            continue
        q_supported = 0
        for c in claims:
            q_supported += 1 if judge_claim(llm, c, ctx) else 0
            time.sleep(0.3)
        total_claims += len(claims)
        supported += q_supported
        f = q_supported / len(claims)
        per_task.append({"task": task_name, "claims": len(claims),
                         "supported": q_supported,
                         "faithfulness": round(f, 3),
                         "hallucination_rate": round(1 - f, 3)})
        print("  [%s] claims=%d supported=%d F=%.2f 幻觉率=%.2f" % (
            task_name, len(claims), q_supported, f, 1 - f))
    if total_claims:
        f_total = supported / total_claims
        print("Faithfulness: %.3f | 幻觉率: %.3f (%d/%d claims)" % (
            f_total, 1 - f_total, supported, total_claims))
    out = {"mode": "faithfulness", "faithfulness": f_total if total_claims else None,
           "hallucination_rate": 1 - f_total if total_claims else None,
           "claims_total": total_claims, "claims_supported": supported,
           "per_task": per_task}
    with open("docs/test/FAITHFULNESS_20260811.json", "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written: docs/test/FAITHFULNESS_20260811.json")


if __name__ == "__main__":
    main()
