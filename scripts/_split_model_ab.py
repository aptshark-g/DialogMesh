# -*- coding: utf-8 -*-
"""拆分模型/提示词消融（2026-08-13）: flash vs pro × 长提示 vs RAGAS 短提示。

用法: .venv/Scripts/python.exe scripts/_split_model_ab.py
"""
import sys, json, urllib.request, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

GW = "http://127.0.0.1:8080"


def chat(model, prompt, mt=2048):
    body = json.dumps({"provider": "deepseek", "model": model,
                       "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": mt, "temperature": 0.0}).encode("utf-8")
    req = urllib.request.Request(GW + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return d["choices"][0]["message"].get("content") or ""


def main():
    import urllib.request as ur
    API = "http://127.0.0.1:8000"
    def post(path, data=None):
        req = ur.Request(API + path, data=json.dumps(data or {}).encode(),
                         headers={"Content-Type": "application/json"})
        with ur.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    q = "统一召回用了哪些算法，RRF 融合提升多少？"
    sid = post("/v3/session")["session_id"]
    answer = post(f"/v3/session/{sid}/message",
                  {"content": q}).get("content", "") or ""
    print("回答长度:", len(answer))

    long_prompt = (
        "给定问题和回答，逐句拆解回答中的每个句子，得到一条或多条完全可理解的"
        "原子事实陈述（claims）。要求: ① 严格只提取回答中已明确陈述的事实，"
        "禁止概括、推断、补充任何回答中没有的内容; ② 每条陈述不得使用代词; "
        "③ 每条一行，用编号开头如 1. 2. 3.; ④ 跳过代码块; ⑤ 表格: 把每一行"
        "转成一条自然语言事实句，禁止输出竖线/表头; ⑥ 公式: 跳过公式本身，"
        "只提取公式前后的解释句; ⑦ 禁止输出 markdown 符号; ⑧ 禁止任何解释、"
        "推理、思考过程或英文输出，只输出中文事实条目。\n\n"
        f"问题: {q}\n\n回答:\n{answer[:1200]}")
    short_prompt = (
        "Given a question and an answer, analyze the complexity of each sentence "
        "in the answer. Break down each sentence into one or more fully "
        "understandable statements. Ensure that no pronouns are used in any "
        "statement. Format the outputs as numbered lines (1. 2. 3.).\n\n"
        f"Question: {q}\n\nAnswer:\n{answer[:1200]}")

    for model in ("deepseek-v4-flash", "deepseek-v4-pro"):
        for name, prompt in (("长提示", long_prompt), ("RAGAS短提示", short_prompt)):
            t0 = time.time()
            try:
                raw = chat(model, prompt)
                lines = [l for l in raw.splitlines() if l.strip()][:8]
                print("\n=== %s × %s (%.1fs, %d 字符) ===" % (
                    model, name, time.time() - t0, len(raw)))
                for l in lines:
                    print("  ", l[:90])
            except Exception as e:
                print("\n=== %s × %s 异常: %s" % (model, name, e))


if __name__ == "__main__":
    main()
