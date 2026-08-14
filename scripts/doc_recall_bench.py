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

# 2026-08-14 语料卫生修复:
# ① walk "docs" 已递归覆盖 docs/only — 双目录导致 docs/only 每块
#    双份装载（#2 消歧后缀）, top-k 被重复块占位, recall@k 实际减半;
# ② 排除 docs/test（评测文档引用 query 原文 → 基准自污染, 实测 832 处）
#    与 docs/notTish（另一项目参考文档, 非 DialogMesh 知识）。
EXCLUDE_PREFIXES = ("docs/test/", "docs/notTish/")
DOC_DIRS = ["docs"]
QUERY_MIN_CHARS = 4
# 结构粒度上限（2026-08-12）: 超大节块按 ### → 段落 → 行 递归切分,
# 全部在结构边界上切（标题/空行/行首）, 绝不从文字中间硬截。
SECTION_MAX_CHARS = 3000
# 粗召回嵌入窗口（2026-08-12, 两级粒度设计 12.2）: 向量嵌入
# "标题 + 核心内容"。窗口 = 结构块上限（SECTION_MAX_CHARS=3000）,
# 与切分同颗粒度 — 结构切分后 99.99% 块 <= 3000 字符, 嵌入覆盖全文;
# 唯一 >3000 的是单行无换行巨文本（无结构边界可切, 前缀窗口兜底）。
# 全文嵌入被旧语料的巨块（>8K 字符 → bge-m3 8192 token 序列,
# O(n²) 注意力）拖慢实测 30 分钟+; 结构切分后 3000 窗口 ≈ 2000 token,
# 批量 GPU 编码 ~13 分钟一次性。
EMBED_WINDOW = SECTION_MAX_CHARS
# v3（2026-08-12）: 结构切分语料 + 3000 窗口（v2 = 未切分语料 + 1500 窗口）。
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache_v3.json")
# 2026-08-14（doc 域 miss 修复, 父级上下文）: 与 core/doc_corpus 同步 —
# 嵌入窗口加文件标题（doc_title | 节标题\n内容）, 缓存升 v4。
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache_v4.json")
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


def _doc_title(text: str, rel: str) -> str:
    """文件标题（父级上下文, 2026-08-14）: 首个 H1; 无 H1 → 文件名。"""
    for line in text.splitlines()[:30]:
        lvl = _heading_level(line)
        if lvl == 1:
            return re.sub(r"^#+\s+", "", line).strip()
    name = os.path.basename(rel)
    return name[:-3] if name.endswith(".md") else name


def _split_at_level(text: str, level: int) -> list:
    """按 >=level 级标题切分。返回 [(heading, content)]。"""
    lines = text.splitlines()
    sections = []
    cur_heading = ""
    cur = []
    for line in lines:
        lvl = _heading_level(line)
        if lvl >= level:
            if cur or cur_heading:
                sections.append((cur_heading, "\n".join(cur).strip()))
            cur_heading = re.sub(r"^#+\s+", "", line).strip()
            cur = []
        else:
            cur.append(line)
    if cur or cur_heading:
        sections.append((cur_heading, "\n".join(cur).strip()))
    return sections


def _split_paragraphs(text: str, max_chars: int) -> list:
    """按空行段落整组聚合到 <= max_chars（不切段内文字）。"""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    out = []
    buf = ""
    for p in paras:
        if buf and len(buf) + len(p) + 2 > max_chars:
            out.append(buf)
            buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf:
        out.append(buf)
    return out


