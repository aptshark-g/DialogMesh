# -*- coding: utf-8 -*-
"""文档语料（core 侧, 2026-08-13）— "信息内容才是召回核心"落地。

生产 recall 全局池此前只含对话树（Hot/Warm/Cold 三级, 记忆域）;
docs/ + docs/only/ 的 11761 块文档语料是独立知识源, 只在评测脚本里
存在。本模块把语料加载/切分/向量缓存移进 core, 供 RecallService
全局池合并（DM_DOC_CORPUS=1 开启）。

切分与 scripts/doc_recall_bench.py 同源（结构递归: ## → ### → 段落 →
行, 不硬截断）; 向量缓存共用 .recall_vec_cache_v3.json。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DOC_DIRS = ["docs", os.path.join("docs", "only")]
# 生产知识源排除项（2026-08-13）: docs/test 是评测产物（查询集/评测报告
# 字面包含 query 文本, 污染召回排序）; docs/notTish 是外部项目参考。
EXCLUDE_PREFIXES = ("docs/test/", "docs/notTish/")
SECTION_MAX_CHARS = 3000
EMBED_WINDOW = SECTION_MAX_CHARS
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache_v3.json")


def _heading_level(line: str) -> int:
    m = re.match(r"^(#{1,6})\s+", line)
    return len(m.group(1)) if m else 0


def _split_at_level(text: str, level: int) -> list:
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
    """结构递归切分（## → ### → 段落 → 行, 全部在结构边界上）。"""
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
                for part in _chunk_parts(c3, max_chars):
                    out.append((label, part))
        else:
            for part in _chunk_parts(content, max_chars):
                out.append((heading, part))
    return out


def _chunk_parts(text: str, max_chars: int) -> list:
    parts = []
    for p in _split_paragraphs(text, max_chars):
        if len(p) <= max_chars:
            parts.append(p)
        else:
            parts.extend(_split_lines(p, max_chars))
    return parts


def load_doc_blocks(limit: int = 0) -> list:
    """全量文档 → 块列表 [{id, text, path, heading, doc, temperature}]。"""
    blocks = []
    seen_ids = set()
    files = []
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
        sections = split_markdown(text)
        if not sections or all(not c for _, c in sections):
            sections = [("", text)]
        for heading, content in sections:
            body = content or ""
            if not body.strip():
                continue
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
            })
    return blocks


def prepare_doc_vectors(blocks: list, skip: bool = False) -> None:
    """批量向量 + 磁盘缓存（与 doc_recall_bench 同口径: 标题+窗口全文）。"""
    if skip:
        return
    cache = {}
    if os.path.exists(VEC_CACHE):
        try:
            with open(VEC_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    for b in blocks:
        if b.get("vector") is None and b["id"] in cache:
            b["vector"] = cache[b["id"]]
    uncached = [b for b in blocks if b.get("vector") is None]
    if not uncached:
        return
    try:
        from core.agent.compiler.semantic_encoder import get_encoder
        enc = get_encoder()
        t0 = time.time()
        total = len(uncached)
        for start in range(0, total, 1000):
            sub = uncached[start:start + 1000]
            texts = [((b.get("heading") or "") + "\n" + b["text"])
                     [:EMBED_WINDOW] for b in sub]
            vectors = enc.encode(texts, batch_size=32, normalize=True)
            for b, vec in zip(sub, vectors):
                v = vec.tolist() if hasattr(vec, "tolist") else list(vec)
                b["vector"] = v
                cache[b["id"]] = v
            with open(VEC_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            print(f"  [doc_corpus vector] {start + len(sub)}/{total} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"  [doc_corpus vector] 编码失败: {e}")
