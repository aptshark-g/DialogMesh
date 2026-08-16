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
    "graph": 0.75,
}
TEMP_WEIGHT: Dict[str, float] = {
    "active": 1.0,
    "paused": 0.7,
    "cold": 0.4,
    "frozen": 0.1,
}
EPSILON = 0.02  # A18 ε 步长（反馈自适应）
PRONOUNS = {"它", "他", "她", "这", "那", "其"}

# 意图感知自适应融合（2026-08-13, W1 后半）: per-intent 融合配置。
# 每种意图天然最优路径不同（用户拍板: "各种意图天然最优不同"）——
# 记忆召回/知识问答重语义（vector 主导）; 数据搜索/代码分析重词法
# +结构（bm25/spo 权重上浮）; 因果推理重约束投影（spo 主导）。
# A18: 各意图各源置信度独立可学习（feedback(intent=...) 调整）。
# 意图名与 _GatewayLLMAdapter.classify_intent 的类别集对齐（软编码:
# 扩展只改这一处）。
INTENT_PROFILES: Dict[str, Dict[str, object]] = {
    "记忆召回": {
        "fuse_mode": "vector_primary",
        "weights": {"vector": 0.55, "bm25": 0.25, "spo": 0.15,
                    "hyde": 0.10, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.10},
        "hyde": True, "diffuse_k": 2, "graph": True,
    },
    "数据搜索": {
        "fuse_mode": "rerank",
        "weights": {"vector": 0.40, "bm25": 0.35, "spo": 0.20,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.10},
        "hyde": True, "diffuse_k": 1, "graph": True,
    },
    "代码分析": {
        "fuse_mode": "rerank",
        "weights": {"vector": 0.35, "bm25": 0.35, "spo": 0.25,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.12},
        "hyde": True, "diffuse_k": 1, "graph": True,
    },
    "任务规划": {
        "fuse_mode": "rerank",
        "weights": {"vector": 0.45, "bm25": 0.30, "spo": 0.20,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.10},
        "hyde": True, "diffuse_k": 2, "graph": True,
    },
    "因果推理": {
        "fuse_mode": "rerank",
        "weights": {"vector": 0.40, "bm25": 0.20, "spo": 0.35,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.10},
        "hyde": True, "diffuse_k": 2, "graph": True,
    },
    "通用讨论": {
        "fuse_mode": "vector_primary",
        "weights": {"vector": 0.50, "bm25": 0.25, "spo": 0.20,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.08},
        "hyde": False, "diffuse_k": 2, "graph": False,
        # 闲聊/讨论类不需要激进检索重排（2026-08-13 消融: casual top1
        # 100%→66.7%、通用讨论 100%→50% 是重排把对话命中挤下去的实例）。
        "rerank": False,
    },
    "casual": {
        "fuse_mode": "vector_primary",
        "weights": {"vector": 0.60, "bm25": 0.20, "spo": 0.10,
                    "hyde": 0.00, "assoc": 0.10, "diffusion": 0.05,
                    "graph": 0.00},
        "hyde": False, "diffuse_k": 1, "graph": False,
        "rerank": False,
    },
    "通用对话": {
        "fuse_mode": "vector_primary",
        "weights": {"vector": 0.55, "bm25": 0.25, "spo": 0.15,
                    "hyde": 0.05, "assoc": 0.05, "diffusion": 0.08,
                    "graph": 0.08},
        "hyde": False, "diffuse_k": 2, "graph": False,
        "rerank": False,
    },
}
# 默认重排权重（无意图/未知意图时）: 保守, vector 主导（dialogue 69.2%
# 由 vector 支撑, 不能因重排掉分）, 但 bm25/spo 独有命中可上浮
# （doc top1 31.1% 提升空间在此——纯 vector 漏检时词法/结构补位）。
RERANK_WEIGHTS: Dict[str, float] = {
    "vector": 0.55, "bm25": 0.25, "spo": 0.15, "hyde": 0.10,
    "assoc": 0.05, "diffusion": 0.08, "graph": 0.10,
}

# 真 HyDE 通用 prompt（2026-08-16, 泛化性设计）: 固定模板、零样本、
# 只含 query、不接触语料/评测标注 — 与 HyDE 原论文（2212.10496）一致,
# 一个模板跨所有 query/域直接使用（不是针对评测集的手写标准）。
# domain-aware: "像项目内部设计文档片段" — 这是按语料域（设计文档）给
# 指令, 与 HyDE 论文按数据集给域指令（如 Wikipedia 风格段落）同构, 属于
# 通用技术而非评测集特调。冒烟实测: 无此导向时假设文档太泛（ReAct/
# Function Calling 通用描述）, 检索命中通用文档而非本项目设计文档。
# 2026-08-16 从研究补充（见 RECALL_FUSION_ABLATION §六）:
#   - 多假设采样（K>1, 温度梯度）: 降低单假设幻觉/方差（RAG-Fusion 形态）
#   - 向量置信门控（DM_HYDE_GATE）: 向量 top-1 ≥ 阈值时不用 HyDE,
#     防假设文档漂移破坏高置信 query（Adaptive Hybrid / SAGE 思路）
#   - 结果作为独立 "hyde" 路线进 RRF 融合, 不替换原 query 向量
HYDE_PROMPT = (
    "根据问题，写一段假设性的设计文档片段（3-5 句，像项目内部设计文档"
    "的描述：包含关键技术术语、模块名、机制名和事实），用于检索增强。"
    "只输出段落，不要任何前言。\n问题: "
)


def normalize_intent(intent: Optional[str]) -> Optional[str]:
    """意图名归一: 空/未知名 → None（走默认 profile）。"""
    if not intent:
        return None
    i = str(intent).strip()
    if i in INTENT_PROFILES:
        return i
    # 别名兜底（英文/缩写 → 中文类别集）
    ALIASES = {
        "task": "任务规划", "任务": "任务规划", "plan": "任务规划",
        "code": "代码分析", "coding": "代码分析",
        "search": "数据搜索", "data": "数据搜索",
        "knowledge": "记忆召回", "memory": "记忆召回",
        "recall": "记忆召回", "query": "记忆召回",
        "why": "因果推理", "causal": "因果推理",
        "discuss": "通用讨论", "chat": "casual", "general": "通用对话",
    }
    return ALIASES.get(i.lower(), None)


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
    parent_context: str = ""          # 父块上下文（文件摘要, 2026-08-14）
    full_text: str = ""               # 全文（2026-08-15 加固: 细节保留,
                                      # P9 低概率高价值原样保留的落地 —
                                      # 锚点展示用 text[:200], 生成上下文
                                      # 用 full_text）
    created_at: float = field(default_factory=time.time)
    scores: Dict[str, float] = field(default_factory=dict)  # 每源原始分（重排用）
    rerank_score: float = 0.0          # 重排层输出分（白盒可查）

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
            "parent_context": self.parent_context[:200],
            "full_text": self.full_text[:4000],
            "scores": self.scores,
            "rerank_score": round(self.rerank_score, 6),
            "fused": round(self.fused(), 4),
        }