def _split_lines(text: str, max_chars: int) -> list:
    """超长段落/表格按行聚合（md 行 = 结构单元, 表格按行组切, 不切行内）。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    out = []
    buf = ""
    for ln in lines:
        if buf and len(buf) + len(ln) + 1 > max_chars:
            out.append(buf)
            buf = ln
        else:
            buf = (buf + "\n" + ln) if buf else ln
    if buf:
        out.append(buf)
    return out


def split_markdown(text: str, max_chars: int = SECTION_MAX_CHARS) -> list:
    """按 ## 级标题切块; 超大节块按结构递归切分（### → 段落 → 行）。

    2026-08-12: 此前超大节块（最大 31K 字符）整块保留 → 嵌入被
    bge-m3 8192 token 序列拖到 30 分钟; 且旧 load_blocks 的 2000 字符
    硬截断把段落切半。现在所有切分点都在结构边界上, 块内内容完整。
    """
    out = []
    for heading, content in _split_at_level(text, 2):
        if len(content) <= max_chars:
            out.append((heading, content))
            continue
        subs = _split_at_level(content, 3)
        if len(subs) > 1 and max(len(c) for _, c in subs) < len(content):
            for h3, c3 in subs:
                label = (f"{heading} / {h3}" if (heading and h3)
                         else (heading or h3))
                if len(c3) <= max_chars:
                    out.append((label, c3))
                else:
                    for p in _split_paragraphs(c3, max_chars):
                        if len(p) <= max_chars:
                            out.append((label, p))
                        else:
                            for ln in _split_lines(p, max_chars):
                                out.append((label, ln))
        else:
            for p in _split_paragraphs(content, max_chars):
                if len(p) <= max_chars:
                    out.append((heading, p))
                else:
                    for ln in _split_lines(p, max_chars):
                        out.append((heading, ln))
    return out


def load_blocks(limit: int = 0) -> list:
    """全量文档 → 块列表 [{id, text, path, heading, doc}]。"""
    blocks = []
    files = []
    seen_ids = set()
    for d in DOC_DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, _, fnames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/") + "/"
            if any(rel_dir.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
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
        doc_title = _doc_title(text, rel)
        sections = split_markdown(text)
        if not sections or all(not c for _, c in sections):
            sections = [("", text)]
        for heading, content in sections:
            # 2026-08-12: 取消 2000 字符硬截断 — 截断导致块内容破碎
            # （段落切半/尾段丢失）, 召回评分与真实内容脱节。块内全文
            # 保留; 向量嵌入由编码器自身截断（bge-m3 max_length=8192）。
            body = content or ""
            if not body.strip():
                continue
            # id 用完整标题（不再 [:40] 截断）+ 碰撞消歧: 完整标题下
            # 重复标题仍可能（同文多节同名）, 追加 #2/#3 序号。
            base_id = f"{rel}#{heading}" if heading else f"{rel}#file"
            bid = base_id
            n = 2
            while bid in seen_ids:
                bid = f"{base_id}#{n}"
                n += 1
            seen_ids.add(bid)
            blocks.append({
                "id": bid, "text": body, "path": [rel, heading or ""],
                "heading": heading, "doc": rel, "temperature": "active",
                "doc_title": doc_title,
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
    # 2026-08-12 修复: 无论是否新块, 先把缓存命中块的向量回填到
    # b["vector"] — 否则只要有一个新块, 其余 ~1.1 万缓存块全部不走
    # 缓存, 首 query 被 _embed 逐个补算拖慢 300s+。
    for b in blocks:
        if b.get("vector") is None and b["id"] in cache:
            b["vector"] = cache[b["id"]]
    # 回填后再算缺失集（文件不存在/损坏时 cache 为空 → 全量计算）
    uncached = [b for b in blocks if b.get("vector") is None]
    if not uncached:
        return
    try:
        from core.agent.compiler.semantic_encoder import get_encoder
        enc = get_encoder()
        t0 = time.time()
        total = len(uncached)
        done = 0
        # 分块编码 + 增量落盘（2026-08-12）: 30 分钟超时进程被杀后
        # 全部白算; 每 1000 块保存一次, 中断只丢最后一段。
        for start in range(0, total, 1000):
            sub = uncached[start:start + 1000]
            # 2026-08-14: 嵌入窗口 = 文件标题 + 节标题 + 内容
            texts = [((f"{b.get('doc_title') or ''} | "
                       f"{b.get('heading') or ''}\n{b['text']}")
                      [:EMBED_WINDOW]) for b in sub]
            vectors = enc.encode(texts, batch_size=32, normalize=True)
            for b, vec in zip(sub, vectors):
                v = vec.tolist() if hasattr(vec, "tolist") else list(vec)
                b["vector"] = v
                cache[b["id"]] = v
            done += len(sub)
            with open(VEC_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            print(f"  [vector] {done}/{total} 块 ({time.time()-t0:.0f}s)",
                  flush=True)
        print(f"  [vector] 完成 {total} 块, {time.time()-t0:.1f}s, "
              f"缓存 {VEC_CACHE}")
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
    """粗筛: 词法交集 ∪ 向量相似度 → top-C 候选块（供真打分）。

    2026-08-10: 纯词法对跨语言 query 是盲区（英文 query 与中文块词面
    零交集, 正确块进不了候选 → en 变体召回 0%）。加入向量粗筛后,
    跨语言 query 的正确中文块能进候选（实测 0 → 12 命中）。
    """
    lex_scored = []
    try:
        import jieba
        qterms = set(jieba.cut(query))
    except Exception:
        qterms = set(query)
    for b in blocks:
        terms = b.get("terms") or []
        overlap = sum(1 for t in qterms if t in terms)
        if overlap > 0:
            lex_scored.append((overlap, b))
    lex_scored.sort(key=lambda x: x[0], reverse=True)
    lex_top = [b for _, b in lex_scored[:top_c]]

    # 向量粗筛: query 与候选块向量相似度 top-C（跨语言保底）
    vec_top = []
    try:
        import numpy as np
        from core.agent.compiler.semantic_encoder import get_encoder
        enc = get_encoder()
        qv = enc.encode([query], normalize=True)[0]
        qn = np.linalg.norm(qv)
        scored = []
        for b in blocks:
            v = b.get("vector")
            if v is None:
                continue
            v = np.asarray(v)
            sim = float(np.dot(qv, v) / (qn * np.linalg.norm(v) + 1e-9))
            if sim > 0.2:
                scored.append((sim, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        vec_top = [b for _, b in scored[:top_c]]
    except Exception:
        pass

    # 合并去重（词法优先）
    seen = set()
    merged = []
    for b in lex_top + vec_top:
        if b["id"] in seen:
            continue
        seen.add(b["id"])
        merged.append(b)
    return merged[:top_c]


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
