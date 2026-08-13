# -*- coding: utf-8 -*-
"""RecallService — 统一召回能力接口（GAP-R1/R2/R5/R6 首批施工, 哲学化升级）。

用户拍板模型（2026-08-08）:
  混合锚点 = 向量(BGE) + BM25 + HyDE(question 扩展) + 溯源置信度加权
  扩散     = 锚点块沿对话树 parent/child k-hop（hierarchical 权重）
  LLM 挑选 = 候选集 → 可选 LLM 排序（MVP: 融合打分排序, LLM 挑选留接口）

哲学化（A12 约束空间 + 状态转化, 2026-08-08 用户拍板）:
  切分 = 语法补全（代词闭环）→ SPO 提炼（subject/predicate/obj）
       → 块 = 约束投影 {SPO 三元组 + 约束上下文 + 状态转化}
  召回 = 约束空间投影对齐（SPO 结构映射, Gentner structure-mapping 对齐）+
         词法/语义/问题扩展多路
  对象间关系 = 转化投影（关联链边/父子边 → k-hop 导航）

溯源置信度（source_confidence, 可学习 A18 ε 自适应）:
  向量 0.9 / BM25 0.7 / HyDE 0.8 / SPO 0.85 / 扩散 0.75
融合: fused = score × source_confidence × 温度权重
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("dm.recall")

SOURCE_CONFIDENCE: Dict[str, float] = {
    "vector": 0.9,
    "bm25": 0.7,
    "hyde": 0.8,
    "spo": 0.85,
    "assoc": 0.75,
    "diffusion": 0.75,
}
TEMP_WEIGHT: Dict[str, float] = {
    "active": 1.0,
    "paused": 0.7,
    "cold": 0.4,
    "frozen": 0.1,
}
EPSILON = 0.02  # A18 ε 步长（反馈自适应）
PRONOUNS = {"它", "他", "她", "这", "那", "其"}


def _is_chinese_query(query: str) -> bool:
    """Query 是否含中文（与 SemanticEncoder._is_chinese 同语义）。"""
    return any('\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff'
               for ch in query)

# 规则增强（SPO-A）: 同义归一表 — 缓解"字面精确匹配"瓶颈
SYNONYM_MAP = {
    "怎么做": "如何实现", "如何做": "如何实现", "怎样做": "如何实现",
    "怎么实现": "如何实现", "怎么做": "如何实现", "怎么": "如何",
    "是什么": "是什么", "什么是": "是什么",
    "区别": "区别", "不同": "区别", "差异": "区别",
    "对比": "对比", "比较": "对比", "选型": "对比",
    "连不上": "连接失败", "连接不上": "连接失败", "无法连接": "连接失败",
    "方案": "设计", "规划": "设计", "计划": "设计",
    "微服务": "微服务架构", "架构": "架构", "系统": "架构",
    "怎么做": "如何实现", "如何": "如何", "办法": "如何",
    "JWT": "JWT", "jwt": "JWT", "认证": "认证", "登录": "登录",
    "用户": "用户", "密码": "密码", "注册": "注册",
}


@dataclass
class RecallHit:
    """一条召回结果（锚点或扩散命中）。"""
    id: str
    text: str
    source: str                 # vector | bm25 | hyde | diffusion
    score: float = 0.5          # 原始相关度 0-1
    confidence: float = 0.5     # 溯源置信度
    temperature: str = "active"
    hops: int = 0
    path: List[str] = field(default_factory=list)
    spo: Optional[dict] = None        # 约束投影（SPO 三元组）
    created_at: float = field(default_factory=time.time)

    def fused(self) -> float:
        """融合分: 相关度 × 溯源置信度 × 温度权重。"""
        return (
            self.score
            * self.confidence
            * TEMP_WEIGHT.get(self.temperature, 0.5)
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text[:200],
            "source": self.source,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "temperature": self.temperature,
            "hops": self.hops,
            "path": self.path,
            "spo": self.spo,
            "fused": round(self.fused(), 4),
        }


@dataclass
class RecallResult:
    query: str
    hits: List[RecallHit] = field(default_factory=list)
    expanded_queries: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "expanded_queries": self.expanded_queries,
            "hits": [h.to_dict() for h in self.hits],
            "latency_ms": round(self.latency_ms, 1),
        }


def format_anchors(result: "RecallResult", max_chars: int = 1200,
                   max_hits: int = 5) -> str:
    """召回结果 → 执行层锚点文本（system 注入, 供精确查阅定位）。

    设计: RECALL_EXECUTION_BRIDGE_DESIGN_20260809 §三 层1→层2:
    粗召回只给"候选锚点"（来源/置信度/片段摘要）, 真实内容由执行层
    用 dir_list/grep/file_read 顺文件树精确查阅, 不把大段原文塞上下文。
    """
    if not result or not result.hits:
        return ""
    parts = ["## 候选锚点（粗召回, 供精确查阅定位; 真实内容请用工具按路径读取）"]
    used = len(parts[0])
    for h in result.hits[:max_hits]:
        text = (h.text or "").strip().replace("\n", " ")[:160]
        loc = ""
        if h.path:
            loc = " <" + ",".join(str(p) for p in h.path[:3]) + ">"
        line = f"- [{h.source} {h.fused():.2f}]{loc} {text}"
        used += len(line) + 1
        if used > max_chars:
            break
        parts.append(line)
    return "\n".join(parts)


class RecallService:
    """统一召回能力底座。"""

    def __init__(
        self,
        engine=None,
        chunk_store=None,
        discourse=None,
        llm=None,
    ):
        self._engine = engine
        self._chunk = chunk_store or getattr(engine, "_chunk_store", None)
        self._discourse = discourse or getattr(engine, "_discourse_tree", None)
        self._llm = llm or getattr(engine, "_llm_provider", None)
        self._blocks_cache: Dict[str, dict] = {}   # bid → block info
        self._block_list: List[dict] = []
        self._embeddings: Dict[str, List[float]] = {}
        self._decomposer = None
        self._feedback_log: List[dict] = []
        self._decompose_misses: List[dict] = []   # 子问题分解失败记录（元认知复盘）
        self._learned_conf: Dict[str, float] = {}
        self._last_result: Optional[RecallResult] = None
        self._spo_cache: Dict[str, List[dict]] = {}
        self._index_cache: Dict[str, dict] = {}   # bid -> {spo, vector}
        self._index_cache_dir = None
        self._index_cache_file = "default"
        # 池归属（2026-08-11 修复竞态）: hot（default/sid）与 global 共用
        # _index_cache dict, 但 flush 时需按池分文件写, 否则 global 覆盖
        # default 的写入, default.json 永远等不到落盘（只落 100/360 块）。
        self._file_bids: Dict[str, set] = {}   # sid -> bid 集合（该文件应含的块）
        self._dirty_files: set = set()         # 待落盘的文件 sid
        # Async index-cache persistence (2026-08-10): writing the full
        # index JSON on every recall blocked the hot path (6.7s/5 queries
        # in benchmarks). Writes now happen in a background thread, at
        # most once per _index_cache_flush_interval, only when dirty.
        self._index_cache_dirty = False
        self._index_cache_flush_interval = 5.0   # seconds (A18-tunable)
        self._index_cache_last_flush = 0.0
        self._index_cache_flush_lock = threading.Lock()
        self._index_cache_closed = False
        self._global_block_list: List[dict] = []
        # 批量余弦矩阵缓存（2026-08-12）: list→array 拷贝每 query 重复
        # （8594 块 × 1024 维 ≈ 70MB）; 块集/嵌入数不变则复用矩阵。
        self._vec_matrix = None
        self._vec_matrix_key = None
        self._vec_bids: List[str] = []
        # 稀疏 BM25 词项索引（2026-08-12）: 每块 tokenize 一次按块集缓存,
        # 消灭"每 query 每块重分词"的 8.6-10s/query 开销。
        self._bm25_indexes: Dict[tuple, dict] = {}
        self._bm25_build_lock = threading.Lock()
        # 默认 vector_primary（2026-08-12 采纳）: 诊断证据 — 100 条全部
        # top1 来自 vector, vector 内 #1 的 46 条被 RRF 长尾压掉 ~12 条;
        # vector 主导排序 + 其他源扩展后 fused top1 与 vector#1 完全对齐
        # （46/46）, doc top1 21.3%→31.1%, dialogue 56.4%→69.2%。
        # 备选: linear | rrf | norm（保留消融/回退）。
        self.fuse_mode = "vector_primary"
        # 时序约束（2026-08-09, 评测驱动发现）: 文档/块版本新旧降权。
        # 0 = 关闭（默认, 不改变既有行为）; >0 = 半衰期天数,
        # 排序分 = fused() × 2^(-age_days / half_life), 下限 0.3。
        self.time_half_life_days = 0.0
        # 并行子问题分解开关（2026-08-11, SUBGRAPH_EXPANSION_UPGRADE 设计 2）:
        # True = LLM 把 query 拆 3-5 子问题并行召回（I/O 密集, threading 足够）;
        # False = 回退旧行为（单 query 或串行 2-3 扩展）。
        self.parallel_decompose = False
        self.decompose_subqueries = 3        # 子问题数（含原 query）
        self.decompose_max_workers = 4       # 并行度（I/O 密集, 线程池）
        # DAG 分层局部扩展开关（设计 1）: True = expand_subgraph 走分层扩展 +
        # 同步剪枝 + 跨锚点桥接; False = 旧 BFS。
        self.dag_layer_expand = False
        self.dag_max_hops = 2
        self.dag_prune_threshold = 0.3       # 边 confidence × relevance 剪枝阈值
        self.dag_budget_per_layer = 12       # 每层节点预算
        self.dag_bridge_check = True         # 跨锚点桥接检查
        # SPO 对齐候选集上限（2026-08-12）: 0 = 全池对齐（旧行为, doc 域
        # 11493 块 ~330ms/池, 双池 ~660ms/query）; >0 = 只对 vector∪bm25
        # 前 N 候选做约束投影对齐（设计 12.2 两级粒度: 粗扫描定位 → 精对齐）。
        # 对齐是排序精修, 不需要全池 — 候选集外块本来就进不了融合前列。
        # 环境变量可覆盖（DM_SPO_CAP=0 关闭候选集, 全池对齐）— 2026-08-12
        # 实测 cap=300 提速但丢 SPO 独有 top1, 保留开关做消融对比。
        try:
            self.spo_candidate_cap = int(os.environ.get("DM_SPO_CAP", "300"))
        except ValueError:
            self.spo_candidate_cap = 300
        # RRF 置信度加权（2026-08-12, 消融开关）: 0 = 纯 RRF（各源等权）;
        # 1 = 贡献 × 溯源置信度（vector 0.9 / bm25 0.7 / spo 0.85 / hyde
        # 0.8 / diffusion 0.75, A18 可学习）。诊断证据: 100 条中全部
        # 34 个融合 top1 来自 vector, 而 vector 路线内 #1 有 45 条 —
        # 11 条被其他源长尾拉下; 设计里溯源置信度本就该参与融合。
        self.rrf_conf_weight = os.environ.get("DM_RRF_CONF", "0") == "1"
        # 跨池去重（2026-08-12）: 全局池包含会话块 → 同一块在 hot 与
        # cold 各出现一次, RRF 被双倍计分（churn 块叠加 6 源）。默认
        # 去重（hot 优先, 更鲜）; DM_DEDUP_POOLS=0 关闭做消融。
        self.dedup_pools = os.environ.get("DM_DEDUP_POOLS", "1") != "0"
        # 文档语料入全局池（2026-08-13, "信息内容才是召回核心"）:
        # 对话树三级（Hot/Warm/Cold）只覆盖记忆域; docs 语料是独立知识源。
        # DM_DOC_CORPUS=1 时全局池合并 11761 块文档（向量走 v3 缓存）。
        self.enable_doc_corpus = os.environ.get(
            "DM_DOC_CORPUS", "0") == "1"
        self._doc_corpus_blocks: Optional[List[dict]] = None
        # 融合模式环境覆盖（2026-08-12）: linear | rrf | vector_primary
        # （证据驱动: top1 全部来自 vector, vector 内 #1 被 RRF 压掉
        # ~10 条 → vector 主导排序 + 其他源扩展）
        _fusion = os.environ.get("DM_FUSION", "")
        if _fusion in ("linear", "rrf", "vector_primary"):
            self.fuse_mode = _fusion

    def _norm(self, w: str) -> str:
        """同义归一（规则增强 SPO-A）: 谓词/主宾比较前归一。"""
        if not w:
            return w
        key = w.strip()
        return SYNONYM_MAP.get(key, key)

    # ── 约束投影: 语法补全（代词闭环）→ SPO 提炼 ───────────────

    def _get_decomposer(self):
        if self._decomposer is None:
            try:
                from core.agent.discourse_block_tree.syntactic_decomposer import (
                    SYNTACTIC_DECOMPOSER,
                )
                self._decomposer = SYNTACTIC_DECOMPOSER
            except Exception:
                self._decomposer = False
        return self._decomposer or None

    def _extract_spo(self, text: str) -> List[dict]:
        """切分标准（哲学化）: 代词闭环补全 → 分句 → SPO 提炼。"""
        if text in self._spo_cache:
            return self._spo_cache[text]
        dec = self._get_decomposer()
        if dec is None:
            return []
        try:
            edus = dec.decompose(text)
        except Exception:
            return []
        # 代词闭环: 用块内最近的主语补全代词宾语/主语（轻量先行词解析）
        last_subject = ""
        out = []
        for edu in edus:
            subj = (getattr(edu, "subject", "") or "").strip()
            pred = (getattr(edu, "predicate", "") or "").strip()
            obj = (getattr(edu, "obj", "") or "").strip()
            if subj in PRONOUNS and last_subject:
                subj = last_subject
            if obj in PRONOUNS and last_subject:
                obj = last_subject
            if subj:
                last_subject = subj
            if pred:
                out.append({
                    "subject": subj,
                    "predicate": pred,
                    "obj": obj,
                    "negation": getattr(edu, "negation", False),
                    "question": getattr(edu, "question", False),
                })
        self._spo_cache[text] = out
        return out

    # ── 索引（懒加载: 首次 recall 前从 discourse 取块） ────────────

    def _ensure_blocks(self, sid: Optional[str] = None) -> List[dict]:
        key = sid or "default"
        if getattr(self, "_current_sid", None) == key and self._block_list:
            return self._block_list
        tm = self._discourse
        if tm is None or not getattr(tm, "blocks", None):
            return []
        self._load_index_cache(key)
        # 会话隔离: 块带 _session_id 标签时按 sid 过滤（热路径 = 当前会话）;
        # 无标签旧树/测试块 → 全量视为该会话（与 dispatch._blocks_for 同语义）
        has_tags = any(getattr(b, "_session_id", "") for b in tm.blocks.values())
        blocks = []
        for bid, b in tm.blocks.items():
            b_sid = getattr(b, "_session_id", "")
            if has_tags and key != "default" and b_sid != key:
                continue
            text = (
                getattr(b, "_raw_text", "") or " ".join(
                    getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
                )
            ).strip()
            if not text:
                continue
            cached = self._index_cache.get(bid) or {}
            # 缓存指纹校验: 文本变了 → 弃用旧 spo/vector（2026-08-11）
            pre_vec = getattr(b, "vector", None)
            if isinstance(pre_vec, (list, tuple)) and len(pre_vec) > 0:
                # 预编码透传（2026-08-12, 与 global 同）: 修复 hot 路径
                # 无视预编码向量 → 8526 块重编码 340s
                vector = list(pre_vec)
                if cached.get("hash") == self._text_hash(text):
                    spo = cached.get("spo") or self._extract_spo(text)
                else:
                    spo = self._extract_spo(text)
            else:
                if cached.get("hash") == self._text_hash(text):
                    spo = cached.get("spo") or self._extract_spo(text)
                    vector = cached.get("vector")
                else:
                    spo = self._extract_spo(text)
                    vector = None
            summary_raw = getattr(b, "summary", "")
            if isinstance(summary_raw, str):
                summary = summary_raw.strip()
            elif summary_raw is not None and hasattr(summary_raw, "get_best"):
                summary = (summary_raw.get_best() or "").strip()
            else:
                summary = ""
            blocks.append({
                "id": bid,
                "text": text,
                "heading": getattr(b, "heading", "") or "",
                "summary": summary,
                "parent": getattr(b, "parent_id", None),
                "children": list(getattr(b, "child_ids", [])),
                "temperature": getattr(b, "status", "active"),
                "spo": spo,
                "vector": vector,
            })
            # 缓存写回: hash + spo + vector（2026-08-12 修复, 与 global 同）
            entry = self._index_cache.setdefault(bid, {})
            entry["hash"] = self._text_hash(text)
            entry["spo"] = spo
            if vector is not None:
                entry["vector"] = vector
        self._block_list = blocks
        self._blocks_cache = {b["id"]: b for b in blocks}
        self._current_sid = key
        self._index_cache_file = key
        self._file_bids.setdefault(key, set()).update(b["id"] for b in blocks)
        self._save_index_cache(key)
        # R2 解孤儿: 块原子喂进 ChunkStore（hash 去重, 供向量后端/关键词兜底）
        if self._chunk is not None:
            try:
                for b in blocks:
                    self._chunk.add_text(b["text"], b["id"],
                                         tags=["discourse_block"])
            except Exception as e:
                logger.debug("chunk index failed: %s", e)
        return blocks

    def _ensure_global_blocks(self) -> List[dict]:
        """冷路径: 全局块池（全量, 不按 sid 过滤）; 独立缓存 global.json。"""
        if self._global_block_list:
            return self._global_block_list
        _t0 = time.time()
        _stat = {"total": 0, "cache_hit": 0, "spo_recalc": 0, "pre_vec": 0}
        tm = self._discourse
        blocks = []
        # 2026-08-13 修复: 索引缓存无条件加载 — 此前在 tm 分支内,
        # 裸服务（无 discourse, 文档语料池）跳过加载 → doc corpus 合并
        # cache_hit=0, 每次全量 SPO 提取 146s。
        self._load_index_cache("global")
        if tm is not None and getattr(tm, "blocks", None):
            for bid, b in tm.blocks.items():
                _stat["total"] += 1
                text = (
                    getattr(b, "_raw_text", "") or " ".join(
                        getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
                    )
                ).strip()
                if not text:
                    continue
                cached = self._index_cache.get(bid) or {}
                # 预编码向量透传（2026-08-11）: FakeBlock.vector（prepare_vectors
                # 批量编码）优先; 回退索引缓存; 都无 → 懒计算。
                pre_vec = getattr(b, "vector", None)
                if isinstance(pre_vec, (list, tuple)) and len(pre_vec) > 0:
                    vector = list(pre_vec)
                    _stat["pre_vec"] += 1
                    # 预编码为准; SPO 仍走缓存（hash 匹配才复用, 否则重算并写回）
                    if cached.get("hash") == self._text_hash(text):
                        spo = cached.get("spo") or self._extract_spo(text)
                        _stat["cache_hit"] += 1
                    else:
                        spo = self._extract_spo(text)
                        _stat["spo_recalc"] += 1
                else:
                # 缓存指纹校验（2026-08-11）: 文本变了 → 弃用旧 spo/vector
                    if cached.get("hash") == self._text_hash(text):
                        spo = cached.get("spo") or self._extract_spo(text)
                        vector = cached.get("vector")
                        _stat["cache_hit"] += 1
                    else:
                        spo = self._extract_spo(text)
                        vector = None
                        _stat["spo_recalc"] += 1
                blocks.append({
                    "id": bid,
                    "text": text,
                    "heading": getattr(b, "heading", "") or "",
                    "parent": getattr(b, "parent_id", None),
                    "children": list(getattr(b, "child_ids", [])),
                    "temperature": getattr(b, "status", "active"),
                    "spo": spo,
                    "vector": vector,
                    "session": getattr(b, "_session_id", ""),
                })
                # 缓存写回: hash + spo 一起落（2026-08-12 修复: 此前只写 hash,
                # spo/vector 永不持久化 → 每次全量重算 140s）
                entry = self._index_cache.setdefault(bid, {})
                entry["hash"] = self._text_hash(text)
                entry["spo"] = spo
                if vector is not None:
                    entry["vector"] = vector
        # P0 写即索引（RECALL_SUBGRAPH_BRIDGE §六）: 合并产出内容块
        # （write_file 索引进 chunk_store 的 produced 原子）——刚写的
        # 文件内容进 recall 冷路径, "产出内容可召回"闭环。
        if self._chunk is not None:
            try:
                for atom in self._chunk.atoms_by_tag("produced"):
                    text = (atom.text or "").strip()
                    if not text:
                        continue
                    bid = atom.block_id
                    if any(b["id"] == bid for b in blocks):
                        continue
                    cached = self._index_cache.get(bid) or {}
                    vec = cached.get("vector") if cached.get("hash") == self._text_hash(text) else None
                    if vec is None:
                        # G0 记忆闭环: 产出块向量现算一次并落盘
                        # （_save_index_cache("global") → 重启后恢复）
                        vec = self._embed(text)
                        if vec is not None:
                            entry = self._index_cache.setdefault(bid, {})
                            entry["vector"] = vec
                            entry["hash"] = self._text_hash(text)
                    blocks.append({
                        "id": bid,
                        "text": text,
                        "parent": None,
                        "children": [],
                        "temperature": "active",
                        "spo": self._extract_spo(text),
                        "vector": vec,
                        "path": [str(bid).replace("file:", "", 1)],
                    })
            except Exception as e:
                logger.debug("produced-block merge failed: %s", e)
        # 文档语料合并（2026-08-13, DM_DOC_CORPUS=1）: "信息内容才是
        # 召回核心" — 对话树三级只覆盖记忆域, docs 语料是独立知识源。
        # 懒加载一次, 向量走 v3 缓存; SPO 一次性提取（与 discourse 同口径）。
        if getattr(self, "enable_doc_corpus", False):
            try:
                from core.agent.recall.doc_corpus import (
                    load_doc_blocks, prepare_doc_vectors)
                if self._doc_corpus_blocks is None:
                    _m_t0 = time.time()
                    doc_blocks = load_doc_blocks()
                    prepare_doc_vectors(doc_blocks)
                    _m_hit = 0
                    _m_ext = 0
                    for b in doc_blocks:
                        b["summary"] = ""
                        b["parent"] = None
                        b["children"] = []
                        # 2026-08-13 修复: 复用索引缓存（hash 指纹）—
                        # 此前无条件全量提取 10787 块 ≈ 147s/进程; 首跑
                        # 后 global.json 持久化 spo, 重启降到秒级。
                        _cached = self._index_cache.get(b["id"]) or {}
                        if _cached.get("hash") == self._text_hash(b["text"]):
                            b["spo"] = _cached.get("spo") or []
                            _m_hit += 1
                        else:
                            b["spo"] = self._extract_spo(b["text"])
                            _m_ext += 1
                        # 写回索引缓存（2026-08-13）: 文档块 hash+spo 必须
                        # 持久化, 否则每次进程重启全量重提取 195s。
                        _entry = self._index_cache.setdefault(b["id"], {})
                        _entry["hash"] = self._text_hash(b["text"])
                        if b["spo"]:
                            _entry["spo"] = b["spo"]
                    self._doc_corpus_blocks = doc_blocks
                    logger.info(
                        "doc corpus merge: %d blocks, cache_hit=%d "
                        "extract=%d, %.1fs",
                        len(doc_blocks), _m_hit, _m_ext,
                        time.time() - _m_t0)
                blocks += self._doc_corpus_blocks
                logger.info("global pool: +%d doc corpus blocks",
                            len(self._doc_corpus_blocks))
            except Exception as e:
                logger.debug("doc corpus merge failed: %s", e)
        self._global_block_list = blocks
        self._index_cache_file = "global"
        self._file_bids.setdefault("global", set()).update(b["id"] for b in blocks)
        self._save_index_cache("global")
        logger.info("ensure_global_blocks: %d 块 %.1fs 命中=%d 重算=%d 预编码=%d",
                    len(blocks), time.time() - _t0,
                    _stat["cache_hit"], _stat["spo_recalc"], _stat["pre_vec"])
        return blocks

    # ── 索引缓存（G0: 首次召回持久化 SPO+向量, 后续直读, 重启不丢） ──

    def _index_dir(self) -> str:
        import os
        if self._index_cache_dir is None:
            self._index_cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))),
                "data", "recall_index")
            os.makedirs(self._index_cache_dir, exist_ok=True)
        return self._index_cache_dir

    def _index_path(self, sid: str) -> str:
        import os, re
        safe = re.sub(r"[^0-9a-zA-Z_-]", "_", sid) or "default"
        return os.path.join(self._index_dir(), f"{safe}.json")

    @staticmethod
    def _text_hash(text: str) -> str:
        """内容指纹: 缓存条目与块文本绑定, 文本变化 → 缓存失效。

        2026-08-11 修复: goldset 重建后 bid 复用（r000...）但内容变了,
        旧缓存向量（旧模型维度）被直接采用 → vector 路余弦全 0, 首跑
        指标被污染。现在缓存条目带 hash, 命中时校验文本一致性。
        """
        import hashlib
        return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

    def _load_index_cache(self, sid: str) -> None:
        import os, json
        path = self._index_path(sid)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = data.get("blocks", {}) if isinstance(data, dict) else {}
            # 合并而非覆盖（2026-08-11）: hot 与 global 分文件存储, 但内存
            # 共用 _index_cache; 覆盖会丢掉另一文件已加载的条目。
            self._index_cache.update(loaded)
            self._file_bids.setdefault(sid, set()).update(loaded.keys())
        except Exception as e:
            logger.debug("index cache load failed: %s", e)
            self._file_bids.setdefault(sid, set())

    def _save_index_cache(self, sid: str) -> None:
        """Schedule an async flush of the index cache (throttled).

        2026-08-10: previously a synchronous full JSON dump on every
        recall — 6.7s/5 queries in benchmarks. Now dirty-flagged and
        written by a background thread at most once per interval.
        """
        if not self._index_cache:
            return
        self._index_cache_dirty = True
        # 按池分文件（2026-08-11）: hot/default 与 global 各自落盘,
        # 不再用单值 pending_sid（global 会覆盖 default 的写入）。
        self._dirty_files.add(sid)
        now = time.time()
        if now - self._index_cache_last_flush < self._index_cache_flush_interval:
            return  # throttled — flush will happen on a later call
        self._spawn_index_cache_flush()

    def _spawn_index_cache_flush(self) -> None:
        """Snapshot + write in a background daemon thread."""
        if not self._index_cache_dirty or self._index_cache_closed:
            return
        with self._index_cache_flush_lock:
            if not self._index_cache_dirty or self._index_cache_closed:
                return
            # 快照剥离 vector（2026-08-12）: 1024 维向量进 JSON 使每次
            # flush 序列化 ~400MB, eval 实测每 query 拖慢 ~10s。向量仅
            # 内存态（_index_cache/_embeddings）+ 专用 vec 缓存承载;
            # 落盘只写 hash+spo（指纹校验仍完整）。
            snapshot = {
                bid: {k: v for k, v in entry.items() if k != "vector"}
                for bid, entry in self._index_cache.items()
            }
            files = set(self._dirty_files)
            file_bids = {sid: set(bids) for sid, bids in self._file_bids.items()}
            self._index_cache_dirty = False
            self._dirty_files.clear()
            self._index_cache_last_flush = time.time()

        def _write():
            import json, os
            try:
                for sid in files:
                    bids = file_bids.get(sid)
                    if not bids:
                        continue
                    sub = {bid: snapshot[bid] for bid in bids
                           if bid in snapshot}
                    if not sub:
                        continue
                    path = self._index_path(sid)
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump({"blocks": sub}, f, ensure_ascii=False)
                    os.replace(tmp, path)
            except Exception as e:
                logger.debug("index cache async save failed: %s", e)
                # retry on next schedule
                with self._index_cache_flush_lock:
                    self._index_cache_dirty = True
                    self._dirty_files.update(files)

        threading.Thread(target=_write, daemon=True).start()

    def flush_index_cache(self) -> None:
        """Synchronous flush (on close/graceful shutdown)."""
        self._index_cache_closed = True
        if not self._index_cache:
            return
        import json, os
        try:
            # 同步兜底: 所有已知文件按各自 bid 子集落盘
            for sid, bids in self._file_bids.items():
                if not bids:
                    continue
                sub = {bid: self._index_cache[bid] for bid in bids
                       if bid in self._index_cache}
                if not sub:
                    continue
                path = self._index_path(sid)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"blocks": sub}, f, ensure_ascii=False)
                os.replace(tmp, path)
            self._dirty_files.clear()
        except Exception as e:
            logger.debug("index cache flush failed: %s", e)

    def _cosine(self, a, b) -> float:
        try:
            import numpy as np
            # 防御: 向量可能以 (1, dim) 嵌套形式存储, 统一压平
            a, b = np.asarray(a, dtype=float).reshape(-1), np.asarray(b, dtype=float).reshape(-1)
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))
        except Exception:
            return 0.0

    def _temporal_factor(self, hit) -> float:
        """时序约束因子: 排序分 = fused() × 2^(-age_days / half_life)。

        无时间戳 / 半衰期关闭 → 1.0（不改变既有行为）;
        旧文档衰减到下限 0.3（同相关度时新文档优先）。
        """
        hl = getattr(self, "time_half_life_days", 0.0) or 0.0
        if hl <= 0:
            return 1.0
        ts = getattr(hit, "created_at", None) or 0.0
        if ts <= 0:
            return 1.0
        age_days = (time.time() - ts) / 86400.0
        if age_days <= 0:
            return 1.0
        return max(0.3, 2.0 ** (-age_days / hl))

    def _embed(self, text: str) -> Optional[List[float]]:
        try:
            from core.infrastructure.model_service import encode_text
            vec = encode_text(text, use_cache=True)
            if vec is None:
                return None
            import numpy as np
            arr = np.asarray(vec)
            return arr.reshape(-1).tolist()  # 压平为 1D, 避免嵌套 (1, dim)
        except Exception:
            return None

    def _chat_once(self, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """经 self._llm 一次对话（兼容 chat/complete/generate 三接口）。"""
        llm = self._llm
        if llm is None:
            return None
        try:
            if hasattr(llm, "chat"):
                resp = llm.chat([{"role": "user", "content": prompt}])
            elif hasattr(llm, "complete"):
                resp = llm.complete(prompt)
            elif hasattr(llm, "generate"):
                from core.agent.llm_providers.base import GenerateRequest
                result = llm.generate(GenerateRequest(
                    prompt=prompt, max_tokens=max_tokens,
                    temperature=0.0,
                    metadata={"thinking": {"type": "disabled"}}))
                resp = result.text if result is not None else ""
            else:
                return None
            return resp if isinstance(resp, str) else getattr(
                resp, "content", "")
        except Exception:
            return None

    def _hyde_query_vector(self, query: str) -> Optional[List[float]]:
        """HyDE 真实现（2026-08-13, P1）: LLM 生成假设答案段落 → 嵌入
        作查询向量。域术语在假设段落里显式出现 → 把"措辞敏感"的答案块
        （实测 rank 13）拉到 top-1; 查询措辞脆弱性的正解。
        无 LLM（评测 bench）→ None, 行为不变。"""
        prompt = (
            "根据问题，写一段假设性的答案（3-5 句，包含可能的关键术语、"
            "算法名和事实），用于检索增强。只输出答案段落：\n问题: " + query
        )
        resp = self._chat_once(prompt, max_tokens=400)
        if not resp or not resp.strip():
            return None
        return self._embed(resp.strip())

    # ── 混合锚点 ─────────────────────────────────────────────────

    def _vector_anchors(self, query: str, top_k: int,
                        blocks: Optional[List[dict]] = None,
                        query_vec: Optional[list] = None) -> List[RecallHit]:
        """BGE 向量召回（余弦）; BGE 不可用 → ChunkStore 关键词兜底。"""
        _t0 = time.time()
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        # HyDE 查询向量（2026-08-13）: 假设答案嵌入, 语义含域术语
        qv = query_vec if query_vec is not None else self._embed(query)
        if qv is not None:
            scored = []
            batch_vecs = []
            batch_bids = []
            _vstat = {"from_emb": 0, "from_block": 0, "reembed": 0,
                      "dim_mismatch": 0, "block_no_vec": 0, "q_dim": len(qv)}
            for b in blocks:
                bid = b["id"]
                # 两级粒度（设计 12.2, 2026-08-11）: 有 summary 时优先对
                # 摘要打分（Coarse scan 快速定位）; 命中后执行层取全文。
                score_text = (b.get("summary") or "").strip() or b["text"]
                ev = self._embeddings.get(bid)
                if ev is None:
                    cached_vec = b.get("vector")
                    # 维度防护（2026-08-11）: 缓存向量维度与当前 query 不一致
                    # （旧模型 512/384 vs bge-m3 1024）→ 弃用重算, 否则余弦恒 0
                    if cached_vec is not None and len(cached_vec) == len(qv):
                        ev = cached_vec
                        self._embeddings[bid] = ev
                        _vstat["from_block"] += 1
                    elif cached_vec is not None:
                        _vstat["dim_mismatch"] += 1
                    else:
                        _vstat["block_no_vec"] += 1
                else:
                    _vstat["from_emb"] += 1
                if ev is None:
                    # 两级粒度（2026-08-12）: 嵌入"标题+核心内容"窗口,
                    # 与 doc_recall_bench.prepare_vectors 同口径（粗扫描）;
                    # 全文由子图扩展/执行层抓取。全文嵌入被巨块
                    # （>8K 字符 → 8192 token 序列）拖到 30 分钟+。
                    coarse = ((b.get("heading") or "")
                              + "\n" + score_text)[:1500]
                    ev = self._embed(coarse)
                    if ev is None:
                        continue
                    self._embeddings[bid] = ev
                    entry = self._index_cache.setdefault(bid, {})
                    entry["vector"] = ev
                    # hash 用全文（与 _ensure_blocks 一致）: 全文变 → 缓存失效,
                    # summary 向量同步重算。保证 spo/vector 缓存同指纹。
                    entry["hash"] = self._text_hash(b["text"])
                    _vstat["reembed"] += 1
                batch_vecs.append(ev)
                batch_bids.append(bid)
            logger.info("vector_anchors: %.1fms blocks=%d emb=%d block=%d "
                        "mismatch=%d novec=%d reembed=%d qdim=%d",
                        (time.time() - _t0) * 1000, len(blocks),
                        _vstat["from_emb"], _vstat["from_block"],
                        _vstat["dim_mismatch"], _vstat["block_no_vec"],
                        _vstat["reembed"], _vstat["q_dim"])
            # Rust 批量余弦（2026-08-11, recall_rust_bridge）: 行为等价,
            # 未编译自动回退 Python。2026-08-12: 矩阵按块集缓存, 省
            # list→array 拷贝（8594 块 × 1024 维 ≈ 70MB/query）。
            try:
                from core.agent.recall.recall_rust_bridge import get_recall_kernel
                import numpy as np
                kernel = get_recall_kernel()
                mkey = (tuple(batch_bids), len(self._embeddings), len(qv))
                if (self._vec_matrix is None
                        or self._vec_matrix_key != mkey
                        or self._vec_matrix.shape[0] != len(batch_bids)):
                    arr = np.asarray(batch_vecs, dtype=np.float64)
                    self._vec_matrix = arr
                    self._vec_matrix_key = mkey
                    self._vec_bids = list(batch_bids)
                else:
                    arr = self._vec_matrix
                if hasattr(kernel, "cosine_topk_buffer"):
                    # PyBuffer 零拷贝（2026-08-11）: numpy 直接提取
                    sims = kernel.cosine_topk_buffer(
                        arr, arr.shape[1],
                        np.asarray(qv, dtype=np.float64), arr.shape[0])
                elif hasattr(kernel, "cosine_topk_bytes"):
                    sims = kernel.cosine_topk_bytes(
                        arr.tobytes(), arr.shape[1],
                        np.asarray(qv, dtype=np.float64).tobytes(),
                        arr.shape[0])
                else:
                    sims = kernel.cosine_topk(
                        arr.flatten().tolist(), arr.shape[1],
                        qv, arr.shape[0])
                # Rust 返回 (行索引, 分数) → 经 batch_bids 映射回块 id
                # （2026-08-12 修复: 此前误把行索引当块 id, Rust 激活时
                # 向量路全部被过滤掉, doc 域召回归零）。
                for row_idx, s in sims:
                    if s <= 0.3 or row_idx >= len(batch_bids):
                        continue
                    bid = batch_bids[row_idx]
                    b = self._blocks_cache.get(bid)
                    if b is None:
                        b = next((x for x in blocks if x["id"] == bid), None)
                    if b is not None:
                        scored.append((s, b))
            except Exception:
                for b in blocks:
                    ev = self._embeddings.get(b["id"])
                    if ev is None:
                        continue
                    sim = self._cosine(qv, ev)
                    if sim > 0.3:
                        scored.append((sim, b))
            scored.sort(key=lambda x: x[0], reverse=True)
            self._save_index_cache(getattr(self, "_index_cache_file", "default"))
            hits = []
            for sim, b in scored[:top_k]:
                    hits.append(RecallHit(
                        id=b["id"], text=b["text"][:200], source="vector",
                        score=sim, confidence=self._confidence("vector"),
                        temperature=b["temperature"],
                        path=b.get("path") or [],
                        created_at=b.get("created_at"),
                    ))
            logger.info("vector_anchors: %.1fms blocks=%d", 
                        (time.time() - _t0) * 1000, len(blocks))
            return hits
        # 兜底: ChunkStore（关键词或 unified 后端）
        if self._chunk is not None:
            try:
                atoms = self._chunk.search(query, top_k=top_k)
                return [
                    RecallHit(
                        id=a.atom_id, text=a.text[:200], source="vector",
                        score=a.priority, confidence=self._confidence("vector"),
                    )
                    for a in atoms
                ]
            except Exception:
                pass
        return []

    def _bm25_tokenize(self, text: str) -> List[str]:
        """分词（与 TopicQuickMatcher._tokenize 同语义: jieba, 单字过滤）。"""
        try:
            from core.agent.compiler.topic_quick_match import TopicQuickMatcher
            return TopicQuickMatcher()._tokenize(text)
        except Exception:
            return []

    def _bm25_index(self, blocks: List[dict]) -> Optional[dict]:
        """稀疏 BM25 词项索引（每块 tokenize 一次, 按块 id 集缓存）。

        2026-08-12 语义修正: 旧实现逐块 _bm25_score 且空 matcher（df 恒 0
        常量 idf, avg_len=0 退化为 TF）; 现按语料真实 df/avg_len 打分,
        与 Rust bm25_scores 内核（RECALL_RUST_DESIGN §三）口径一致。

        2026-08-12 持久化: 11761 块 jieba 全量分词 ~14s/进程; 索引与
        块集绑定（ids 集合 hash 作文件名）落盘 gzip, 二次进程直接加载。
        """
        _t0 = time.time()
        key = tuple(b["id"] for b in blocks)
        cached = self._bm25_indexes.get(key)
        if cached is not None:
            return cached
        # 磁盘缓存（按块集指纹: ids + 内容 hash）: 命中则跳过全量分词。
        # 2026-08-13 修复: key 只含 ids 时, 相同 id 不同内容（测试池复用
        # b1/b2/b3、语料重建）会命中脏索引 → 误命中/漏命中。
        import hashlib, gzip, json as _json
        _content_h = hashlib.md5()
        for _b in blocks:
            _content_h.update((_b.get("text") or "")[:200].encode(
                "utf-8", "replace"))
        fp = hashlib.md5(
            ("|".join(key) + "::" + _content_h.hexdigest()).encode(
                "utf-8", "replace")).hexdigest()[:20]
        disk_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            "data", "recall_index", "bm25_%s.json.gz" % fp)
        if os.path.exists(disk_path):
            try:
                with gzip.open(disk_path, "rt", encoding="utf-8") as f:
                    idx_obj = _json.load(f)
                idx_obj["term_id"] = {
                    k: int(v) for k, v in idx_obj["term_id"].items()}
                idx_obj["df"] = [tuple(x) for x in idx_obj["df"]]
                idx_obj["docs"] = [tuple(x) for x in idx_obj["docs"]]
                self._bm25_indexes[key] = idx_obj
                logger.info("bm25_index: loaded %d docs from %s (%.0fms)",
                            idx_obj["n_docs"], os.path.basename(disk_path),
                            (time.time() - _t0) * 1000)
                return idx_obj
            except Exception as e:
                logger.debug("bm25 index disk load failed: %s", e)
        with self._bm25_build_lock:
            cached = self._bm25_indexes.get(key)
            if cached is not None:
                return cached
            term_id: Dict[str, int] = {}
            docs: List[tuple] = []
            df_counts: Dict[int, int] = {}
            doc_lens: List[float] = []
            for idx, b in enumerate(blocks):
                score_text = (b.get("summary") or "").strip() or b["text"]
                toks = self._bm25_tokenize(score_text)
                doc_lens.append(float(len(toks)))
                tf: Dict[str, int] = {}
                for t in toks:
                    tf[t] = tf.get(t, 0) + 1
                for t, c in tf.items():
                    tid = term_id.setdefault(t, len(term_id))
                    docs.append((idx, tid, c))
                    df_counts[tid] = df_counts.get(tid, 0) + 1
            if not docs:
                idx_obj = {"docs": [], "df": [], "term_id": {},
                           "doc_lens": [], "avg_len": 0.0,
                           "n_docs": len(blocks)}
                self._bm25_indexes[key] = idx_obj
                return idx_obj
            avg_len = sum(doc_lens) / max(1, len(doc_lens))
            idx_obj = {
                "docs": docs,
                "df": [(tid, c) for tid, c in sorted(df_counts.items())],
                "term_id": term_id,
                "doc_lens": doc_lens,
                "avg_len": avg_len,
                "n_docs": len(blocks),
            }
            self._bm25_indexes[key] = idx_obj
            logger.info("bm25_index: built %d docs / %d terms / %.1fs",
                        len(blocks), len(term_id), time.time() - _t0)
            try:
                with gzip.open(disk_path, "wt", encoding="utf-8") as f:
                    _json.dump(idx_obj, f, ensure_ascii=False)
            except Exception as e:
                logger.debug("bm25 index disk save failed: %s", e)
            return idx_obj

    def _bm25_anchors(self, query: str, top_k: int,
                      blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """BM25 词法召回（Rust 稀疏内核, Python 回退; 语料真实 df）。

        2026-08-12: 旧实现每 query 对每块重分词打分（文档池 8.6-10s/query）;
        现 = 词项索引（每块分词一次按块集缓存）+ Rust bm25_scores 批量打分。
        """
        _t0 = time.time()
        # 跨语言保护 (2026-08-10, 变体评测 en 0% 根因):
        # 非中文 query 对中文语料做词法匹配会因 ASCII 术语（tool_loop/
        # blueprint 等）与中文块内同名术语碰巧匹配产生假高分, 压过向量
        # 语义分。英文/混合 query 的词法召回交给向量（BGE-M3 统一空间）。
        if not _is_chinese_query(query):
            return []
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        if not blocks:
            return []
        idx = self._bm25_index(blocks)
        term_id = idx["term_id"]
        qids: List[int] = []
        seen: set = set()
        for t in self._bm25_tokenize(query):
            tid = term_id.get(t)
            if tid is not None and tid not in seen:
                qids.append(tid)
                seen.add(tid)
        if not qids:
            return []
        try:
            from core.agent.recall.recall_rust_bridge import get_recall_kernel
            kernel = get_recall_kernel()
            scored = kernel.bm25_scores(
                idx["docs"], idx["df"], idx["n_docs"], qids,
                1.2, 0.75, idx["doc_lens"], idx["avg_len"])
        except Exception as e:
            logger.debug("bm25 kernel failed: %s", e)
            scored = []
        scored = [(d, s) for d, s in scored if s > 0]
        # 确定性排序（2026-08-12）: Rust bm25_scores 内部 HashMap 迭代
        # 顺序跨进程随机（RandomState 种子不同）→ 平分时 bm25 源内排名
        # 跨进程漂移 → RRF 融合 top1 在重跑间翻转（实测 22↔21/39）。
        # 显式 tie-break: 分数降序 + doc 索引升序。
        scored.sort(key=lambda x: (-x[1], x[0]))
        logger.info("bm25_anchors: %.1fms blocks=%d hits=%d qterms=%d",
                    (time.time() - _t0) * 1000, len(blocks), len(scored),
                    len(qids))
        if not scored:
            return []
        max_s = scored[0][1] or 1.0
        out = []
        for doc_idx, s in scored[:top_k]:
            b = blocks[doc_idx]
            out.append(RecallHit(
                id=b["id"], text=b["text"][:200], source="bm25",
                score=s / max_s, confidence=self._confidence("bm25"),
                temperature=b["temperature"],
                path=b.get("path") or [],
                created_at=b.get("created_at"),
            ))
        return out

    def _spo_anchors(self, query: str, top_k: int,
                     blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """约束空间投影对齐（SPO 结构映射）:
        查询 SPO vs 块 SPO 按 谓语0.5/主语0.3/宾语0.2 加权对齐。
        2026-08-08 升级: 谓词对齐从"字面"升级为"抽象关系类型"
        （map_predicate: "源于"=="是"==is_a → 语义归一, 双语两阶段设计）。
        """
        _t0 = time.time()
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        from core.agent.recall.spo_relation_map import map_predicate, set_llm
        if self._llm is not None:
            set_llm(self._llm)
        q_spo = self._extract_spo(query)
        if not q_spo:
            return []
        # 两级粒度（2026-08-12）: 候选集限定 — SPO 是排序精修, 先由
        # vector/bm25 粗扫描定位 top-C 再做约束投影对齐, 避免全池
        # O(n) 对齐（11493 块 ~330ms/池）。候选外块本就不进融合前列。
        cap = getattr(self, "spo_candidate_cap", 0)
        if cap and len(blocks) > cap:
            cand_ids = set()
            for h in self._vector_anchors(query, cap, blocks=blocks):
                cand_ids.add(h.id)
            for h in self._bm25_anchors(query, cap, blocks=blocks):
                cand_ids.add(h.id)
            blocks = [b for b in blocks if b["id"] in cand_ids]
        scored = []
        use_norm = getattr(self, "fuse_mode", "linear") == "norm"
        for b in blocks:
            b_spo = b.get("spo") or []
            if not b_spo:
                continue
            best = 0.0
            for qs in q_spo:
                for bs in b_spo:
                    s = 0.0
                    if use_norm:
                        q_subj = self._norm(qs.get("subject") or "")
                        b_subj = self._norm(bs.get("subject") or "")
                        q_pred = self._norm(qs.get("predicate") or "")
                        b_pred = self._norm(bs.get("predicate") or "")
                        q_obj = self._norm(qs.get("obj") or "")
                        b_obj = self._norm(bs.get("obj") or "")
                    else:
                        q_subj = qs.get("subject") or ""
                        b_subj = bs.get("subject") or ""
                        q_pred = qs.get("predicate") or ""
                        b_pred = bs.get("predicate") or ""
                        q_obj = qs.get("obj") or ""
                        b_obj = bs.get("obj") or ""
                    if q_subj and q_subj == b_subj:
                        s += 0.3
                    if q_pred and b_pred:
                        if q_pred == b_pred:
                            s += 0.5  # 字面一致
                        elif map_predicate(q_pred) == map_predicate(b_pred):
                            s += 0.5  # 抽象关系类型一致（语义归一）
                    if q_obj and q_obj == b_obj:
                        s += 0.2
                    if s > best:
                        best = s
            if best > 0:
                scored.append((best, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        logger.info("spo_anchors: %.1fms blocks=%d hits=%d",
                    (time.time() - _t0) * 1000, len(blocks), len(scored))
        return [
            RecallHit(
                id=b["id"], text=b["text"][:200], source="spo",
                score=s, confidence=self._confidence("spo"),
                temperature=b["temperature"], spo=(b.get("spo") or [{}])[0],
                path=b.get("path") or [],
                created_at=b.get("created_at"),
            )
            for s, b in scored[:top_k]
        ]

    def _assoc_anchors(self, query: str, top_k: int,
                       blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """关联链源（转化投影）: 有 AssociationService 检索接口则并入, 否则跳过。"""
        if blocks is None:
            self._ensure_blocks()
        assoc = getattr(self._engine, "_assoc_service", None)
        if assoc is None:
            return []
        for method in ("retrieve", "query", "search"):
            fn = getattr(assoc, method, None)
            if fn is None:
                continue
            try:
                rows = fn(query, top_k=top_k) if method != "search" else fn(query)
                if not rows:
                    return []
                hits = []
                for r in rows[:top_k]:
                    text = (
                        r.get("text") or r.get("summary") or r.get("content")
                        or str(r)[:100]
                    )
                    hits.append(RecallHit(
                        id=str(r.get("id", f"assoc_{len(hits)}")),
                        text=str(text)[:200], source="assoc",
                        score=float(r.get("score", 0.5)),
                        confidence=self._confidence("assoc"),
                    ))
                return hits
            except Exception as e:
                logger.debug("assoc anchor failed: %s", e)
                return []
        return []

    def _expand_questions(self, query: str) -> List[str]:
        """HyDE/question 式召回: LLM 把 query 展开为 N 个子问题; 无 LLM → 原 query。

        2026-08-11 升级（SUBGRAPH_EXPANSION_UPGRADE 设计 2）: 子问题数可配
        （decompose_subqueries）; 失败不阻塞（返回原 query 兜底）; 失败记录
        进 _decompose_misses 供元认知复盘。
        """
        if self._llm is None:
            return [query]
        n = max(1, int(getattr(self, "decompose_subqueries", 3)))
        prompt = (
            f"把下面的查询展开为 {n} 个更具体的子问题（每行一个, 只输出问题）:\n"
            f"查询: {query}"
        )
        try:
            if hasattr(self._llm, "chat"):
                resp = self._llm.chat([{"role": "user", "content": prompt}])
            elif hasattr(self._llm, "complete"):
                resp = self._llm.complete(prompt)
            elif hasattr(self._llm, "generate"):
                from core.agent.llm_providers.base import GenerateRequest
                result = self._llm.generate(GenerateRequest(
                    prompt=prompt, max_tokens=256, temperature=0.3))
                resp = result.text if result is not None else ""
            else:
                return [query]
            text = resp if isinstance(resp, str) else getattr(resp, "content", "")
            qs = [q.strip() for q in text.splitlines() if q.strip()][:n]
            return [query] + qs if qs else [query]
        except Exception as e:
            logger.debug("HyDE expansion failed: %s", e)
            self._decompose_misses.append({"query": query, "error": str(e)[:120]})
            return [query]

    def _expand_questions_legacy(self, query: str) -> List[str]:
        """旧行为: 展开 2-3 子问题（并行分解关闭时的轻量兜底）。"""
        if self._llm is None:
            return [query]
        prompt = (
            f"把下面的查询展开为 2-3 个更具体的子问题（每行一个, 只输出问题）:\n"
            f"查询: {query}"
        )
        try:
            if hasattr(self._llm, "chat"):
                resp = self._llm.chat([{"role": "user", "content": prompt}])
            elif hasattr(self._llm, "complete"):
                resp = self._llm.complete(prompt)
            elif hasattr(self._llm, "generate"):
                from core.agent.llm_providers.base import GenerateRequest
                result = self._llm.generate(GenerateRequest(
                    prompt=prompt, max_tokens=256, temperature=0.3))
                resp = result.text if result is not None else ""
            else:
                return [query]
            text = resp if isinstance(resp, str) else getattr(resp, "content", "")
            qs = [q.strip() for q in text.splitlines() if q.strip()][:3]
            return [query] + qs if qs else [query]
        except Exception as e:
            logger.debug("HyDE expansion failed: %s", e)
            return [query]

    def _hyde_anchors(self, expanded: List[str], top_k: int) -> List[RecallHit]:
        """对扩展问题并行全路召回, 合并去重（2026-08-11 升级）。

        旧行为: 串行只走 vector。新行为: 并行（线程池, I/O 密集不受 GIL 限制）
        每子问题走 vector+bm25+spo（全路）; 子问题全空 → 记 miss 不阻塞。
        """
        seen = set()
        hits = []
        pool = getattr(self, "decompose_max_workers", 4)

        def _one(q):
            out = []
            for h in self._vector_anchors(q, top_k):
                out.append(h)
            for h in self._bm25_anchors(q, top_k):
                out.append(h)
            for h in self._spo_anchors(q, top_k):
                out.append(h)
            return q, out

        if getattr(self, "parallel_decompose", False) and len(expanded) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max(1, pool)) as ex:
                results = list(ex.map(_one, expanded))
        else:
            results = [_one(q) for q in expanded]
        for q, sub in results:
            if not sub:
                self._decompose_misses.append({"query": q, "error": "empty recall"})
                continue
            for h in sub:
                if h.id in seen:
                    continue
                seen.add(h.id)
                h.source = "hyde"
                h.confidence = self._confidence("hyde")
                hits.append(h)
        return hits[:top_k]

    # ── 扩散 ────────────────────────────────────────────────────

    def _diffuse(self, anchors: List[RecallHit], k: int = 2) -> List[RecallHit]:
        """锚点块沿对话树 parent/child 扩散 k-hop（hierarchical 权重 0.8/hop）。"""
        out = []
        for a in anchors:
            frontier = [(a.id, 0)]
            visited = {a.id}
            while frontier:
                cur, depth = frontier.pop(0)
                if depth >= k:
                    continue
                b = self._blocks_cache.get(cur)
                if b is None:
                    continue
                nbrs = [b["parent"]] if b.get("parent") else []
                nbrs += [c for c in b.get("children", []) if c != a.id]
                for nb in nbrs:
                    if nb in visited or nb not in self._blocks_cache:
                        continue
                    visited.add(nb)
                    nb_info = self._blocks_cache[nb]
                    hop = depth + 1
                    out.append(RecallHit(
                        id=nb, text=nb_info["text"][:200], source="diffusion",
                        score=a.score * (0.8 ** hop),
                        confidence=a.confidence * 0.9,
                        temperature=nb_info["temperature"],
                        hops=hop,
                        path=nb_info.get("path") or [a.id, nb],
                    ))
                    frontier.append((nb, hop))
        return out

    # ── A18 权重自适应 + A6 反馈 ─────────────────────────────────

    def _confidence(self, source: str) -> float:
        """读取可学习置信度（默认表, 被 feedback 调整后覆盖）。"""
        return self._learned_conf.get(source, SOURCE_CONFIDENCE[source])

    def feedback(self, hit_id: str, useful: bool, note: str = "") -> dict:
        """A6 后验反馈: ε 步长调整来源置信度（GAP-D4 update_source_credibility 落地）。
        持久化后续接入（当前进程内; 记录可审计）。"""
        found = None
        # 从最近一次结果里找 hit
        if self._last_result:
            for h in self._last_result.hits:
                if h.id == hit_id:
                    found = h
                    break
        if found is None:
            return {"ok": False, "error": "hit not found"}
        base_source = found.source.split(":", 1)[-1]  # hot:bm25 -> bm25
        conf = self._confidence(base_source)
        new_conf = max(0.1, min(1.0, conf + (EPSILON if useful else -EPSILON)))
        self._learned_conf[base_source] = new_conf
        self._feedback_log.append({
            "ts": time.time(), "hit_id": hit_id, "source": base_source,
            "useful": useful, "before": round(conf, 4),
            "after": round(new_conf, 4), "note": note,
        })
        return {
            "ok": True, "source": base_source,
            "before": round(conf, 4), "after": round(new_conf, 4),
        }

    def weights(self) -> dict:
        """A18 参数白盒: 当前各源置信度（可调节）。"""
        return {k: round(self._confidence(k), 4) for k in SOURCE_CONFIDENCE}

    def set_weight(self, source: str, value: float) -> dict:
        """A18 用户感知调节: 显式覆盖某源置信度（clamp 0.1-1.0）。"""
        if source not in SOURCE_CONFIDENCE:
            return {"ok": False, "error": f"unknown source: {source}"}
        self._learned_conf[source] = max(0.1, min(1.0, float(value)))
        return {"ok": True, "source": source,
                "confidence": round(self._learned_conf[source], 4)}

    # ── 主入口 ─────────────────────────────────────────────────

    def recall(
        self,
        query: str,
        intent: Optional[str] = None,
        top_k: int = 10,
        sid: Optional[str] = None,
        use_hyde: bool = True,
    ) -> RecallResult:
        t0 = time.time()
        self._last_sid = sid
        hot_blocks = self._ensure_blocks(sid)
        cold_blocks = self._ensure_global_blocks()
        if use_hyde and getattr(self, "parallel_decompose", False):
            expanded = self._expand_questions(query)
        elif use_hyde:
            expanded = self._expand_questions_legacy(query)
        else:
            expanded = [query]
        hits: List[RecallHit] = []
        single = getattr(self, "single_source", None)
        # HyDE 查询向量（2026-08-13, DM_HYDE=1）: 假设答案嵌入喂给
        # vector 路（bm25/spo 仍用原 query）; 无 LLM 时自动跳过。
        hyde_vec = None
        if os.environ.get("DM_HYDE", "0") == "1" and self._llm is not None:
            hyde_vec = self._hyde_query_vector(query)

        def _run(blocks, tag):
            out = []
            if single in (None, "vector"):
                out += self._vector_anchors(
                    query, top_k, blocks=blocks, query_vec=hyde_vec)
            if single in (None, "bm25"):
                out += self._bm25_anchors(query, top_k, blocks=blocks)
            if single in (None, "spo"):
                out += self._spo_anchors(query, top_k, blocks=blocks)
            if single in (None, "assoc"):
                out += self._assoc_anchors(query, top_k, blocks=blocks)
            return out

        # 热路径: 当前会话块（小池, 快, 优先）
        hot_hits = _run(hot_blocks, "hot")
        for h in hot_hits:
            h.source = "hot:" + h.source
        hits += hot_hits
        # 冷路径: 全局块池（大池, 覆盖广）
        cold_hits = _run(cold_blocks, "cold")
        # 2026-08-13 修复: cold 命中必须打 "cold:" 前缀（与 hot 对称）—
        # 此前无前缀, 冷池独有时（生产无会话树/文档语料池）vector_primary
        # 融合的 vec_rank 查不到 cold:vector → 退化为 RRF 排序, 冷池
        # 排序错误（评测热池=全块掩盖了此 bug）。
        for h in cold_hits:
            h.source = "cold:" + h.source
        if getattr(self, "dedup_pools", True):
            hot_ids = {h.id for h in hot_hits}
            cold_hits = [h for h in cold_hits if h.id not in hot_ids]
        hits += cold_hits
        # HyDE（仅全量模式）
        if single == "hyde":
            hits += self._hyde_anchors(expanded, top_k)
        elif use_hyde and single is None and len(expanded) > 1:
            hits += self._hyde_anchors(expanded, top_k)
        # 扩散（在锚点基础上）
        anchor_ids = {h.id for h in hits}
        if single is None:
            hits += self._diffuse(hits, k=2)
        # 融合排序 + 去重
        best: Dict[str, RecallHit] = {}
        if getattr(self, "fuse_mode", "linear") == "rrf":
            # RRF: 每源内按 score 排序得 rank, 跨源累加 1/(k+rank)（尺度不敏感）
            from collections import defaultdict
            by_source: Dict[str, List[RecallHit]] = defaultdict(list)
            for h in hits:
                by_source[h.source].append(h)
            rrf_scores: Dict[str, float] = defaultdict(float)
            for src, hs in by_source.items():
                hs.sort(key=lambda h: h.score, reverse=True)
                w = 1.0
                if getattr(self, "rrf_conf_weight", False):
                    w = self._confidence(src.split(":", 1)[-1])
                for rank, h in enumerate(hs):
                    rrf_scores[h.id] += w / (60 + rank + 1)
            for h in hits:
                if h.id in best:
                    continue
                if h.id in rrf_scores:
                    h.score = rrf_scores[h.id]
                best[h.id] = h
            ordered = sorted(
                best.values(),
                key=lambda h: h.score * self._temporal_factor(h),
                reverse=True)
        elif getattr(self, "fuse_mode", "linear") == "vector_primary":
            # 证据驱动融合（2026-08-12, 待全量验证）: 诊断显示 100 条中
            # 全部 top1 来自 vector 路线, 且 vector 内 #1 的 45 条中有
            # ~10 条被其他源长尾压出 #1（RRF 负增益）。vector 命中的块
            # 按向量相似度序主导排序; 非 vector 块（bm25/spo 独有召回,
            # 扩展性来源）按 RRF 续排 — 召回扩展与排序解耦。
            from collections import defaultdict
            by_source = defaultdict(list)
            for h in hits:
                by_source[h.source].append(h)
            vec_rank: Dict[str, int] = {}
            vh = list(by_source.get("hot:vector", []))
            cold_vec = by_source.get("cold:vector", [])
            if cold_vec:
                vh_ids = {x.id for x in vh}
                vh += [h for h in cold_vec if h.id not in vh_ids]
            vh.sort(key=lambda h: h.score, reverse=True)
            for rank, h in enumerate(vh):
                vec_rank.setdefault(h.id, rank)
            rrf_scores = defaultdict(float)
            for src, hs in by_source.items():
                hs.sort(key=lambda h: h.score, reverse=True)
                for rank, h in enumerate(hs):
                    rrf_scores[h.id] += 1.0 / (60 + rank + 1)
            for h in hits:
                if h.id in best:
                    continue
                if h.id in rrf_scores:
                    h.score = rrf_scores[h.id]
                best[h.id] = h
            ordered = sorted(
                best.values(),
                key=lambda h: (
                    h.id not in vec_rank,
                    vec_rank.get(h.id, 1 << 30),
                    -h.score,
                ))
        else:
            for h in hits:
                cur = best.get(h.id)
                if cur is None or h.fused() > cur.fused():
                    best[h.id] = h
            ordered = sorted(
                best.values(),
                key=lambda h: h.fused() * self._temporal_factor(h),
                reverse=True)
        result = RecallResult(
            query=query,
            hits=ordered[:top_k],
            expanded_queries=expanded,
            latency_ms=(time.time() - t0) * 1000,
        )
        self._last_result = result
        return result
