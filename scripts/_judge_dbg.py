# -*- coding: utf-8 -*-
"""文件执行: judge_claim 判定调试（2026-08-11）。"""
import sys

sys.path.insert(0, ".")

from scripts.claim_eval import GatewayLLM, judge_claim


def main():
    llm = GatewayLLM()
    ctx = (
        "制作一个像 Pi 那样温暖好奇支持性的 AI agent，需要同时关注技术架构、"
        "交互设计和人格塑造三个层面。Pi 的核心优势在于它不像工具型助手，"
        "而更像一个善于倾听、会追问、有记忆的伙伴。人格与对话策略是最关键的"
        "差异点。"
    )
    tests = [
        ("命中", "Pi 的核心优势在于它不像工具型助手"),
        ("命中2", "Pi 更像一个善于倾听、会追问、有记忆的伙伴"),
        ("未命中", "今天天气很好适合出去走走"),
    ]
    out = []
    for label, claim in tests:
        r = judge_claim(llm, claim, ctx)
        out.append("%s: -> %s" % (label, r))
    with open("_judge_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
