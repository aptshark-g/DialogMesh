#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LLM 精排试点分析 — 从试点报告逐条数据计算混合策略（2026-08-14）。

纯 LLM 替换会拆掉正确 top1（下行 > 上行）; 有意义的形态是"受限覆盖":
仅当 LLM 的挑选落在融合候选排名 (1, cap] 内才覆盖, 否则保留 fused top1。
本脚本从 docs/test/LLM_RERANK_PILOT_YYYYMMDD.md 读取逐条数据,
模拟各 cap 的 top1, 并把分析段回写进报告（幂等, 重跑试点后重跑本脚本）。

用法: .venv\\Scripts\\python.exe scripts/llm_rerank_analyze.py [--path ...]
"""
from __future__ import annotations

import io
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse(path: str) -> list:
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for l in f:
            m = re.match(
                r"- fused=(True|False) llm=(True|False) rank=\S+ pick=(\S+) "
                r"gap=(True|False) \d+ms", l.strip())
            if m:
                rows.append({
                    "fused": m.group(1) == "True",
                    "llm": m.group(2) == "True",
                    "pick": None if m.group(3) == "None"
                    else int(m.group(3)),
                })
    return rows


def main():
    path = "docs/test/LLM_RERANK_PILOT_%s.md" % time.strftime("%Y%m%d")
    if not os.path.exists(path):
        print("report not found:", path)
        return 1
    rows = parse(path)
    if not rows:
        print("no rows parsed")
        return 1
    n = len(rows)
    fused = sum(r["fused"] for r in rows)
    llm = sum(r["llm"] for r in rows)
    down = [r["pick"] for r in rows if r["fused"] and not r["llm"]
            and r["pick"]]
    up = [r["pick"] for r in rows if not r["fused"] and r["llm"]
          and r["pick"]]
    agree_ok = sum(1 for r in rows if r["fused"] and r["pick"] == 1)
    agree_wrong = sum(1 for r in rows
                      if not r["fused"] and r["pick"] == 1)
    cap_lines = []
    for cap in (1, 2, 3, 4, 5, 6, 7, 8, 10, 15):
        ok = sum(
            r["llm"] if (r["pick"] is not None and 1 < r["pick"] <= cap)
            else r["fused"]
            for r in rows)
        star = " **" if cap == 4 else ""
        cap_lines.append(
            f"| 受限覆盖 cap={cap:>2} | {ok}/{n} ({100.0*ok/n:.1f}%){star} |")
    analysis = [
        "",
        "## 混合策略模拟（2026-08-14, 从逐条数据计算）", "",
        f"- 运行: {n} 条 doc 查询 | fused top1: {fused}/{n} "
        f"({100.0*fused/n:.1f}%) | LLM top1: {llm}/{n} "
        f"({100.0*llm/n:.1f}%)",
        f"- 上行（fused miss → LLM 中）: {len(up)} | 下行（fused 中 → "
        f"LLM 拆）: {len(down)}", "",
        "| 策略 | top1 | 说明 |",
        "|---|---|---|",
        f"| V1 纯 fused | {fused}/{n} ({100.0*fused/n:.1f}%) | 现状基线 |",
        f"| V2 纯 LLM 替换 | {llm}/{n} ({100.0*llm/n:.1f}%) | 拆掉 "
        f"{len(down)} 条正确的, 只补 {len(up)} 条 — 小模型单独排序劣于融合 |",
    ] + cap_lines + [
        "",
        "关键观察:",
        f"- 下行 pick 排名 {sorted(down)} / 上行 pick 排名 {sorted(up)} "
        "— 排名信号不能完全区分, cap 值换数据集需重验",
        f"- LLM 与 fused 一致（pick=1）: fused 对 {agree_ok} 条 / "
        f"fused 错 {agree_wrong} 条 — 'LLM 同意'是强确认信号, "
        "'LLM 不同意'才是模糊区",
        "- 受限覆盖 cap=4 是模拟最优（+4.9pp）; 生产接入建议: "
        "DM_LLM_RERANK=1（默认关）+ BASE/MODEL/TIMEOUT 环境变量, "
        "失败降级 fused, 仅 doc/知识类意图启用",
        "- 待网关恢复后用 deepseek-v4-flash 复跑对比模型质量（下行是否"
        "收窄）, 再决定小模型/云端模型入生产",
        "",
    ]
    with io.open(path, encoding="utf-8") as f:
        txt = f.read()
    marker = "## 逐条"
    idx = txt.find(marker)
    if idx < 0:
        print("no 逐条 marker")
        return 1
    head = txt[:idx].rstrip() + "\n"
    tail = txt[idx:]
    # 幂等: 去掉旧分析段
    old = head.find("## 混合策略模拟")
    if old >= 0:
        head = head[:old].rstrip() + "\n"
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(analysis) + "\n" + tail)
    print("analysis written to", path)
    print("\n".join(analysis[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
