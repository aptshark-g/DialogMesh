# -*- coding: utf-8 -*-
"""文件执行: split_claims 调试（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.claim_eval import GatewayLLM, split_claims


def main():
    llm = GatewayLLM()
    ref = (
        "制作一个像 Pi 那样温暖好奇支持性的 AI agent，需要同时关注技术架构、"
        "交互设计和人格塑造三个层面。Pi 的核心优势在于它不像工具型助手，"
        "而更像一个善于倾听、会追问、有记忆的伙伴。人格与对话策略是最关键的"
        "差异点。Pi 的对话风格建立在 Socratic 式引导加情感认可之上。"
    )
    # 对比三种指令措辞（mt=2048）
    prompts = {
        "numbered": "把下面的文本拆成独立的原子事实陈述。每条一行, 用编号开头如 1. 2. 3.。只输出陈述:\n\n" + ref,
        "semicolon": "把下面的文本拆成独立的原子事实陈述, 用分号分隔。只输出陈述:\n\n" + ref,
        "json": "把下面的文本拆成独立的原子事实陈述, 输出 JSON 数组, 每个元素一条:\n\n" + ref,
        "plain_list": "列出这段文本中的事实:\n\n" + ref,
    }
    results = {}
    for k, p in prompts.items():
        raw = llm.chat(p, max_tokens=2048)
        results[k] = raw
    with open("_split_out.txt", "w", encoding="utf-8") as f:
        for k, r in results.items():
            f.write("== %s (len=%d): %r\n" % (k, len(r), r[:200]))
    print("done")


if __name__ == "__main__":
    main()
