# -*- coding: utf-8 -*-
"""五维评测（2026-08-13）: 相关性/一致性/忠实度/流畅性/连贯性。

LLM-judge rubric（SummEval/RAGAS 对齐）: 每个任务取 v3 回答 + 接地上下文
（按任务选池, top-20 全文）, 一次调用输出五维 1-5 分 + 理由（JSON）。
thinking 关闭（deepseek-v4 推理会写进 content）; response_format json。

用法: .venv/Scripts/python.exe scripts/eval_five_dim.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GW = "http://127.0.0.1:8080"
API = "http://127.0.0.1:8000"

TASKS = {
    "simple": ("帮我规划一个用户登录系统，包含注册、JWT认证、密码找回。",
               "goldset"),
    "code": ("写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。",
             "goldset"),
    "explain": ("帮我规划一个代码审查任务。", "goldset"),
    "recall_fact": ("统一召回用了哪些算法，RRF 融合提升多少？", "doc"),
}

# Prometheus 式分档锚点 rubric（2026-08-13）: 每档有明确描述,
# judge 先写推理（reasoning）再给分（CoT, SummEval 验证相关性更高）。
RUBRIC = (
    "你是评测员。给定【问题】【回答】【参考上下文】，按 1-5 分对回答打分"
    "（5 最好）。先写一句推理（reasoning），再给出各维度分数。\n\n"
    "维度与分档锚点：\n"
    "relevance 相关性:\n"
    "  5=回答覆盖上下文全部关键信息且完全切题; 4=覆盖大部分关键信息; "
    "3=覆盖部分关键信息或有离题; 2=只覆盖少量关键信息; "
    "1=完全离题或信息缺失严重。\n"
    "consistency 一致性:\n"
    "  5=与上下文无任何事实矛盾; 4=极轻微偏差; 3=存在一两处可察觉矛盾; "
    "2=多处矛盾; 1=与上下文严重冲突。\n"
    "faithfulness 忠实度:\n"
    "  5=回答中陈述几乎全部能被上下文支持; 4=绝大多数可支持; "
    "3=约一半可支持; 2=少量可支持; 1=基本无支撑。\n"
    "fluency 流畅性:\n"
    "  5=句子通顺自然无可挑剔; 4=个别小瑕疵; 3=部分句子生硬; "
    "2=明显不通顺; 1=大量病句。\n"
    "coherence 连贯性:\n"
    "  5=结构清晰逻辑严密; 4=整体连贯有轻微跳跃; 3=结构松散; "
    "2=逻辑断裂明显; 1=杂乱无章。\n\n"
    "只输出 JSON，不要任何其他文字："
    '{"reasoning":"一句推理","relevance":n,"consistency":n,'
    '"faithfulness":n,"fluency":n,"coherence":n}'
)


class JudgeLLM:
    def chat_json(self, prompt: str) -> dict:
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": 512, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(
            GW + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        raw = d["choices"][0]["message"].get("content") or "{}"
        try:
            return json.loads(raw)
        except Exception:
            # 容错: 提取首个 { ... }
            s, e = raw.find("{"), raw.rfind("}")
            if s >= 0 and e > s:
                return json.loads(raw[s:e + 1])
            return {}


def post(path, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(API + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main():
    from scripts.recall_goldset import load_goldset, build_service
    import scripts.doc_recall_bench as drb

    llm = JudgeLLM()
    gold = load_goldset()
    gold_blocks = {b["id"]: b["text"] for b in gold["blocks"]}
    svc = build_service(
        [{"id": b["id"], "text": b["text"],
          "session": b.get("session", ""),
          "vector": b.get("vector")}
         for b in gold["blocks"]], mode="vector_primary")
    doc_blocks = drb.load_blocks()
    drb.prepare_vectors(doc_blocks)
    doc_texts = {b["id"]: b["text"] for b in doc_blocks}
    doc_svc = build_service(
        [{"id": b["id"], "text": b["text"], "session": "",
          "vector": b.get("vector")} for b in doc_blocks],
        mode="vector_primary")

    rows = []
    t_all = time.time()
    for task_name, (query, pool) in TASKS.items():
        t0 = time.time()
        sid = post("/v3/session")["session_id"]
        content = post(f"/v3/session/{sid}/message",
                       {"content": query}).get("content", "") or ""
        if not content.strip():
            rows.append({"task": task_name, "error": "empty reply"})
            print("[%s] 空回复" % task_name)
            continue
        svc_use = doc_svc if pool == "doc" else svc
        texts_map = doc_texts if pool == "doc" else gold_blocks
        res = svc_use.recall(query, top_k=20, use_hyde=False)
        ctx = "\n".join(
            (texts_map.get(h.id) or h.text or "") for h in res.hits[:20])
        prompt = (RUBRIC + "\n\n【问题】\n" + query +
                  "\n\n【回答】\n" + content[:3000] +
                  "\n\n【参考上下文】\n" + ctx[:15000])
        verdict = llm.chat_json(prompt)
        row = {"task": task_name, "pool": pool, "ms": int(
            (time.time() - t0) * 1000)}
        row.update({k: verdict.get(k) for k in (
            "relevance", "consistency", "faithfulness", "fluency",
            "coherence")})
        row["reasoning"] = verdict.get("reasoning",
                                       verdict.get("reason", ""))
        rows.append(row)
        print("[%s] rel=%s con=%s fai=%s flu=%s coh=%s | %s" % (
            task_name, row.get("relevance"), row.get("consistency"),
            row.get("faithfulness"), row.get("fluency"),
            row.get("coherence"), row.get("reasoning", "")[:40]))

    dims = ("relevance", "consistency", "faithfulness", "fluency",
            "coherence")
    out = ["# 五维评测（2026-08-13, LLM-judge 1-5）", "",
           "- 任务: 4（登录规划/hello.py/代码审查/召回事实）",
           "- 判定: deepseek-v4-flash, thinking 关闭, JSON rubric",
           "- 接地上下文: 按任务选池, top-20 全文", ""]
    for r in rows:
        if "error" in r:
            out.append("- [%s] %s" % (r["task"], r["error"]))
            continue
        out.append("- [%s] 相关=%s 一致=%s 忠实=%s 流畅=%s 连贯=%s | %s" % (
            r["task"], r.get("relevance"), r.get("consistency"),
            r.get("faithfulness"), r.get("fluency"), r.get("coherence"),
            r.get("reasoning", "")))
    out += ["", "## 汇总", ""]
    for d in dims:
        vals = [r.get(d) for r in rows if isinstance(r.get(d), (int, float))]
        if vals:
            out.append("- %s: 均值 %.2f（%s）" % (
                d, sum(vals) / len(vals), "/".join(str(v) for v in vals)))
    out.append("")
    out.append("- 总耗时 %.0fs" % (time.time() - t_all))
    with open("docs/test/FIVE_DIM_EVAL_20260813.md", "w",
              encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out[-12:]))


if __name__ == "__main__":
    main()