@dataclass
class RecallResult:
    query: str
    hits: List[RecallHit] = field(default_factory=list)
    expanded_queries: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    file_boost_ms: float = 0.0        # 文件层耗时（两级检索监控, 2026-08-14）
    files_hit: int = 0                # 文件层命中数
    pool_extras: List[RecallHit] = field(default_factory=list)  # C 最小版候选池扩展

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "expanded_queries": self.expanded_queries,
            "hits": [h.to_dict() for h in self.hits],
            "latency_ms": round(self.latency_ms, 1),
            "file_boost_ms": round(self.file_boost_ms, 1),
            "files_hit": self.files_hit,
            "pool_extras": [h.to_dict() for h in self.pool_extras],
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
        # 父块上下文（2026-08-14, 方案 B 返回层 — 对齐 ParentDocument
        # Retriever: 检索小块, 返回时附父块上下文, 不参与排序）
        if getattr(h, "parent_context", ""):
            line += f" | 文件: {h.parent_context[:120]}"
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
        # A18 持久化（2026-08-13）: 置信度/权重覆盖落盘 data/recall_index/
        # learned_conf.json — 重启不丢（此前进程内, 反馈即失）。
        # 键: "source"（全局）或 "意图:source"（per-intent）;
        # 权重覆盖: {"rerank:intent:source": w}（重排权重, 白盒可调）。
        self._weight_overrides: Dict[str, Dict[str, float]] = {}
        self._load_learned_conf()
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
        # 重排层（2026-08-13, P1）: 候选生成后按意图权重特征重排。
        # DM_RERANK=0 关闭（消融对比）。默认开。
        self.rerank = os.environ.get("DM_RERANK", "1") != "0"
        # 源独有保底（2026-08-14, 实验开关, 默认关）:
        # 设想 — vector_primary 下向量长尾填满 top-k, bm25/spo 独有
        # 命中被埋（doc 域 8 条 miss: vec=None 且 bm25 rank 1-2）。
        # 实测（eval_100 消融）— ×1.5 提升纯非 vector 命中是**负优化**:
        # doc top1 34.4%→31.1%, 记忆召回 40.3%→37.3% — bm25 假阳性
        # 同被抬升, 净损 3.3pp。结论: 无差别提升"源独有"= 无差别提升
        # 噪声; 保底必须区分"正确独有"与"噪声独有"（待设计, 如按
        # 源强度阈值/校验）, 当前保留开关供后续实验。
        self.source_guarantee = os.environ.get(
            "DM_SOURCE_GUARANTEE", "0") != "0"
        try:
            self.guarantee_boost = float(os.environ.get(
                "DM_SOURCE_GUARANTEE_BOOST", "1.5"))
        except ValueError:
            self.guarantee_boost = 1.5
        # 强独有信号保底 v2（2026-08-16, B 类修复消融）: 与
        # DM_SOURCE_GUARANTEE 的区别 — 旧版对"所有非 vector 命中"×1.5
        # （噪声同抬, 实测负增益）; 新版只对"无 vector 证据 + bm25/spo
        # 源内强分（≥阈值）"的块上浮（A25 多信号交叉: vector 失效时
        # 信任确定性词法/结构信号）。实测数据: q002/q033/q044/q052 期望
        # 块在 bm25 rank1-2 (score 0.89-1.0), vector 完全漏检, 被
        # vector_primary 长尾埋掉 → fused MISS。
        self.route_unique = os.environ.get(
            "DM_ROUTE_UNIQUE", "0") != "0"
        try:
            self.route_unique_threshold = float(os.environ.get(
                "DM_ROUTE_UNIQUE_THRESHOLD", "0.8"))
        except ValueError:
            self.route_unique_threshold = 0.8
        # 向量置信门控（2026-08-16, A 类稀释修复消融）: 本次 query 的
        # vector top-1 分 ≥ 阈值 → 向量可靠, 跳过重排（vector_primary
        # 直接按向量序, 防重排归一化把强纯 vector 命中稀释 — 实测
        # 记忆分层 vec=1→fused=19、G3 四保护 vec=1→fused=8 等 7 条）。
        # 对齐 RECALL_MAINSTREAM_GAP 引用的 Adaptive Hybrid（固定 Top-L
        # 融合 ≠ 全列表融合; 按 query 动态深度）与 SAGE（按查询难度动态
        # 选 k）— 这里是"按查询向量置信度动态选融合方式"。
        self.vector_gate = os.environ.get("DM_VEC_GATE", "0") != "0"
        try:
            self.vector_gate_threshold = float(os.environ.get(
                "DM_VEC_GATE_THRESHOLD", "0.70"))
        except ValueError:
            self.vector_gate_threshold = 0.70
        # 伪相关反馈（2026-08-16, DM_PRF, 默认关）: bm25 top-k 块向量
        # 质心 + 原 query 向量（Rocchio 混合）→ 二次 vector 检索。
        # 探查实证（_prf_probe）: B 类 4 条（q002/q033/q044/q052）期望块
        # 全不在 vector top-100（query-cos 0.43-0.51, BGE-M3 提问式 vs
        # 陈述式块缺陷）; PRF alpha=0.5-0.7 拉到 rank 1/1/None/1。
        # 主流技术（RECALL_MAINSTREAM_GAP: HyDE 的廉价替代/补充, 无 LLM）。
        self.prf = os.environ.get("DM_PRF", "0") != "0"
        try:
            self.prf_alpha = float(os.environ.get("DM_PRF_ALPHA", "0.5"))
        except ValueError:
            self.prf_alpha = 0.5
        try:
            self.prf_fb_blocks = int(os.environ.get("DM_PRF_FB", "3"))
        except ValueError:
            self.prf_fb_blocks = 3
        # 多假设 HyDE（2026-08-16, DM_HYDE_K 默认 1 = 既有单假设 query_vec
        # 行为不变）: >1 = 每假设文档独立检索 + RRF 合并（RAG-Fusion
        # 形态, "hyde" 独立路线进融合）。泛化设计见 HYDE_PROMPT 注释。
        try:
            self.hyde_k = int(os.environ.get("DM_HYDE_K", "1"))
        except ValueError:
            self.hyde_k = 1
        # 向量置信门控（DM_HYDE_GATE 默认关）: 本次 query 的 vector top-1
        # 分 ≥ 阈值 → 向量可靠, 不启用 HyDE（防假设文档漂移破坏高置信
        # query — 对齐 2026-08-16 消融: vec_gate 全量负是因为对 dialogue
        # 高置信也跳重排; 这里只对低置信 query 加 HyDE, 不动其它机制）。
        self.hyde_gate = os.environ.get("DM_HYDE_GATE", "0") != "0"
        try:
            self.hyde_gate_threshold = float(os.environ.get(
                "DM_HYDE_GATE_THRESHOLD", "0.70"))
        except ValueError:
            self.hyde_gate_threshold = 0.70
        # 旧查询分解路径开关（2026-08-16, DM_HYDE_DECOMPOSE 默认 1 保持
        # 既有行为）: use_hyde=True 时旧行为会 LLM 拆子问题并逐个子问题全路
        # 召回（_hyde_anchors）。真 HyDE 评测要隔离"多假设文档"的贡献,
        # 用 DM_HYDE_DECOMPOSE=0 跳过分解（expanded=[query]）。
        self.hyde_decompose = os.environ.get(
            "DM_HYDE_DECOMPOSE", "1") != "0"
        # HyDE→BM25 词项扩展（2026-08-17, DM_HYDE_BM25 默认 0 — 实测
        # 负结果）: 假设文档提取 tf×idf 加权扩展词 → 独立 BM25 检索 →
        # 与原 BM25 RRF 融合（论文 2511.19349: Rocchio 反馈模型优于朴素
        # 拼接）。冒烟+消融实证: 假设文档的通用脚手架词（Tool/进行/结果/
        # 机制…, 过滤后仍）检索到通用工具设计文档, 挤掉多向量弱增益
        # （q002: BM25 off rank13 → on None）。根因同向量侧 — 假设文档
        # 无法复现语料内部词汇。保留开关, 未来若换更贴近语料的生成
        # 方式（Query2Doc 拼接 / 微调）可重测。
        self.hyde_bm25 = os.environ.get("DM_HYDE_BM25", "0") != "0"
        try:
            self.hyde_bm25_terms = int(os.environ.get(
                "DM_HYDE_BM25_TERMS", "15"))
        except ValueError:
            self.hyde_bm25_terms = 15
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
        # 两级检索（2026-08-14, 方案 B+C 合并体）: 文件级摘要向量库
        # （~600 文件）— query 先打文件层, 命中文件的节块 boost +
        # parent_context 返回。摘要策略: mechanical（默认零成本）/
        # small（LM Studio）/ llm（网关）; DM_FILE_SUMMARY 覆盖。
        self._file_summaries: Optional[Dict[str, str]] = None
        self._file_summary_vectors: Dict[str, List[float]] = {}
        # 两级检索（2026-08-14 实验, 默认关 — 诚实消融结果）:
        # 文件层命中 → 节块保底抬分（Parent-Child 直投候选）。
        # 实测 doc top1 23→22（净损）: "文件对但块弱相关"的块被保底
        # 抬到 top-1, 挤掉真正相关块。方案 A（doc_title 嵌入窗口,
        # 34.4→37.7%）才是有效提升; 文件层保底需更精细设计
        # （文件命中后只在文件内部排序, 而非全局保底）— DM_FILE_BOOST=1
        # 开启实验。
        self._file_summary_boost = os.environ.get(
            "DM_FILE_BOOST", "0") != "0"
        self._file_boost_factor = 0.10   # 加性 boost（余弦分 +0.1）
        self._file_summary_top = 5       # 文件层 top-k
        # 2026-08-14（B 尾巴）: 文件层信号进重排权重（DM_FILE_RERANK=1）。
        # 不保底抬分（DM_FILE_BOOST 已被消融否决 — 全局保底挤掉真相关
        # 块）, 而是文件摘要命中 → 该文件节块的重排特征加权（可消融,
        # 与 DM_FILE_BOOST 正交: 一个动检索层, 一个动重排层）。
        self._file_rerank = os.environ.get(
            "DM_FILE_RERANK", "0") != "0"
        self._file_rerank_weight = 0.15   # 重排特征加性权重（与 w[src] 同量级）
        # 2026-08-14（C 最小版）: 文件命中 → 该文件节块进候选池扩展
        # （DM_FILE_POOL=1）。只扩候选不抬排序 — 消融结论: 文件层
        # 信号颗粒度错配, 抬排名必输; 价值在给子图更多锚点/合并材料。
        self._file_pool = os.environ.get("DM_FILE_POOL", "0") != "0"
        self._file_pool_per_doc = 3       # 每命中文件最多进池块数
        self._file_summary_strategy = os.environ.get(
            "DM_FILE_SUMMARY", "mechanical")
        self._file_summary_vec_path = None
        self._load_file_summary_vectors()
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
                # 2026-08-14: hot 块透传文件上下文（与 _ensure_global_blocks
                # 对齐）— doc/path 供返回层 parent_context 附加与文件级
                # boost; doc_title 供无预编码向量时的嵌入窗口（方案 A 同
                # 口径）。对话树块无这些属性 → 空值, 行为不变。
                "doc": getattr(b, "doc", "") or "",
                "doc_title": getattr(b, "doc_title", "") or "",
                "path": (getattr(b, "_path", None)
                         or ([getattr(b, "doc", "")]
                             if getattr(b, "doc", "") else [])),
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
                    "doc": getattr(b, "doc", ""),
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

    # ── 两级检索（2026-08-14, 方案 B+C 合并体）────────────────

    def _ensure_file_summaries(self) -> Dict[str, str]:
        """文件级摘要懒加载（全局池含 doc 块时才加载）。

        不依赖 enable_doc_corpus 开关（eval 的 doc_service 构造时
        未开该开关, 但块带 doc 字段 — 有 doc 块即加载）。"""
        if self._file_summaries is not None:
            return self._file_summaries
        pool = self._global_block_list or []
        has_doc = any(b.get("doc") for b in pool)
        if not has_doc:
            # 2026-08-14: eval/bench 的 doc 块在 hot 池（discourse）, 冷池
            # 为空 → 只看冷池会导致 parent_context 永远附加不上。hot 池
            # 有 doc 块（_ensure_blocks 已透传 doc）即加载。
            hot = self._block_list or []
            has_doc = any(b.get("doc") for b in hot)
        if not has_doc:
            self._file_summaries = {}
            return self._file_summaries
        try:
            from core.agent.recall.doc_corpus import load_file_summaries
            self._file_summaries = load_file_summaries(
                strategy=getattr(self, "_file_summary_strategy",
                                 "mechanical"))
        except Exception as e:
            logger.debug("file summaries load failed: %s", e)
            self._file_summaries = {}
        return self._file_summaries

    def _file_summary_vec_file(self) -> str:
        if self._file_summary_vec_path is None:
            self._file_summary_vec_path = os.path.join(
                self._index_dir(), "doc_file_summaries_vectors.json")
        return self._file_summary_vec_path

    def _load_file_summary_vectors(self) -> None:
        """文件摘要向量落盘加载（首查 23s → 秒级）。"""
        try:
            import json as _json
            with open(self._file_summary_vec_file(), "r",
                      encoding="utf-8") as f:
                self._file_summary_vectors = _json.load(f)
            # 2026-08-14 修复: 向量与摘要策略强绑定 — 缓存无策略标记
            # 或与当前策略不一致 → 全弃（否则 small 摘要配 mechanical
            # 旧向量, 文件层信号失真）。
            if (self._file_summary_vectors.get("_strategy")
                    != self._file_summary_strategy):
                self._file_summary_vectors = {}
        except Exception:
            self._file_summary_vectors = {}

    def _save_file_summary_vectors(self) -> None:
        try:
            import json as _json
            out = dict(self._file_summary_vectors)
            out["_strategy"] = self._file_summary_strategy
            tmp = self._file_summary_vec_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(out, f, ensure_ascii=False)
            os.replace(tmp, self._file_summary_vec_file())
        except Exception as e:
            logger.debug("file summary vectors save failed: %s", e)

    def _file_doc_scores(self, query: str) -> tuple:
        """query → 文件摘要向量 top-k → {doc: 相似度}。

        返回 ({doc: sim}, 文件层耗时 ms, 文件层命中数)。
        文件摘要向量懒计算（~600 文件, 一次嵌入缓存进 _embeddings）。
        消费方: DM_FILE_BOOST（检索层保底, 已消融否决）与
        DM_FILE_RERANK（重排层加权, 2026-08-14 B 尾巴）。
        """
        t0 = time.time()
        summaries = self._ensure_file_summaries()
        if not summaries:
            return {}, 0.0, 0
        qv = self._embed(query)
        if qv is None:
            return {}, 0.0, 0
        scored = []
        for doc, summary in summaries.items():
            vec = self._file_summary_vectors.get(doc)
            if vec is None:
                vec = self._embed(summary[:1000])
                if vec is None:
                    # 2026-08-14 修复: 嵌入偶发失败不静默跳过 —
                    # 轻量词法兜底（无 jieba 依赖: 中文按 2-gram 字,
                    # ASCII 按词; 交集>0 → 弱命中 0.35）。防文件层
                    # 因 embed 抖动漏文件。
                    if self._lex_overlap(query, summary) > 0:
                        scored.append((0.35, doc))
                    continue
                self._file_summary_vectors[doc] = vec
                # 增量落盘（避免进程中断全丢）
                if len(self._file_summary_vectors) % 100 == 0:
                    self._save_file_summary_vectors()
            sim = self._cosine(qv, vec)
            if sim > 0.3:
                scored.append((sim, doc))
        self._save_file_summary_vectors()
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self._file_summary_top]
        return ({d: s for s, d in top},
                (time.time() - t0) * 1000, len(top))

    @staticmethod
    def _lex_overlap(a: str, b: str) -> int:
        """轻量词法交集: 中文字符二元组 + ASCII 词, 无第三方依赖。"""
        import re

        def _tokens(s: str) -> set:
            out = set()
            cjk = re.findall(r"[\u4e00-\u9fff]", s)
            for i in range(len(cjk) - 1):
                out.add(cjk[i] + cjk[i + 1])
            out.update(re.findall(r"[A-Za-z0-9_]{2,}", s))
            return out

        return len(_tokens(a) & _tokens(b))

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1e-9
        nb = math.sqrt(sum(y * y for y in b)) or 1e-9
        return dot / (na * nb)

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

    def _chat_once(self, prompt: str, max_tokens: int = 300,
                   temperature: float = 0.0) -> Optional[str]:
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
                    temperature=temperature,
                    metadata={"thinking": {"type": "disabled"}}))
                # 兼容两种返回约定（2026-08-16）: GenerateResult（.text）
                # 或纯字符串（_GatewayLLMAdapter 直返文本）。
                resp = (result.text if hasattr(result, "text")
                        else (result if isinstance(result, str) else ""))
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
        prompt = HYDE_PROMPT + query
        resp = self._chat_once(prompt, max_tokens=400)
        if not resp or not resp.strip():
            return None
        return self._embed(resp.strip())

    def _hyde_hypotheses(self, query: str, k: int = 3) -> List[str]:
        """多假设生成（2026-08-16, 泛化性设计）: 同一通用 prompt, K 个
        假设文档, 温度梯度采样（[0.0, 0.5, 0.9]）。单假设（k=1）→ 温度
        0.0 稳定复现; 多假设 → 覆盖不同措辞/侧重, 降低单次幻觉方差。
        部分生成失败 → 返回已成功的子集（RRF 对可用假设融合）。"""
        if k <= 1:
            temps = [0.0]
        else:
            temps = [0.0, 0.5, 0.9][:k]
        out: List[str] = []
        for t in temps:
            resp = self._chat_once(HYDE_PROMPT + query, max_tokens=400,
                                   temperature=t)
            if resp and resp.strip():
                out.append(resp.strip())
        return out

    def _vector_multi_anchors(self, query: str, top_k: int,
                              blocks: Optional[List[dict]],
                              qvecs: List[list]) -> List[RecallHit]:
        """多查询向量 RRF（2026-08-16, RAG-Fusion 形态）:

        原 query 向量 + K 个 HyDE 假设文档向量, 各自 vector 检索 top_k,
        跨查询 RRF 合并 → 作为 vector 路线命中（保持 vector 主导融合,
        不被当独立 "hyde" 源埋掉）。研究依据: HyDE 原论文（2212.10496）
        + RAG-Fusion（多查询生成 + RRF）+ Revisiting Feedback Models
        for HyDE（2511.19349: 朴素拼接非最优, 多信号需正规融合）。
        """
        from collections import defaultdict
        rrf: Dict[str, float] = defaultdict(float)
        by_id: Dict[str, RecallHit] = {}
        for qv in qvecs:
            for rank, h in enumerate(self._vector_anchors(
                    query, top_k, blocks=blocks, query_vec=qv)):
                rrf[h.id] += 1.0 / (60 + rank + 1)
                by_id[h.id] = h
        ordered = sorted(by_id.values(), key=lambda h: rrf[h.id],
                         reverse=True)
        for h in ordered:
            h.score = round(rrf[h.id], 6)
        return ordered[:top_k]

    def _prf_query_vector(self, query: str,
                          blocks: Optional[List[dict]] = None,
                          top_k: Optional[int] = None,
                          alpha: Optional[float] = None) -> Optional[list]:
        """伪相关反馈查询向量（2026-08-16, Rocchio）:

        aug = (1-α)·q_vec + α·mean(bm25 top-k 块向量), 归一化。
        用确定性词法命中的"相关块质心"拉近提问式 query 与陈述式块在
        嵌入空间的距离（BGE-M3 对称嵌入的已知缺陷）。无 bm25 命中/无
        向量 → None（回退原 query）。A18: 参数 α / k 可消融。
        """
        if top_k is None:
            top_k = getattr(self, "prf_fb_blocks", 3)
        if alpha is None:
            alpha = getattr(self, "prf_alpha", 0.5)
        qv = self._embed(query)
        if qv is None:
            return None
        try:
            import numpy as np
            hits = self._bm25_anchors(query, top_k, blocks=blocks)
            vecs = []
            for h in hits[:top_k]:
                v = (self._embeddings.get(h.id)
                     or next((b.get("vector") for b in blocks or []
                              if b["id"] == h.id), None))
                if v is not None and len(v) == len(qv):
                    vecs.append(np.asarray(v, dtype=np.float32))
            if not vecs:
                return None
            centroid = sum(vecs) / len(vecs)
            aug = np.asarray(qv, dtype=np.float32) * (1.0 - alpha) \
                + centroid * alpha
            norm = float(np.linalg.norm(aug))
            return (aug / norm).tolist() if norm else None
        except Exception as e:
            logger.debug("prf query vector failed: %s", e)
            return None

    # ── 混合锚点 ─────────────────────────────────────────────────

    def _vector_anchors(self, query: str, top_k: int,
                        blocks: Optional[List[dict]] = None,
                        query_vec: Optional[list] = None,
                        prf_vec: Optional[list] = None,
                        boost_docs: Optional[set] = None,
                        pool_docs: Optional[set] = None) -> List[RecallHit]:
        """BGE 向量召回（余弦）; BGE 不可用 → ChunkStore 关键词兜底。"""
        _t0 = time.time()
        if blocks is None:
            self._ensure_blocks()
            blocks = self._block_list
        # 查询向量优先级（2026-08-16）: PRF 质心（Rocchio, 词法证据
        # 交叉）> HyDE 假设答案（LLM 域术语）> 原 query 嵌入。
        qv = prf_vec if prf_vec is not None else (
            query_vec if query_vec is not None else self._embed(query))
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
                    # 2026-08-14: coarse 兜底窗口带文件标题（父级上下文,
                    # 与 doc_corpus v4 嵌入同口径）。无 doc_title（对话树
                    # 块/goldset）→ 与原窗口字节级一致, 不引入回归。
                    _doc_t = b.get("doc_title") or ""
                    if _doc_t:
                        coarse = ((f"{_doc_t} | "
                                   f"{b.get('heading') or ''}\n{score_text}")
                                  [:1500])
                    else:
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
                    if row_idx >= len(batch_bids):
                        continue
                    bid = batch_bids[row_idx]
                    b = self._blocks_cache.get(bid)
                    if b is None:
                        b = next((x for x in blocks if x["id"] == bid), None)
                    boosted = (boost_docs and b is not None
                               and b.get("doc") in boost_docs)
                    if boost_docs and b is not None and bid.startswith(
                            "docs/only/G10"):
                        logger.info("G10 boost check: doc=%r in=%s",
                                    b.get("doc")[:40],
                                    b.get("doc") in boost_docs)
                    # 两级检索（2026-08-14, 方案 B+C 合并体）:
                    # 文件层命中的文件 → 其节块直接进候选（即使 sim<0.3
                    # 被阈值滤掉 — Parent-Child 正解: 文件对 → 块可见）。
                    # score = max(原始分, 保底 0.25) + 0.1 boost。
                    if boosted:
                        s = max(s, 0.25) + self._file_boost_factor
                    if s > 0.3 or boosted or (
                            pool_docs and b is not None
                            and b.get("doc") in pool_docs):
                        if b is not None:
                            scored.append((s, b))
            except Exception:
                for b in blocks:
                    ev = self._embeddings.get(b["id"])
                    if ev is None:
                        continue
                    sim = self._cosine(qv, ev)
                    boosted = (boost_docs and b.get("doc") in boost_docs)
                    if boosted:
                        sim = max(sim, 0.25) + self._file_boost_factor
                    if sim > 0.3 or boosted or (
                            pool_docs and b.get("doc") in pool_docs):
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

    def _pool_doc_ratio(self, blocks: Optional[List[dict]]) -> float:
        """域门控判别（2026-08-17）: 池内带 doc 字段（知识文档）的占比。

        实测（HYDE_EVAL）: HyDE 对知识文档池 +3.3pp、对会话池 -7.7pp。
        会话块（对话树/goldset）无 doc 字段, 文档块有 → 用 doc 占比
        判别"知识池 vs 会话池", ≥ 阈值才启用 HyDE（防 dialogue 回归）。
        """
        if not blocks:
            return 0.0
        n = min(len(blocks), 30)
        if n <= 0:
            return 0.0
        return sum(1 for b in blocks[:n] if b.get("doc")) / n

    def _bm25_qids_anchors(self, qids: List[int], top_k: int,
                           blocks: List[dict],
                           idx: dict) -> List[RecallHit]:
        """BM25 打分（共享内核调用）: 给定词项 id 集 → 命中块。"""
        _t0 = time.time()
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

    def _bm25_anchors(self, query: str, top_k: int,
                      blocks: Optional[List[dict]] = None) -> List[RecallHit]:
        """BM25 词法召回（Rust 稀疏内核, Python 回退; 语料真实 df）。

        2026-08-12: 旧实现每 query 对每块重分词打分（文档池 8.6-10s/query）;
        现 = 词项索引（每块分词一次按块集缓存）+ Rust bm25_scores 批量打分。
        """
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
        return self._bm25_qids_anchors(qids, top_k, blocks, idx)

    def _bm25_hyde_anchors(self, query: str, top_k: int,
                           blocks: List[dict],
                           hyps: List[str]) -> List[RecallHit]:
        """HyDE→BM25 词项扩展（2026-08-17, Rocchio 反馈模型近似）:

        假设文档 → 提取 tf×idf 加权扩展词（Rocchio: 词频 × 语料 idf,
        去掉原 query 词）→ 独立 BM25 检索 → 与原 BM25 RRF 融合。
        Rust kernel 不支持词项权重, 用 rank 融合近似加权（论文
        2511.19349: 朴素字符串拼接非最优, 正规反馈模型显著更优）。
        """
        if not hyps or not blocks:
            return []
        try:
            idx = self._bm25_index(blocks)
            term_id = idx["term_id"]
            df_map = dict(idx["df"])
            n_docs = idx["n_docs"]
            # 扩展词质量门（2026-08-17, 冒烟实证）: 假设文档含大量通用
            # 脚手架词（进行/直至/返回/结果/机制/引入...）+ 语料高频词
            # （Tool/Function/Schema 散布于所有工具设计文档）→ 不过滤会
            # 检索到通用工具文档而非期望文档。停用词 + df 占比过滤。
            _stop = {"进行", "直至", "返回", "结果", "机制", "引入", "循环",
                     "拼接", "通过", "我们", "实现", "支持", "用于", "可以",
                     "使用", "需要", "以及", "并且", "这个", "该", "其",
                     "的", "了", "在", "中", "和", "与", "为", "将", "被"}
            orig_tids: set = set()
            for _t in self._bm25_tokenize(query):
                _tid = term_id.get(_t)
                if _tid is not None:
                    orig_tids.add(_tid)
            w: Dict[int, float] = {}
            for h in hyps:
                for t in self._bm25_tokenize(h):
                    tid = term_id.get(t)
                    if tid is None or tid in orig_tids:
                        continue
                    if t in _stop:
                        continue
                    df_t = df_map.get(tid, 0)
                    if n_docs > 0 and df_t / n_docs > 0.25:
                        continue    # 语料 25%+ 块共有 → 区分度低
                    idf = math.log(
                        (n_docs - df_t + 0.5) / (df_t + 0.5) + 1.0)
                    w[tid] = w.get(tid, 0.0) + idf   # tf×idf（token 重复累加）
            if not w:
                return []
            exp_tids = [tid for tid, _ in sorted(
                w.items(), key=lambda x: -x[1])
                [:getattr(self, "hyde_bm25_terms", 15)]]
            if not exp_tids:
                return []
            exp_hits = self._bm25_qids_anchors(exp_tids, top_k, blocks, idx)
            if not exp_hits:
                return []
            orig_hits = self._bm25_anchors(query, top_k, blocks=blocks)
            # RRF 融合（原 query 秩 + 扩展词秩）
            from collections import defaultdict
            rrf: Dict[str, float] = defaultdict(float)
            by_id: Dict[str, RecallHit] = {}
            for rank, h in enumerate(orig_hits, 1):
                rrf[h.id] += 1.0 / (60 + rank)
                by_id[h.id] = h
            for rank, h in enumerate(exp_hits, 1):
                rrf[h.id] += 1.0 / (60 + rank)
                by_id[h.id] = h
            ordered = sorted(by_id.values(),
                             key=lambda h: rrf[h.id], reverse=True)
            for h in ordered:
                h.score = round(rrf[h.id], 6)
            return ordered[:top_k]
        except Exception as e:
            logger.debug("bm25 hyde expansion failed: %s", e)
            return []

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
                resp = (result.text if hasattr(result, "text")
                        else (result if isinstance(result, str) else ""))
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
                resp = (result.text if hasattr(result, "text")
                        else (result if isinstance(result, str) else ""))
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

    def _segment_anchors(self, segments: List[str],
                         top_k: int) -> List[RecallHit]:
        """多意图 segments 消费（2026-08-13, 意图副路径实质化）:

        每个子意图段并行全路召回（vector+bm25+spo, 线程池 I/O 密集）,
        合并去重, 源标记 "segment"（区别于 hyde 的查询扩展 — 这是
        意图拆分的段, 语义权重更高）。失败段记录 miss 不阻塞。
        """
        segs = [s.strip() for s in (segments or []) if s and s.strip()]
        if len(segs) <= 1:
            return []
        seen: set = set()
        hits: List[RecallHit] = []
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

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max(1, pool)) as ex:
                results = list(ex.map(_one, segs))
        except Exception:
            results = [_one(q) for q in segs]
        for q, sub in results:
            if not sub:
                self._decompose_misses.append(
                    {"query": q, "error": "segment empty recall"})
                continue
            for h in sub:
                if h.id in seen:
                    continue
                seen.add(h.id)
                h.source = "segment"
                h.confidence = 0.8
                hits.append(h)
        return hits[: top_k * 2]

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

    def _learned_conf_path(self) -> str:
        import os
        return os.path.join(self._index_dir(), "learned_conf.json")

    def _load_learned_conf(self) -> None:
        """A18 持久化加载: 置信度 + 重排权重覆盖（重启不丢）。"""
        import json as _json
        try:
            with open(self._learned_conf_path(), "r", encoding="utf-8") as f:
                data = _json.load(f)
            conf = data.get("confidence") or {}
            for k, v in conf.items():
                try:
                    self._learned_conf[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            overrides = data.get("rerank_weights") or {}
            for intent, srcs in overrides.items():
                self._weight_overrides[str(intent)] = {
                    str(s): float(w) for s, w in srcs.items()
                    if isinstance(w, (int, float))}
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("learned_conf load failed: %s", e)

    def _save_learned_conf(self) -> None:
        """A18 持久化保存（反馈/调权后调用; 文件小, 直接写）。"""
        import json as _json
        try:
            data = {
                "confidence": dict(self._learned_conf),
                "rerank_weights": {
                    k: v for k, v in self._weight_overrides.items()},
            }
            path = self._learned_conf_path()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=1)
            import os
            os.replace(tmp, path)
        except Exception as e:
            logger.debug("learned_conf save failed: %s", e)

    def _confidence(self, source: str,
                    intent: Optional[str] = None) -> float:
        """读取可学习置信度（默认表, 被 feedback 调整后覆盖）。

        W1 后半（2026-08-13）: 意图感知 — 优先读 per-intent 置信度
        （"意图:来源" 键）; 无则回退全局（旧行为）。A18 参数白盒:
        weights(intent=) 可单独查看/调节每个意图的配置。"""
        key = f"{intent}:{source}" if intent else source
        return self._learned_conf.get(
            key, self._learned_conf.get(source, SOURCE_CONFIDENCE[source]))

    def feedback(self, hit_id: str, useful: bool, note: str = "",
                 intent: Optional[str] = None) -> dict:
        """A6 后验反馈: ε 步长调整来源置信度（GAP-D4 update_source_credibility 落地）。

        2026-08-13（W1 后半）: 带 intent 时只调该意图的置信度
        （"意图:来源"）, 不影响其他意图; 不带 intent = 全局调整（旧行为）。
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
        conf = self._confidence(base_source, intent)
        new_conf = max(0.1, min(1.0, conf + (EPSILON if useful else -EPSILON)))
        key = f"{intent}:{base_source}" if intent else base_source
        self._learned_conf[key] = new_conf
        self._feedback_log.append({
            "ts": time.time(), "hit_id": hit_id, "source": base_source,
            "intent": intent, "useful": useful, "before": round(conf, 4),
            "after": round(new_conf, 4), "note": note,
        })
        self._save_learned_conf()
        return {
            "ok": True, "source": base_source,
            "intent": intent,
            "before": round(conf, 4), "after": round(new_conf, 4),
        }

    def weights(self, intent: Optional[str] = None) -> dict:
        """A18 参数白盒: 当前各源置信度（可调节）。

        intent 指定时返回该意图的权重视图（含重排权重 + 置信度）;
        不带 intent 返回全局置信度（旧行为）。"""
        base = {k: round(self._confidence(k), 4) for k in SOURCE_CONFIDENCE}
        if not intent:
            return base
        profile = INTENT_PROFILES.get(normalize_intent(intent)) or {}
        weights = dict(profile.get("weights") or RERANK_WEIGHTS)
        # 白盒覆盖（set_weight 写入的 rerank 权重优先）
        for src, w in (self._weight_overrides.get(intent) or {}).items():
            weights[src] = w
        return {
            "confidence": {
                k: round(self._confidence(k, intent), 4)
                for k in SOURCE_CONFIDENCE},
            "rerank": {k: round(v, 4) for k, v in weights.items()},
            "fuse_mode": profile.get("fuse_mode") or self.fuse_mode,
        }

    def set_weight(self, source: str, value: float,
                   intent: Optional[str] = None,
                   target: str = "confidence") -> dict:
        """A18 用户感知调节: 显式覆盖置信度或重排权重（clamp 0-1）。

        target="confidence": 源置信度（全局或 per-intent）;
        target="rerank": 重排权重（per-intent, 影响 _rerank 加权）。
        均持久化（learned_conf.json）, 重启不丢。
        """
        value = max(0.0, min(1.0, float(value)))
        if target == "rerank":
            if intent not in INTENT_PROFILES:
                return {"ok": False,
                        "error": f"unknown intent: {intent} "
                                 f"(rerank 权重需指定已定义意图)"}
            profile = INTENT_PROFILES[intent]
            if source not in profile.get("weights", {}):
                return {"ok": False,
                        "error": f"unknown rerank source: {source} "
                                 f"for intent {intent}"}
            over = self._weight_overrides.setdefault(intent, {})
            over[source] = value
            self._save_learned_conf()
            return {"ok": True, "target": "rerank", "intent": intent,
                    "source": source, "weight": round(value, 4)}
        if source not in SOURCE_CONFIDENCE:
            return {"ok": False, "error": f"unknown source: {source}"}
        key = f"{intent}:{source}" if intent else source
        self._learned_conf[key] = max(0.1, value)
        self._save_learned_conf()
        return {"ok": True, "source": source,
                "intent": intent,
                "confidence": round(self._learned_conf[key], 4)}

    # ── 主入口 ─────────────────────────────────────────────────

    # ── W3: recall 本体图扩展（内容边, 2026-08-13） ─────────────

    def _graph_anchors(self, query: str, top_k: int) -> List[RecallHit]:
        """内容边图扩展: ConceptGraph 对 query 做局部图检索
        （compile_context = 实体定位 + 边优先级扩散, 有向/无环, 预算限定）。

        定位（W3 验收）: recall() 本体可扩展图 — 树空/块空时也能从
        持久化图抓相关内容（用户: "就算树空的，子图扩展也能去持久化
        里面抓吧？"）; 节点 metadata.doc → path, 执行层 file_read
        精确查阅全文（粗召回只给定位, 不塞大段原文）。
        无 engine / 无图 → []（评测 bench 不受影响, 确定性保持）。
        """
        if self._engine is None or not query or not query.strip():
            return []
        graph = None
        ci = getattr(self._engine, "_content_index", None)
        if ci is not None and hasattr(ci, "_graph"):
            graph = ci._graph
        if graph is None:
            graph = getattr(self._engine, "_graph", None)
        if graph is None or not hasattr(graph, "compile_context"):
            return []
        try:
            items = graph.compile_context(
                query, top_k=top_k, max_hops=2, max_nodes=max(12, top_k * 4))
            out: List[RecallHit] = []
            for i, item in enumerate(items):
                text = getattr(item, "text", "") or ""
                if not text.strip():
                    continue
                path = []
                for dp in (item.metadata or {}).get("doc", []) or []:
                    if dp:
                        path.append(str(dp))
                rel = float(getattr(item, "relevance", 0.5) or 0.5)
                out.append(RecallHit(
                    id=f"graph:{i}:{hash(text) & 0xffffffff:08x}",
                    text=text[:200], source="graph",
                    score=min(1.0, 0.3 + rel / 2),
                    confidence=self._confidence("graph"),
                    path=path,
                ))
            logger.info("graph_anchors: %d items (query=%.40s)",
                        len(out), query)
            return out[:top_k]
        except Exception as e:
            logger.debug("graph anchors failed: %s", e)
            return []

    # ── 重排层（2026-08-13, P1: doc top1 31%→40%+ 的施工面） ─────

    def _rerank(self, hits: List[RecallHit],
                intent: Optional[str] = None,
                file_sims: Optional[dict] = None) -> List[RecallHit]:
        """候选生成（粗序）→ 特征重排: 每源分数按候选集内源 max 归一
        （跨源尺度无关: vector 余弦 0.3-1.0 / bm25 已归一到 0-1 /
        spo 0-1）, 按意图权重加权; 源缺失不惩罚（只对存在的源求和）。

        A18 白盒: 权重 = 意图 profile.weights（feedback(intent=) 可调
        置信度, 权重表静态）; 平局按原序 → 确定性双跑一致。
        """
        profile = INTENT_PROFILES.get(normalize_intent(intent)) or {}
        w = dict(profile.get("weights") or RERANK_WEIGHTS)
        # A18 白盒覆盖（set_weight(target="rerank") 持久化的权重优先）
        for src, wv in (self._weight_overrides.get(intent) or {}).items():
            w[src] = wv
        cap = max(12, min(60, len(hits)))
        cands = hits[:cap]
        tail = hits[cap:]
        src_max: Dict[str, float] = {}
        for h in cands:
            for src, s in h.scores.items():
                base = src.split(":", 1)[-1]
                if s > src_max.get(base, 0.0):
                    src_max[base] = s
        order = {id(h): i for i, h in enumerate(cands)}
        for h in cands:
            feat = 0.0
            for src, s in h.scores.items():
                m = src_max.get(src.split(":", 1)[-1]) or 0.0
                if m > 0:
                    feat += w.get(src.split(":", 1)[-1], 0.1) * (s / m)
            # 文件层信号进重排（2026-08-14, B 尾巴）: 文件摘要命中 →
            # 该文件节块加权（乘文件摘要相似度, 不保底不全局抬）。
            # 与 DM_FILE_BOOST 正交（一个动检索层, 一个动重排层）。
            if file_sims and h.path:
                s_f = file_sims.get(h.path[0])
                if s_f:
                    feat += self._file_rerank_weight * s_f
            # 源独有保底（2026-08-14）: 纯非 vector 命中（该块只有
            # bm25/spo 等独有证据）→ 贡献 ×boost — 防"源的 top-1 被
            # 向量长尾埋掉"。通用规则, 非意图特调; 闲聊类不走重排
            # 天然不生效。
            if (getattr(self, "source_guarantee", False)
                    and "vector" not in h.scores
                    and h.scores):
                feat *= getattr(self, "guarantee_boost", 1.5)
            # 强独有信号保底 v2（2026-08-16, DM_ROUTE_UNIQUE）:
            # 无 vector 证据 + bm25/spo 源内强分（≥ 阈值）→ 该块只被
            # 确定性信号命中且很强（q002/q052 bm25 score=1.0）→ 上浮。
            # 与旧 source_guarantee 区别: 只对"强分独有"生效, 不抬噪声
            # 长尾; 且加性（不乘）, 不与其它源分数叠加失控。
            if (getattr(self, "route_unique", False)
                    and "vector" not in h.scores and h.scores):
                route_vals = [v for k, v in h.scores.items()
                              if k.split(":", 1)[-1]
                              in ("bm25", "spo", "hyde")]
                best_route = max(route_vals, default=0.0)
                if best_route >= getattr(self, "route_unique_threshold", 0.8):
                    feat += 0.5 * best_route
            h.rerank_score = round(feat, 6)
        cands.sort(key=lambda h: (-h.rerank_score, order[id(h)]))
        return cands + tail

    def recall(
        self,
        query: str,
        intent: Optional[str] = None,
        top_k: int = 10,
        sid: Optional[str] = None,
        use_hyde: bool = True,
        expand_graph: Optional[bool] = None,
        sub_queries: Optional[List[str]] = None,
    ) -> RecallResult:
        t0 = time.time()
        self._last_sid = sid
        intent_n = normalize_intent(intent)
        profile = INTENT_PROFILES.get(intent_n) or {}
        # 意图感知融合模式（W1 后半）: profile.fuse_mode 优先; 显式 env
        # DM_FUSION 仍可覆盖（消融开关, 与 __init__ 一致）。
        fuse_mode = self.fuse_mode
        if profile.get("fuse_mode") and not os.environ.get("DM_FUSION", ""):
            fuse_mode = profile["fuse_mode"]
        # 意图感知 HyDE / 扩散深度 / 图扩展
        if profile.get("hyde") is not None:
            use_hyde = use_hyde and bool(profile["hyde"])
        diffuse_k = int(profile.get("diffuse_k") or 2)
        if expand_graph is None:
            expand_graph = bool(profile.get("graph", False))
        hot_blocks = self._ensure_blocks(sid)
        cold_blocks = self._ensure_global_blocks()
        # 域门控（2026-08-17, HYDE_EVAL 实测驱动）: 域由主池（hot）类型
        # 决定 — 会话域（hot 非文档）完全禁用 HyDE（含 cold 注入）; 知识
        # 文档域（hot 是文档）启用。实测 dialogue 的污染来自"会话 query +
        # cold 文档池被 HyDE"（run2 76.9% vs run3 74.4% 的非确定差异）。
        _hot_is_doc = self._pool_doc_ratio(hot_blocks) >= 0.8
        if (use_hyde and getattr(self, "hyde_decompose", True)):
            if getattr(self, "parallel_decompose", False):
                expanded = self._expand_questions(query)
            else:
                expanded = self._expand_questions_legacy(query)
        else:
            expanded = [query]
        hits: List[RecallHit] = []
        single = getattr(self, "single_source", None)
        # 真 HyDE（2026-08-16 泛化性设计, 默认 DM_HYDE=1）:
        #   K=1（默认）: 单假设文档嵌入作 query_vec（既有行为不变）;
        #   K>1: 多假设文档各自检索 + RRF 合并 → "hyde" 独立路线进融合
        #     （RAG-Fusion 形态, 不替换原 query 向量）;
        #   DM_HYDE_GATE=1: 向量 top-1 ≥ 阈值 → 跳过 HyDE（防假设文档
        #     漂移破坏高置信 query）。无 LLM 自动跳过。
        hyde_vec = None
        hyde_qvecs: Optional[List[list]] = None
        hyde_hyp_texts: List[str] = []
        # 2026-08-16 评测实锤: HyDE（K=1 替换向量 / K=3 RAG-Fusion）在本
        # 项目自指语料上净负（doc 54.1→41.0 / 54.1, dialogue 76.9→69.2,
        # 见 RECALL_FUSION_ABLATION §六 / HYDE_EVAL 记录）— 假设文档无法
        # 复现内部精确词汇。默认关闭（DM_HYDE=0）, 开关保留做实验。
        if (_hot_is_doc
                and os.environ.get("DM_HYDE", "0") == "1"
                and self._llm is not None):
            _k = max(1, int(getattr(self, "hyde_k", 1) or 1))
            _gate = getattr(self, "hyde_gate", False)
            _enabled = True
            if _gate:
                _pre = self._vector_anchors(
                    query, 1, blocks=hot_blocks or cold_blocks)
                _enabled = (not _pre) or (
                    _pre[0].score < getattr(
                        self, "hyde_gate_threshold", 0.70))
            if _enabled:
                if _k > 1:
                    # RAG-Fusion 形态: 原 query + K 假设文档向量 → vector
                    # 路线多查询 RRF（合入 vector 源, 不被当独立源埋掉）。
                    hyps = self._hyde_hypotheses(query, _k)
                    hyde_hyp_texts = hyps
                    _qv = self._embed(query)
                    _hvs = [hv for hv in
                            (self._embed(t) for t in hyps) if hv]
                    if _qv and _hvs:
                        hyde_qvecs = [_qv] + _hvs
                else:
                    hyde_vec = self._hyde_query_vector(query)
        # 两级检索（2026-08-14, 方案 B+C 合并体）: 文件层定位 →
        # 命中文件的节块 boost。只对冷池（doc 语料）生效; 监控耗时。
        file_boost_ms = 0.0
        files_hit: set = set()
        file_sims: dict = {}
        if single is None and cold_blocks and (
                getattr(self, "_file_summary_boost", False)
                or getattr(self, "_file_rerank", False)
                or getattr(self, "_file_pool", False)):
            file_sims, file_boost_ms, _ = self._file_doc_scores(query)
            files_hit = set(file_sims)

        def _run(blocks, tag):
            out = []
            # 伪相关反馈（2026-08-16, DM_PRF）: bm25 命中块质心扩展
            # query 向量 → vector 路。只影响向量检索, 与 bm25/spo 路
            # 正交（质心来自 bm25, 喂回 vector — 两信号交叉, A25）。
            _pv = None
            if getattr(self, "prf", False):
                _pv = self._prf_query_vector(query, blocks=blocks)
            # 域门控（2026-08-17, HYDE_EVAL 实测驱动）: HyDE 只对知识
            # 文档池（doc 占比 ≥ 0.8）生效 — 会话池原样。实测 doc +3.3pp
            # / dialogue -7.7pp 的不对称正来自池类型; 会话块无 doc 字段。
            _doc_pool = self._pool_doc_ratio(blocks) >= 0.8
            if single in (None, "vector"):
                if hyde_qvecs is not None and _doc_pool:
                    # RAG-Fusion 多查询向量（2026-08-16）: 原 query + K 假设
                    # 文档各自检索 + RRF 合并, 产出仍为 vector 源命中。
                    out += self._vector_multi_anchors(
                        query, top_k, blocks=blocks, qvecs=hyde_qvecs)
                else:
                    out += self._vector_anchors(
                        query, top_k, blocks=blocks,
                        query_vec=hyde_vec if _doc_pool else None,
                        prf_vec=_pv,
                        boost_docs=files_hit if tag == "cold" else None)
            if single in (None, "bm25"):
                if (hyde_hyp_texts and getattr(self, "hyde_bm25", True)
                        and _doc_pool):
                    # HyDE→BM25 词项扩展（2026-08-17）: 假设文档扩展词
                    # BM25 + 原 BM25 RRF（Rocchio 近似, 论文 2511.19349）。
                    out += self._bm25_hyde_anchors(
                        query, top_k, blocks, hyde_hyp_texts)
                else:
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
        # 多意图 segments 消费（2026-08-13）: 意图拆分的子段并行全路召回,
        # 与 hyde 查询扩展互补（段 = 独立意图, 语义权重更高）
        if single is None and sub_queries:
            hits += self._segment_anchors(sub_queries, top_k)
        # 扩散（在锚点基础上, 意图感知深度）
        anchor_ids = {h.id for h in hits}
        if single is None:
            hits += self._diffuse(hits, k=diffuse_k)
        # W3: recall 本体图扩展（内容边, 树空也可从持久化图抓）
        if single is None and expand_graph and self._engine is not None:
            hits += self._graph_anchors(query, top_k)
        # 每源原始分收集（重排特征, 跨源合并时保留所有源分数）
        score_index: Dict[str, Dict[str, float]] = {}
        for h in hits:
            base = h.source.split(":", 1)[-1]
            d = score_index.setdefault(h.id, {})
            if base not in d or h.score > d[base]:
                d[base] = h.score
        # 融合排序 + 去重
        best: Dict[str, RecallHit] = {}
        if fuse_mode == "rrf":
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
                    w = self._confidence(src.split(":", 1)[-1], intent_n)
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
        elif fuse_mode == "vector_primary":
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
        # 重排层（2026-08-13, P1）: 粗序 → 特征重排（意图权重）。
        # DM_RERANK=0 关闭（消融对比）。默认开。
        for h in ordered:
            h.scores.update(score_index.get(h.id, {}))
        # 父块上下文（2026-08-14, 方案 B）: doc 块命中附文件摘要 —
        # LLM/执行层拿到"文件级语义", 不只有 160 字节块片段
        summaries = self._ensure_file_summaries()
        for h in ordered:
            if not h.parent_context and summaries:
                doc = next((p for p in (h.path or [])
                            if p in summaries), None)
                if doc:
                    h.parent_context = summaries[doc][:200]
        if (getattr(self, "rerank", True)
                and bool(profile.get("rerank", True))
                and os.environ.get("DM_RERANK", "1") != "0"
                and len(ordered) > 1):
            # 向量置信门控（2026-08-16, DM_VEC_GATE）: vector top-1 分
            # 高 → 向量可靠, 跳过重排防稀释（A 类 7 条 vec=1→fused>1 的
            # 根因是重排归一化让多源弱块压过强纯 vector 块）。
            _vec_top = max(
                (h.scores.get("vector", 0.0) for h in ordered), default=0.0)
            _skip = (getattr(self, "vector_gate", False)
                     and _vec_top >= getattr(
                         self, "vector_gate_threshold", 0.70))
            if not _skip:
                ordered = self._rerank(ordered, intent_n, file_sims)
        # 2026-08-15 加固（P9/A7 细节保留）: 全文回填 — 锚点展示仍用
        # text[:200], 但 hit 携带全文供生成上下文/子图/执行层取用。
        # 此前 7 条召回路径全部 [:200] 截断, "低概率高价值原样保留"
        # 只存在于设计, 未进实现（llm_reply 上下文被摘要压扁 → 幻觉）。
        for h in ordered:
            if h.full_text:
                continue
            b = (self._blocks_cache.get(h.id)
                 or next((x for x in cold_blocks if x["id"] == h.id), None))
            if b is not None:
                h.full_text = b.get("text") or ""
        # C 最小版候选池扩展（2026-08-14, DM_FILE_POOL=1）: 文件命中
        # 文件的节块按自然分进 pool_extras（不抬排序, 只扩候选）—
        # 给子图编译更多锚点/合并材料。消融结论: 文件层信号抬排名必输,
        # 价值在召回扩展。
        pool_extras: List[RecallHit] = []
        if (getattr(self, "_file_pool", False) and file_sims
                and cold_blocks):
            try:
                pool_blocks = [b for b in cold_blocks
                               if b.get("doc") in file_sims]
                ph = self._vector_anchors(
                    query,
                    top_k=self._file_pool_per_doc * max(len(file_sims), 1),
                    blocks=pool_blocks, pool_docs=set(file_sims))
                existing = {h.id for h in ordered}
                for h in ph:
                    if h.id in existing:
                        continue
                    h.source = "cold:pool"
                    b = next((x for x in pool_blocks if x["id"] == h.id), None)
                    if b is not None:
                        h.full_text = b.get("text") or ""
                    if not h.parent_context:
                        doc = h.path[0] if h.path else None
                        if doc and doc in summaries:
                            h.parent_context = summaries[doc][:200]
                    pool_extras.append(h)
                    if len(pool_extras) >= (
                            self._file_pool_per_doc * max(len(file_sims), 1)):
                        break
            except Exception as e:
                logger.debug("pool extras failed: %s", e)
        result = RecallResult(
            query=query,
            hits=ordered[:top_k],
            expanded_queries=expanded,
            latency_ms=(time.time() - t0) * 1000,
            file_boost_ms=round(file_boost_ms, 2),
            files_hit=len(files_hit),
            pool_extras=pool_extras,
        )
        self._last_result = result
        return result
