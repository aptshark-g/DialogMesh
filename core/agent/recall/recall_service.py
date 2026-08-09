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
        self._learned_conf: Dict[str, float] = {}
        self._last_result: Optional[RecallResult] = None
        self._spo_cache: Dict[str, List[dict]] = {}
        self._index_cache: Dict[str, dict] = {}   # bid -> {spo, vector}
        self._index_cache_dir = None
        self._index_cache_file = "default"
        self._global_block_list: List[dict] = []
        self.fuse_mode = "linear"   # linear | rrf | norm（RRF 融合 / 规则增强）
        # 时序约束（2026-08-09, 评测驱动发现）: 文档/块版本新旧降权。
        # 0 = 关闭（默认, 不改变既有行为）; >0 = 半衰期天数,
        # 排序分 = fused() × 2^(-age_days / half_life), 下限 0.3。
        self.time_half_life_days = 0.0

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
            spo = cached.get("spo") or self._extract_spo(text)
            blocks.append({
                "id": bid,
                "text": text,
                "parent": getattr(b, "parent_id", None),
                "children": list(getattr(b, "child_ids", [])),
                "temperature": getattr(b, "status", "active"),
                "spo": spo,
                "vector": cached.get("vector"),
            })
            self._index_cache.setdefault(bid, {})["spo"] = spo
        self._block_list = blocks
        self._blocks_cache = {b["id"]: b for b in blocks}
        self._current_sid = key
        self._index_cache_file = key
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
        tm = self._discourse
        if tm is None or not getattr(tm, "blocks", None):
            return []
        self._load_index_cache("global")
        blocks = []
        for bid, b in tm.blocks.items():
            text = (
                getattr(b, "_raw_text", "") or " ".join(
                    getattr(u, "raw_text", "") for u in getattr(b, "atomic_units", [])
                )
            ).strip()
            if not text:
                continue
            cached = self._index_cache.get(bid) or {}
            blocks.append({
                "id": bid,
                "text": text,
                "parent": getattr(b, "parent_id", None),
                "children": list(getattr(b, "child_ids", [])),
                "temperature": getattr(b, "status", "active"),
                "spo": cached.get("spo") or self._extract_spo(text),
                "vector": cached.get("vector"),
                "session": getattr(b, "_session_id", ""),
            })
        self._global_block_list = blocks
        self._index_cache_file = "global"
        self._save_index_cache("global")
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

    def _load_index_cache(self, sid: str) -> None:
        import os, json
        path = self._index_path(sid)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._index_cache = data.get("blocks", {}) if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("index cache load failed: %s", e)
            self._index_cache = {}

    def _save_index_cache(self, sid: str) -> None:
        import json
        if not self._index_cache:
            return
        try:
            path = self._index_path(sid)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"blocks": self._index_cache}, f, ensure_ascii=False)
            import os
            os.replace(tmp, path)
        except Exception as e:
            logger.debug("index cache save failed: %s", e)

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

    # ── 混合锚点 ─────────────────────────────────────────────────

    def _vector_anchors(self, query: str, top_k: int,
                        blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """BGE 向量召回（余弦）; BGE 不可用 → ChunkStore 关键词兜底。"""
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        qv = self._embed(query)
        if qv is not None:
            scored = []
            for b in blocks:
                bid = b["id"]
                if b.get("vector") is not None:
                    ev = b["vector"]
                    self._embeddings[bid] = ev
                elif bid not in self._embeddings:
                    ev = self._embed(b["text"])
                    if ev is None:
                        continue
                    self._embeddings[bid] = ev
                    self._index_cache.setdefault(bid, {})["vector"] = ev
                sim = self._cosine(qv, self._embeddings[bid])
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

    def _bm25_anchors(self, query: str, top_k: int,
                      blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """BM25 词法召回（TopicQuickMatcher._bm25_score 同款算法）。"""
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        try:
            from core.agent.compiler.topic_quick_match import TopicQuickMatcher
            matcher = TopicQuickMatcher()
        except Exception:
            return []
        scored = []
        for b in blocks:
            try:
                s = matcher._bm25_score(query, b["text"])
            except Exception:
                s = 0.0
            if s > 0:
                scored.append((s, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return []
        max_s = scored[0][0] or 1.0
        return [
            RecallHit(
                id=b["id"], text=b["text"][:200], source="bm25",
                score=s / max_s, confidence=self._confidence("bm25"),
                temperature=b["temperature"],
                path=b.get("path") or [],
                created_at=b.get("created_at"),
            )
            for s, b in scored[:top_k]
        ]

    def _spo_anchors(self, query: str, top_k: int,
                     blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """约束空间投影对齐（SPO 结构映射）:
        查询 SPO vs 块 SPO 按 谓语0.5/主语0.3/宾语0.2 加权对齐。
        2026-08-08 升级: 谓词对齐从"字面"升级为"抽象关系类型"
        （map_predicate: "源于"=="是"==is_a → 语义归一, 双语两阶段设计）。
        """
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        from core.agent.recall.spo_relation_map import map_predicate, set_llm
        if self._llm is not None:
            set_llm(self._llm)
        q_spo = self._extract_spo(query)
        if not q_spo:
            return []
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
        """HyDE/question 式召回: LLM 把 query 展开为 2-3 个问题; 无 LLM → 原 query。"""
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
        """对扩展问题分别向量召回, 合并去重。"""
        seen = set()
        hits = []
        for q in expanded:
            for h in self._vector_anchors(q, top_k):
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
        expanded = self._expand_questions(query) if use_hyde else [query]
        hits: List[RecallHit] = []
        single = getattr(self, "single_source", None)

        def _run(blocks, tag):
            out = []
            if single in (None, "vector"):
                out += self._vector_anchors(query, top_k, blocks=blocks)
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
        hits += _run(cold_blocks, "cold")
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
                key=lambda h: h.score * self._temporal_factor(h),
                reverse=True)
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
