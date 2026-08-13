#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""层3 变体查询集生成 — LLM 把 50 条人工查询各生成 3 种变体。

变体类型:
  zh_syn  = 同义改写（中文, 换词换句式, 语义不变）
  en      = 英文翻译/表达
  casual  = 口语化（像开发者随口问）

输出: docs/test/recall_queries_variants.json
  [{id, variant_type, query, original_id, original_query, expected, level}]
expected 从原查询继承（变体语义等价 → 命中规则不变）。
"""
from __future__ import annotations
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUERIES = os.path.join(ROOT, "docs", "test", "recall_queries.json")
OUT = os.path.join(ROOT, "docs", "test", "recall_queries_variants.json")
GATEWAY = os.environ.get("DM_GATEWAY", "http://127.0.0.1:8080")
MODEL = os.environ.get("DM_VARIANT_MODEL", "deepseek-v4-flash")
BATCH = 4
MAX_TOKENS = 2048

PROMPTS = {
    "zh_syn": (
        "你是检索查询改写专家。把下面每条用户查询改写为语义等价的中文同义句"
        "（换用不同措辞/句式, 保留全部关键信息与术语）。只输出 JSON 数组, "
        "元素为改写的单句查询, 数量与输入一致, 不要编号、不要解释。"
    ),
    "en": (
        "You rewrite search queries into natural English equivalents."
        " Keep all key terms and meaning. Output ONLY a JSON array of "
        "single sentences, same count as input, no numbering, no explanation."
    ),
    "casual": (
        "把下面每条查询改写成开发者随手打字的那种口语化问法"
        "（可以口语、略随意, 但保留关键术语）。只输出 JSON 数组, "
        "元素为单句, 数量与输入一致, 不要编号、不要解释。"
    ),
}

def chat(messages, temperature=0.6):
    url = f"{GATEWAY}/v1/chat/completions"
    body = json.dumps({
        "provider": "deepseek",
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": MAX_TOKENS,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]

def parse_json_array(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    return json.loads(text[start:end + 1])

def main():
    queries = json.load(open(QUERIES, encoding="utf-8"))["queries"]
    print(f"源查询: {len(queries)} 条")
    variants = []
    for vtype, prompt in PROMPTS.items():
        done = 0
        for i in range(0, len(queries), BATCH):
            chunk = queries[i:i + BATCH]
            lines = [f"{j+1}. {q['query']}" for j, q in enumerate(chunk)]
            user = "\n".join(lines)
            for attempt in range(3):
                try:
                    out = chat([
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user},
                    ])
                    arr = parse_json_array(out)
                    if arr is None or len(arr) != len(chunk):
                        raise ValueError(f"bad array len={len(arr) if arr else 0}")
                    break
                except Exception as e:
                    print(f"  [{vtype}] batch@{i} retry {attempt+1}: {e}")
                    time.sleep(3)
                    arr = None
            if not arr:
                print(f"  [{vtype}] batch@{i} FAILED — 跳过该批")
                continue
            for j, (q, vq) in enumerate(zip(chunk, arr)):
                vq = str(vq).strip().strip("\"'").strip()
                if not vq or len(vq) < 4:
                    continue
                variants.append({
                    "id": f"v{len(variants)+1:03d}",
                    "variant_type": vtype,
                    "query": vq,
                    "original_id": q.get("id"),
                    "original_query": q["query"],
                    "expected": list(q.get("expected") or []),
                    "level": q.get("level", "simple"),
                })
                done += 1
            print(f"  [{vtype}] {done}/{len(queries)}")
    json.dump({"meta": {
        "created": "2026-08-10",
        "purpose": "层3 变体评测查询集 (LLM 生成)",
        "source": f"recall_queries.json x{len(PROMPTS)} 变体类型",
        "gateway": GATEWAY, "model": MODEL,
    }, "queries": variants}, open(OUT, "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)
    print(f"变体总数: {len(variants)} → {OUT}")

if __name__ == "__main__":
    main()
