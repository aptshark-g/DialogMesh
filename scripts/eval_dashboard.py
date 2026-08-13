#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评测面板 — 统一汇总各评测产物的参数/指标/口径/缺失（2026-08-11）。

目的: 用户"先实现测试的参数展现" — 此前结果散落 6+ 份 md/json,
口径不统一、有过时数据、看不到参数。本脚本读全部产物 → 输出:
  docs/test/EVAL_DASHBOARD.md   人读汇总（参数/指标/口径/缺失标注）
  docs/test/EVAL_DASHBOARD.json 机读数据（供前端阶段 B 接入）

用法: .venv\\Scripts\\python.exe scripts/eval_dashboard.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = os.path.join(ROOT, "docs", "test")


def _load_json_md(name: str):
    """产物可能是纯 JSON 或带前导文本的 md, 兼容两种。"""
    path = os.path.join(TEST_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except Exception:
        # 剥离 markdown 代码块后重试
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return {"_raw_md": raw}


def _pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "-"


def collect_memory_bench(d):
    """MEMORY_BENCH_20260810.md — 会话黄金集（RRF/linear, top-k 命中 + CP）。"""
    if d is None:
        return None
    raw = d.get("_raw_md", "")
    if raw:
        m = re.search(r"（(\d+) query / (\d+) 块）", raw)
        q = int(m.group(1)) if m else None
        b = int(m.group(2)) if m else None
        def grab(label):
            mm = re.search(re.escape(label) + r"\s*\|\s*([\d.]+)%", raw)
            return float(mm.group(1)) if mm else None
        cp = re.search(r"Context Precision@(\d+)\s*\|\s*([\d.]+)", raw)
        rb = re.search(r"top1 命中率 \|\s*[\d.]+% \|\s*([\d.]+)%", raw)
        return {
            "name": "记忆评测（会话黄金集）",
            "query": q, "blocks": b,
            "mode": "rrf", "top_k": 5,
            "top1": grab("top1 命中率"),
            "top3": grab("top3 命中率"),
            "top5": grab("top5 命中率"),
            "random_baseline": float(rb.group(1)) if rb else None,
            "context_precision": float(cp.group(2)) if cp else None,
            "cp_at": int(cp.group(1)) if cp else None,
        }
    return None


def collect_refine(d, kind):
    """REFINE_ABLATION / REFINE_BENCH — 精细化链路（L0/L1/L2 消融 + LLM 选择）。"""
    if d is None:
        return None
    total = d.get("n")
    if kind == "ablation":
        s = d.get("stats", {})
        t = d.get("times", {})
        return {
            "name": "精细化消融（L0 粗召回 / L1 子图 / L2 LLM 选择）",
            "query": total, "top_k": d.get("top_k"),
            "L0_top1": _pct(s.get("L0", 0), total),
            "L1_top1": _pct(s.get("L1", 0), total),
            "L2_top1": _pct(s.get("L2", 0), total),
            "L0_avg_ms": round(t.get("L0", {}).get("avg_ms", 0), 1),
            "L1_avg_ms": round(t.get("L1", {}).get("avg_ms", 0), 3),
            "L2_avg_ms": round(t.get("L2", {}).get("avg_ms", 0), 1),
            "note": "goldset 无图数据 → L1 实为 top-10 透传, 非真图搜索",
        }
    return {
        "name": "精细化基准（粗召回 top1 vs LLM 挑选 top1）",
        "query": total, "top_k": d.get("top_k"),
        "coarse_top1": _pct(d.get("coarse_top1", 0), total),
        "refine_top1": _pct(d.get("refine_top1", 0), total),
        "avg_select_ms": round(d.get("avg_select_ms", 0), 1),
    }


def collect_agent(d):
    """AGENT_BENCH — 真实 v3 链路任务评测。"""
    if d is None:
        return None
    s = d.get("summary", {})
    avg_ms = s.get("avg_latency_ms")
    p95_ms = s.get("p95_latency_ms")
    tp = s.get("tokens_prompt")
    tc = s.get("tokens_completion")
    return {
        "name": "Agent 任务评测（真实 v3 链路）",
        "n": s.get("n"),
        "success_rate": s.get("success_rate"),
        "avg_latency_s": round(avg_ms / 1000, 1) if avg_ms else None,
        "p95_latency_s": round(p95_ms / 1000, 1) if p95_ms else None,
        "tokens_per_task": round((tp + tc) / s.get("n", 1)) if tp and tc else None,
    }


def collect_doc_recall(d):
    """DOC_RECALL_BENCH — 文档域 2444 块 50 query。"""
    if d is None:
        return None
    raw = d.get("_raw_md", "")
    if not raw:
        return None
    m = re.search(r"语料:\s*(\d+) 块", raw)
    blocks = int(m.group(1)) if m else None
    m2 = re.search(r"Query:\s*(\d+)", raw)
    queries = int(m2.group(1)) if m2 else None
    rb = re.search(r"随机基线:\s*([\d.]+)%", raw)
    top1 = re.search(r"\|\s*linear\s*\|\s*([\d.]+)%", raw)
    mrr = re.search(r"\|\s*linear\s*\| [\d.]+%[^|]*\| [\d]+ \| [\d]+ \| ([\d.]+)", raw)
    return {
        "name": "文档域召回（docs/only 全量）",
        "query": queries, "blocks": blocks,
        "random_baseline": float(rb.group(1)) if rb else None,
        "top1_linear": float(top1.group(1)) if top1 else None,
        "mrr_linear": float(mrr.group(1)) if mrr else None,
    }


def collect_variant(d):
    """DOC_RECALL_VARIANT_BENCH — BGE-M3 跨语言变体。"""
    if d is None:
        return None
    raw = d.get("_raw_md", "")
    if not raw:
        return None
    out = {"name": "跨语言变体评测（BGE-M3 统一）"}
    for label, key in [("原查询", "orig"), ("变体[zh_syn]", "zh_syn"),
                       ("变体[en]", "en"), ("变体[casual]", "casual"),
                       ("变体[全部]", "variant_all")]:
        m = re.search(re.escape(label) + r"\s*\|\s*\d+\s*\|\s*([\d.]+)%", raw)
        if m:
            out[key + "_top1"] = float(m.group(1))
    return out


def main():
    sections = []
    data = {}

    mb = collect_memory_bench(_load_json_md("MEMORY_BENCH_20260810.md"))
    if mb:
        data["memory_bench"] = mb
        sections.append(mb)

    for name, kind in [("REFINE_ABLATION_20260810.md", "ablation"),
                       ("REFINE_BENCH_20260810.md", "bench")]:
        d = collect_refine(_load_json_md(name), kind)
        if d:
            data["refine_" + kind] = d
            sections.append(d)

    ab = collect_agent(_load_json_md("AGENT_BENCH_20260810.md"))
    if ab:
        data["agent_bench"] = ab
        sections.append(ab)

    dr = collect_doc_recall(_load_json_md("DOC_RECALL_BENCH_20260809.md"))
    if dr:
        data["doc_recall"] = dr
        sections.append(dr)

    var = collect_variant(_load_json_md("DOC_RECALL_VARIANT_BENCH_20260810.md"))
    if var:
        data["variant"] = var
        sections.append(var)

    lines = ["# DialogMesh 评测面板 — 统一参数与指标（2026-08-11）", "",
             "> 自动生成: `scripts/eval_dashboard.py`（读 docs/test/ 产物, 不重跑评测）",
             "> 口径: RAGAS 标准 docs/only/recall/RECALL_EVAL_STANDARDS_20260810.md",
             "> 状态标注: ✅ 已实现 / ⚠️ 口径受限 / ❌ 未实现", ""]
    for s in sections:
        lines += ["---", "", "## " + s.get("name", "?"), ""]
        for k, v in s.items():
            if k == "name":
                continue
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    lines += ["## 缺失/受限（诚实标注）", "",
              "- ❌ **Context Recall**（claim 级, LLM）: 未实现 — memory_bench 只做块级命中",
              "- ❌ **Faithfulness/幻觉率**（claim 级, LLM）: 未实现 — 需 v3 回复拆 claims 判定",
              "- ⚠️ **L1 子图**在 goldset 无图数据下 = top-10 透传, 非真图搜索",
              "- ⚠️ **AGENT_EVAL_SUMMARY** 中记忆指标为旧集（40 query/218 块）; 现为 82/360",
              "- ⚠️ **REFINE_CHAIN_DUMP** LLM 返回空为网关缓存 bug（已修, 可重跑）", ""]

    out_md = os.path.join(TEST_DIR, "EVAL_DASHBOARD.md")
    out_json = os.path.join(TEST_DIR, "EVAL_DASHBOARD.json")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("written: %s" % out_md)
    print("written: %s" % out_json)


if __name__ == "__main__":
    main()
