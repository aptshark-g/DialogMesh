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

# 2026-08-14 语料卫生修复: walk "docs" 已递归覆盖 docs/only — 双目录
# 导致 docs/only 每块双份装载（#2 消歧后缀占位 top-k）。保留
# EXCLUDE_PREFIXES（docs/test 评测污染 / docs/notTish 另一项目参考）。
DOC_DIRS = ["docs"]
# 生产知识源排除项（2026-08-13）: docs/test 是评测产物（查询集/评测报告
# 字面包含 query 文本, 污染召回排序）; docs/notTish 是外部项目参考。
EXCLUDE_PREFIXES = ("docs/test/", "docs/notTish/")
SECTION_MAX_CHARS = 3000
EMBED_WINDOW = SECTION_MAX_CHARS
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache_v3.json")
# 2026-08-14（doc 域 miss 修复, 父级上下文）: 嵌入窗口加文件标题
# （doc_title | 节标题\n内容）— 小块语义带上文件级上下文, 救"跨块
# 概念"查询（agentic/存储分层 等 9 条 miss 的根因: 文件级语义没参与
# 嵌入）。缓存版本升 v4（嵌入内容变更, 旧 v3 缓存必须失效全量重算）。
VEC_CACHE = os.path.join(ROOT, "scripts", ".recall_vec_cache_v4.json")
FILE_SUMMARY_CACHE = os.path.join(
    ROOT, "data", "recall_index", "doc_file_summaries.json")

# 文件摘要策略（2026-08-14, 两级检索/父块上下文）:
#   mechanical — 首个 H1 + 引言段截断（零成本, 默认; 我们的文档开头
#                自带状态/引言块, 机械摘要质量够用）
#   llm        — 网关生成（质量最高, 慢; DM_FILE_SUMMARY=llm 启用,
#                生成一次落盘复用）
#   small      — 本地小模型（中间路线; DM_FILE_SUMMARY=small, 待接
#                ollama/本地端点）
FILE_SUMMARY_STRATEGIES = ("mechanical", "llm", "small")
FILE_SUMMARY_MAX_CHARS = 300


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


def _mechanical_summary(text: str, title: str) -> str:
    """机械摘要: 标题 + 引言块（首个非标题段）截断。零成本。"""
    intro = ""
    for para in text.split("\n\n"):
        stripped = para.strip()
        if not stripped or stripped.startswith("#"):
            continue
        intro = " ".join(stripped.split())[:FILE_SUMMARY_MAX_CHARS]
        break
    if title and intro:
        return f"{title}: {intro}"
    return title or intro


def _iter_doc_files(limit: int = 0):
    """遍历知识源 md 文件（与 load_doc_blocks 同目录规则）。"""
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
        yield rel, text


def load_file_summaries(limit: int = 0, strategy: str = "mechanical",
                        refresh: bool = False) -> dict:
    """文件级摘要 {doc: summary}（两级检索的"社区摘要", 2026-08-14）。

    mechanical 零成本实时算; llm/small 走缓存（生成一次落盘复用）。
    缓存路径 data/recall_index/doc_file_summaries.json。
    """
    strategy = strategy if strategy in FILE_SUMMARY_STRATEGIES else "mechanical"
    cache_path = FILE_SUMMARY_CACHE
    cached = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            cached = {}
    if strategy == "mechanical" and not refresh:
        out = {}
        for rel, text in _iter_doc_files(limit):
            out[rel] = _mechanical_summary(text, _doc_title(text, rel))
        return out
    if cached.get("_strategy") == strategy and not refresh:
        return {k: v for k, v in cached.items() if k != "_strategy"}
    out = {}
    for rel, text in _iter_doc_files(limit):
        if strategy == "llm":
            out[rel] = _llm_summary(text, _doc_title(text, rel))
        else:
            out[rel] = _small_model_summary(text, _doc_title(text, rel))
    cached = dict(out)
    cached["_strategy"] = strategy
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f, ensure_ascii=False, indent=1)
    except Exception as e:
        logger = __import__("logging").getLogger("dm.doc_corpus")
        logger.debug("file summary cache save failed: %s", e)
    return out


def _llm_summary(text: str, title: str) -> str:
    """LLM 摘要（网关; 失败降级机械, 不阻塞两级检索）。"""
    prompt = (
        "用一句话概括下面文档的主题与内容范围（<=80 字, 用于检索定位）:\n"
        f"文档: {title}\n{text[:3000]}"
    )
    try:
        import urllib.request
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": 120, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read())
        text_out = (d["choices"][0]["message"].get("content") or "").strip()
        if text_out:
            return f"{title}: {text_out[:FILE_SUMMARY_MAX_CHARS]}"
    except Exception:
        pass
    return _mechanical_summary(text, title)


def _small_model_summary(text: str, title: str) -> str:
    """小模型摘要（LM Studio 本地端点, 2026-08-14 实测）。

    实测（qwen/qwen3.5-9b, 关思考）: 2s/文档, 概括质量显著优于
    mechanical（含"四壳/闭环"等检索锚点词）。失败降级机械。
    端点: 127.0.0.1:1234（LM Studio OpenAI 兼容）; 环境变量
    DM_LMSTUDIO_URL / DM_LMSTUDIO_MODEL 可覆盖。
    """
    endpoint = os.environ.get("DM_LMSTUDIO_URL", "http://127.0.0.1:1234")
    model = os.environ.get("DM_LMSTUDIO_MODEL", "qwen/qwen3.5-9b")
    prompt = (
        "用一句话概括下面文档的主题与内容范围（<=80 字, 用于检索定位, "
        "包含关键术语）:\n"
        f"文档: {title}\n{text[:3000]}"
    )
    try:
        import urllib.request
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200, "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{endpoint}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        out = (d["choices"][0]["message"].get("content") or "").strip()
        if out:
            return f"{title}: {out[:FILE_SUMMARY_MAX_CHARS]}"
    except Exception:
        pass
    return _mechanical_summary(text, title)


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
        doc_title = _doc_title(text, rel)
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
                "doc_title": doc_title,
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
            # 2026-08-14: 嵌入窗口 = 文件标题 + 节标题 + 内容（父级
            # 上下文; 救小块缺文件级语义的 miss）
            texts = [((f"{b.get('doc_title') or ''} | "
                       f"{b.get('heading') or ''}\n{b['text']}")
                      [:EMBED_WINDOW]) for b in sub]
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
