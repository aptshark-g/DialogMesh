# -*- coding: utf-8 -*-
"""文件执行: 长文本 claim 拆分是否真的空返回（2026-08-11）。"""
import json
import time
import urllib.request


def ask(prompt, mt=2048):
    body = json.dumps({
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": mt, "temperature": 0.0,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    c = d["choices"][0]["message"].get("content") or ""
    return c, d["choices"][0].get("finish_reason")


def main():
    ref = (
        "制作一个像 Pi 那样温暖好奇支持性的 AI agent，需要同时关注技术架构、"
        "交互设计和人格塑造三个层面。Pi 的核心优势在于它不像工具型助手，"
        "而更像一个善于倾听、会追问、有记忆的伙伴。人格与对话策略是最关键的"
        "差异点。Pi 的对话风格建立在 Socratic 式引导加情感认可之上。"
    )
    tests = {
        "short_plain": "数数: 一 二 三",
        "short_claim": "拆 claims: 天空是蓝的。太阳很亮。",
        "long_plain": "总结这段: " + ref,
        "long_claim": "把下面的文本拆成原子陈述, 每条一行:\n" + ref,
    }
    for k, p in tests.items():
        c, fr = ask(p)
        print("%s: len=%d finish=%s %r" % (k, len(c), fr, c[:60]))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
