#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文档语料召回跑分 — 625 份真实设计文档作为召回测试语料（量化体系第一块）。

设计: RECALL_EXECUTION_BRIDGE_DESIGN §八（docs 语料 = 天然测试资源）。

- 语料: docs/ + docs/only/ 全量 md, 按章节切块（块带 path 索引 = 执行层
  精确查阅的真实来源）
- Query: 每块的章节标题/文档标题（self-retrieval: 应命中自己的源块）
- 指标: top1/top3/top5 命中率 + MRR + 随机基线
- 对比: linear vs rrf 融合
- 漂移候选: 源块未进 top5 的 query 列表（文档-代码/新旧文档漂移审计线索）

用法:
    python scripts/doc_recall_bench.py                          # 全量+人工查询集
    python scripts/doc_recall_bench.py --queries docs/test/recall_queries.json
    python scripts/doc_recall_bench.py --auto-queries 300       # 辅助: 标题自生成
    python scripts/doc_recall_bench.py --limit 50 --mode rrf    # 快速试跑
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DOC_DIRS = ["docs", os.path.join("docs", "only")]
BLOCK_MAX_CHARS = 2000      # 单块索引文本上限（召回匹配用, 真实内容走 path）
QUERY_MIN_CHARS = 4
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache.json")
TERM_CACHE = os.path.join(ROOT, "scripts", ".recall_term_index.json")


class FakeBlock:
    def __init__(self, bid, text, path=None):
        self.block_id = bid
        self._raw_text = text
        self.parent_id = None
        self.child_ids = []
        self.status = "active"
        self.atomic_units = []
        self._path = path


class FakeDiscourse:
    def __init__(self, blocks):
        self.blocks = {b.block_id: b for b in blocks}


# ── 语料构建: md → 章节块（带 path 索引）────────────────────

def _heading_level(line: str) -> int:
    m = re.match(r"^(#{1,6})\s+", line)
    return len(m.group(1)) if m else 0


def split_markdown(text: str) -> list:
    """按 ## 级标题切块。返回 [(heading, content)]。"""
    lines = text.splitlines()
    sections = []
    cur_heading = ""
    cur = []
    for line in lines:
        lvl = _heading_level(line)
        if lvl >= 2:
            if cur or cur_heading:
                sections.append((cur_heading, "\n".join(cur).strip()))
            cur_heading = re.sub(r"^#+\s+", "", line).strip()
            cur = []
        else:
            cur.append(line)
    if cur or cur_heading:
        sections.append((cur_heading, "\n".join(cur).strip()))
    return sections


def load_blocks(limit: int = 0) -> list:
    """全量文档 → 块列表 [{id, text, path, heading, doc}]。"""
    blocks = []
    files = []
    for d in DOC_DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, _, fnames in os.walk(base):
            for fn in sorted(fnames):
                if fn.endswith(".md"):
                    files.append(os.path.join(dirpath, fn))
    if limit:
        files = files[:limit]
    for fp in sorted(files):
        rel = os.path.relpath(fp, ROOT).replace("\\", "/")
        try:
            with open(fp, encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        if not text.strip():
            continue
        created_at = _doc_timestamp(rel, fp)
        sections = split_markdown(text)
        if not sections or all(not c for _, c in sections):
            sections = [("", text)]
        for heading, content in sections:
            body = (content or "")[:BLOCK_MAX_CHARS]
            if not body.strip():
                continue
            bid = f"{rel}#{heading[:40]}" if heading else f"{rel}#file"
            blocks.append({
                "id": bid, "text": body, "path": [rel, heading or ""],
                "heading": heading, "doc": rel, "temperature": "active",
                "created_at": created_at,
            })
    return blocks


def _doc_timestamp(rel: str, fp: str) -> float:
    """文档时间戳: 优先文件名日期（_YYYYMMDD）, 否则 mtime。"""
    m = re.search(r"_(\d{8})", rel)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").timestamp()
        except ValueError:
            pass
    try:
        return os.path.getmtime(fp)
    except OSError:
        return 0.0


def prepare_vectors(blocks: list, skip: bool = False) -> None:
    """批量计算块向量 + 磁盘缓存（重跑秒级）。

    提速: ①批量 encode(batch_size=32) 摊薄 CPU 开销 ~10x
          ②缓存落盘 scripts/.recall_vec_cache.json, 二次跑零 embedding
    可选 GPU: 装 CUDA 版 torch 后自动 device=cuda（再 10-50x）。
    """
    if skip:
        return
    cache = {}
    if os.path.exists(VEC_CACHE):
        try:
            with open(VEC_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    uncached = [(b, b["id"]) for b in blocks
                if b["id"] not in cache and not b.get("vector")]
    if not uncached:
        for b in blocks:
            if b["id"] in cache:
                b["vector"] = cache[b["id"]]
        return
    try:
        from core.agent.compiler.semantic_encoder import get_encoder
        enc = get_encoder()
        t0 = time.time()
        texts = [b["text"][:500] for b, _ in uncached]
        vectors = enc.encode(texts, batch_size=32, normalize=True)
        for (b, bid), vec in zip(uncached, vectors):
            v = vec.tolist() if hasattr(vec, "tolist") else list(vec)
            b["vector"] = v
            cache[bid] = v
        with open(VEC_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f"  [vector] {len(uncached)} 块批量编码完成 "
              f"({time.time()-t0:.1f}s, 缓存 {VEC_CACHE})")
    except Exception as e:
        print(f"  [vector] 编码失败, 降级跳过: {e}")


def preindex_terms(blocks: list) -> None:
    """预索引: 每块 jieba 分词一次（消灭每 query 重复分词）。

    粗筛候选集用词项交集, 真打分仍走 RecallService（只对候选块）。
    """
    cache = {}
    if os.path.exists(TERM_CACHE):
        try:
            with open(TERM_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    try:
        import jieba
        for b in blocks:
            bid = b["id"]
            if bid not in cache:
                cache[bid] = list(set(jieba.cut(b["text"][:1000])))
        with open(TERM_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        print(f"  [index] 词项索引失败, 降级为空: {e}")
        cache = {}
    for b in blocks:
        b["terms"] = cache.get(b["id"], [])


def coarse_candidates(query: str, blocks: list, top_c: int = 200) -> list:
    """粗筛: query 词项与块词项交集排序 → top-C 候选块（供真打分）。"""
    try:
        import jieba
        qterms = set(jieba.cut(query))
    except Exception:
        qterms = set(query)
    scored = []
    for b in blocks:
        terms = b.get("terms") or []
        overlap = sum(1 for t in qterms if t in terms)
        if overlap > 0:
            scored.append((overlap, b))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in scored[:top_c]]


def build_queries(blocks, max_queries: int = 300) -> list:
    """块标题 → query（self-retrieval: expected = 源块）。去重/过滤。"""
    queries = []
    seen = set()
    for b in blocks:
        q = (b["heading"] or "").strip()
        if len(q) < QUERY_MIN_CHARS or q in seen:
            continue
        if re.fullmatch(r"[\d\s\W]+", q):
            continue
        seen.add(q)
        queries.append({"query": q, "expected": [b["id"]], "doc": b["doc"]})
        if len(queries) >= max_queries:
            break
    return queries


def load_external_queries(path: str) -> list:
    """外部人工查询集: [{query, expected(doc paths), level}]。
    命中规则 = 命中的块属于 expected 任一文档。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    queries = []
    for q in data.get("queries", []):
        query = str(q.get("query", "")).strip()
        expected = [str(x) for x in (q.get("expected") or [])]
        if not query or not expected:
            continue
        queries.append({
            "query": query, "expected_docs": set(expected),
            "level": str(q.get("level", "simple")),
        })
    return queries


# ── 跑分 ─────────────────────────────────────────────────────

def build_service(blocks, mode="linear", single=None):
    from core.agent.recall.recall_service import RecallService
    discourse = FakeDiscourse([
        FakeBlock(b["id"], b["text"], b.get("path")) for b in blocks])
    svc = RecallService(engine=None, chunk_store=None, discourse=discourse,
                        llm=None)
    svc.fuse_mode = mode
    svc.single_source = single
    return svc


def evaluate(service, queries, top_k=5, blocks=None, top_c=0):
    hits1 = hits3 = hits5 = 0
    mrr = 0.0
    misses = []
    by_level = {}
    for qi in queries:
        if blocks and top_c > 0:
            # 粗筛候选集 → 真打分只跑候选块（粗召回→精排 的评测侧复刻）
            cand = coarse_candidates(qi["query"], blocks, top_c)
            service._ensure_blocks = (
                lambda sid, _c=cand: _c)
            service._ensure_global_blocks = lambda: []
        res = service.recall(qi["query"], top_k=top_k, use_hyde=False)
        rank = None
        for i, h in enumerate(res.hits, 1):
            if _hit_matches(h.id, qi):
                rank = i
                break
        level = qi.get("level", "simple")
        st = by_level.setdefault(level, {"top1": 0, "n": 0, "mrr": 0.0})
        st["n"] += 1
        if rank is None:
            misses.append((qi["query"][:60],
                           ",".join(sorted(qi.get("expected_docs", [])))[:60],
                           [h.id.split("#")[0] for h in res.hits[:3]]))
            continue
        mrr += 1.0 / rank
        st["mrr"] += 1.0 / rank
        if rank <= 1:
            hits1 += 1
            st["top1"] += 1
        if rank <= 3:
            hits3 += 1
        if rank <= 5:
            hits5 += 1
    total = len(queries)
    return {
        "total": total,
        "top1": hits1, "top3": hits3, "top5": hits5,
        "mrr": mrr / max(total, 1),
        "misses": misses,
        "by_level": by_level,
    }


def _hit_matches(hit_id: str, qi: dict) -> bool:
    """命中判定: 块 id（rel/path#heading）属于 expected 任一文档。"""
    doc = hit_id.split("#")[0]
    if doc in qi.get("expected_docs", set()):
        return True
    # 兼容 expected 用绝对路径前缀
    for ed in qi.get("expected_docs", set()):
        if doc.startswith(ed) or ed.startswith(doc):
            return True
    return False


def random_baseline(blocks, queries, top_k=5):
    pool = max(len(blocks), 1)
    return 1.0 - (1.0 - 1.0 / pool) ** top_k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 个文档")
    ap.add_argument("--queries", default="",
                    help="外部人工查询集 JSON（层2）")
    ap.add_argument("--auto-queries", type=int, default=0,
                    help="辅助: 标题自生成 query 数（默认 0 = 不用）")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--mode", default="all", choices=["all", "linear", "rrf"])
    ap.add_argument("--skip-vectors", action="store_true",
                    help="跳过向量编码（bm25-only 快速模式）")
    ap.add_argument("--single", default=None,
                    choices=["vector", "bm25", "spo", "hyde", "assoc"],
                    help="单源模式（不融合）")
    ap.add_argument("--top-c", type=int, default=0,
                    help="粗筛候选集大小（0 = 全库扫描; 推荐 200）")
    ap.add_argument("--dirs", default="",
                    help="语料目录逗号分隔（默认 docs + docs/only; "
                         "评测推荐 only）")
    ap.add_argument("--temporal-days", type=float, default=0.0,
                    help="时序约束半衰期天数（0=关; 评测推荐 60）")
    args = ap.parse_args()

    print("[1/3] 构建语料...")
    if args.dirs:
        global DOC_DIRS
        DOC_DIRS = [d.strip() for d in args.dirs.split(",")]
    blocks = load_blocks(args.limit)
    if not args.skip_vectors:
        prepare_vectors(blocks)
    else:
        print("  [vector] 跳过（--skip-vectors, bm25-only 快速模式）")
    if args.top_c > 0:
        preindex_terms(blocks)
    if args.queries:
        queries = load_external_queries(args.queries)
        print(f"  语料: {len(blocks)} 块 / 外部查询集: {len(queries)} query "
              f"({args.queries})")
    else:
        queries = build_queries(blocks, args.auto_queries)
        print(f"  语料: {len(blocks)} 块 / 标题自生成: {len(queries)} query "
              "（辅助模式）")
    print(f"  语料: {len(blocks)} 块 / {len(queries)} query")

    print("[2/3] 跑分...")
    modes = ["linear", "rrf"] if args.mode == "all" else [args.mode]
    if args.single:
        modes = ["single:" + args.single]
    results = {}
    for mode in modes:
        t0 = time.time()
        svc = build_service(blocks, mode, args.single)
        if args.temporal_days > 0:
            svc.time_half_life_days = args.temporal_days
        results[mode] = evaluate(svc, queries, args.top_k,
                                 blocks, args.top_c)
        r = results[mode]
        print(f"  {mode}: top1={r['top1']}/{r['total']} ({100.0*r['top1']/max(r['total'],1):.1f}%) "
              f"top3={r['top3']} top5={r['top5']} MRR={r['mrr']:.3f} "
              f"({time.time()-t0:.1f}s)")

    print("[3/3] 落盘报告...")
    report = render_report(blocks, queries, results, args)
    out_dir = os.path.join(ROOT, "docs", "test")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "DOC_RECALL_BENCH_20260809.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告: {out_path}")


def render_report(blocks, queries, results, args) -> str:
    rb = random_baseline(blocks, queries, args.top_k)
    qsrc = (args.queries if args.queries
            else f"标题自生成 x{args.auto_queries}（辅助）")
    lines = [
        "# 文档语料召回跑分（2026-08-09）",
        "",
        f"- 语料: {len(blocks)} 块（docs + docs/only 全量 md, 章节切块, "
        "块带 path 索引 = 执行层精确查阅来源）",
        f"- Query: {len(queries)}（{qsrc}）",
        f"- 随机基线: {100.0*rb:.1f}%",
        "",
        "## 指标",
        "",
        "| 模式 | top1 | top3 | top5 | MRR |",
        "|---|---|---|---|---|",
    ]
    for mode, r in results.items():
        lines.append(
            f"| {mode} | {100.0*r['top1']/max(r['total'],1):.1f}% "
            f"({r['top1']}/{r['total']}) | {r['top3']} | {r['top5']} "
            f"| {r['mrr']:.3f} |")
    lines += ["", "## 分级统计（按 query level）", "",
              "| 级别 | 模式 | top1 | n | MRR |", "|---|---|---|---|---|"]
    for mode, r in results.items():
        for level, st in sorted(r.get("by_level", {}).items()):
            lines.append(
                f"| {level} | {mode} | "
                f"{100.0*st['top1']/max(st['n'],1):.1f}% | {st['n']} | "
                f"{st['mrr']/max(st['n'],1):.3f} |")
    lines += ["", "## 漂移候选（源块未进 top5, 文档审计线索）", ""]
    worst = sorted(results.values(), key=lambda r: -len(r["misses"]))[0]
    for q, doc, topdocs in worst["misses"][:15]:
        lines.append(f"- query: `{q}` (期望 `{doc}`) → top: {topdocs}")
    if not worst["misses"]:
        lines.append("- 无")
    lines += ["", "## 复跑", "", "```bash",
              f"python scripts/doc_recall_bench.py --queries {args.queries}"
              if args.queries else
              f"python scripts/doc_recall_bench.py --auto-queries {args.auto_queries}",
              "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
