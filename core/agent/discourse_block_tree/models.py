# core/agent/discourse_block_tree/models.py
"""DiscourseBlock Tree 核心数据模型。

定义 EDU（基本话语单元）、DiscourseBlock（话语块）、Entity（实体）、
ProgressiveSummary（渐进式摘要）等数据类，作为整个系统的统一数据契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ── 枚举类型 ──────────────────────────────────────────────────────
class EDUType(str, Enum):
    """EDU 类型。"""
    STATEMENT = "statement"      # 陈述
    QUESTION = "question"        # 疑问
    COMMAND = "command"          # 命令/指令
    META = "meta"                # 元指令（对话控制）


class BlockState(str, Enum):
    """话语块生命周期状态。"""
    ACTIVE = "active"            # 活跃（最近 5 轮内）
    COOLING = "cooling"          # 冷却（5-10 轮）
    COLD = "cold"                # 冷（> 10 轮）
    MERGED = "merged"            # 已合并


class BoundaryType(str, Enum):
    """切分边界类型。"""
    COHESION_CLIFF = "cohesion_cliff"       # 粘合度悬崖
    BDI = "bdi"                              # 突发意图漂移
    MANUAL = "manual"                        # 手动标记
    LLM = "llm"                              # LLM 辅助标记


# ── 微观维度 (μ1-μ5) ────────────────────────────────────────────
@dataclass
class MicroDimensions:
    """微观粘合度维度。

    权重: μ1=0.30, μ2=0.25, μ3=0.20, μ4=0.15, μ5=0.10
    """
    μ1: float = 0.0    # 实体重叠（实体是否重复/指代）
    μ2: float = 0.0    # 因果链标记（因为/所以/如果/导致）
    μ3: float = 0.0    # 指代消解密度（代词、省略补全数量）
    μ4: float = 0.0    # 时态连贯性（时间副词一致性）
    μ5: float = 0.0    # 语态对齐（主语/动作连贯性）

    # 权重常量
    WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

    def composite(self) -> float:
        """计算微观加权总分。"""
        return (self.μ1 * 0.30 + self.μ2 * 0.25 + self.μ3 * 0.20 +
                self.μ4 * 0.15 + self.μ5 * 0.10)

    def to_dict(self) -> Dict[str, float]:
        return {
            "μ1_entity_overlap": self.μ1,
            "μ2_causal_chain": self.μ2,
            "μ3_reference_resolution": self.μ3,
            "μ4_tense_coherence": self.μ4,
            "μ5_voice_alignment": self.μ5,
            "composite": self.composite(),
        }


# ── 宏观维度 (M1-M4) ────────────────────────────────────────────
@dataclass
class MacroDimensions:
    """宏观话语凝聚力维度。

    权重: M1=0.35, M2=0.25, M3=0.20, M4=0.20
    """
    M1: float = 0.0    # 语义相似度（embedding 余弦）
    M2: float = 0.0    # 意图一致性（相同意图标签）
    M3: float = 0.0    # 实体重叠（实体集合 Jaccard）
    M4: float = 0.0    # 时间窗口内聚（相邻时间衰减）

    # 权重常量
    WEIGHTS = [0.35, 0.25, 0.20, 0.20]

    def composite(self) -> float:
        """计算宏观加权总分。"""
        return (self.M1 * 0.35 + self.M2 * 0.25 + self.M3 * 0.20 +
                self.M4 * 0.20)

    def to_dict(self) -> Dict[str, float]:
        return {
            "M1_semantic_similarity": self.M1,
            "M2_intent_consistency": self.M2,
            "M3_entity_overlap": self.M3,
            "M4_temporal_coherence": self.M4,
            "composite": self.composite(),
        }


# ── 基本话语单元 (EDU) ──────────────────────────────────────────
@dataclass
class EDU:
    """基本话语单元（Elementary Discourse Unit）。

    Stage 2 (SyntacticDecomposer) 输出：一个子句对应一个 EDU。
    Stage 3 (MacroMicroQuantizer) 填充：embedding、维度评分。
    """
    id: str                          # 全局唯一 ID（如 "edu:T3:U1"）
    turn_index: int                  # 所属轮次索引
    edu_index: int                   # 轮内 EDU 索引（0-based）
    raw_text: str                    # 原始文本（Stage 1 补全后）

    # 语法成分（Stage 2 填充）
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    subject_attrs: List[str] = field(default_factory=list)
    object_attrs: List[str] = field(default_factory=list)
    negation: bool = False
    uncertainty: bool = False
    imperative: bool = False
    question: bool = False
    raw_entities: List[str] = field(default_factory=list)
    parse_failed: bool = False
    parse_failed_reason: str = ""

    # 语义特征（Stage 3 填充）
    embedding: Optional[List[float]] = None       # 语义向量
    intent_label: Optional[str] = None            # 意图标签（如 "analyze"、"question"）
    micro_dimensions: Optional[MicroDimensions] = None  # 微观维度
    macro_dimensions: Optional[MacroDimensions] = None  # 宏观维度
    
    # 时间戳
    timestamp: Optional[float] = None             # 创建时间（epoch）

    # 切分标记
    boundary_type: Optional[BoundaryType] = None  # 如果该 EDU 是切分边界，标记类型

    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()

    @property
    def is_boundary(self) -> bool:
        """该 EDU 是否是一个话语块的边界。"""
        return self.boundary_type is not None

    @property
    def compact(self) -> str:
        """压缩表示。"""
        attrs = f"[NOT]" if self.negation else ""
        return f"({attrs}{self.subject}) {self.predicate} ({self.object})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "turn_index": self.turn_index,
            "edu_index": self.edu_index,
            "raw_text": self.raw_text,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "negation": self.negation,
            "imperative": self.imperative,
            "question": self.question,
            "intent_label": self.intent_label,
            "parse_failed": self.parse_failed,
            "boundary_type": self.boundary_type.value if self.boundary_type else None,
            "micro_composite": self.micro_dimensions.composite() if self.micro_dimensions else None,
            "macro_composite": self.macro_dimensions.composite() if self.macro_dimensions else None,
        }


# ── 渐进式摘要 ────────────────────────────────────────────────────
@dataclass
class ProgressiveSummary:
    """渐进式摘要（v1-v3）。

    v1: 单轮摘要（逐轮压缩）
    v2: 块内摘要（跨轮次合并）
    v3: 演化摘要（主题级高阶压缩，跨块触发）
    """
    v1: Optional[str] = None           # 单轮压缩（保留主谓宾 + 关键属性）
    v2: Optional[str] = None           # 块内合并（包含 3 个 top 实体 + 意图）
    v3: Optional[str] = None           # 演化摘要（LLM 压缩，仅在触发时生成）
    
    v1_timestamp: Optional[float] = None
    v2_timestamp: Optional[float] = None
    v3_timestamp: Optional[float] = None
    
    v3_trigger_reason: Optional[str] = None  # "turn_count>5" | "hot_block_lost" | ...

    def __post_init__(self):
        import time
        if self.v1 and self.v1_timestamp is None:
            self.v1_timestamp = time.time()
        if self.v2 and self.v2_timestamp is None:
            self.v2_timestamp = time.time()
        if self.v3 and self.v3_timestamp is None:
            self.v3_timestamp = time.time()

    @property
    def latest(self) -> Optional[str]:
        """返回最新可用的摘要。"""
        if self.v3:
            return self.v3
        if self.v2:
            return self.v2
        return self.v1

    @property
    def latest_level(self) -> int:
        """返回最新摘要的级别（1/2/3）。"""
        if self.v3:
            return 3
        if self.v2:
            return 2
        if self.v1:
            return 1
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "v1": self.v1,
            "v2": self.v2,
            "v3": self.v3,
            "latest": self.latest,
            "latest_level": self.latest_level,
        }


# ── 实体记录 ──────────────────────────────────────────────────────
@dataclass
class Entity:
    """话语块内提取的实体记录。"""
    name: str                    # 实体名称
    type: str                    # 类型：tool / concept / address / person / ...
    first_appearance: int        # 首次出现轮次
    last_appearance: int           # 最后出现轮次
    mention_count: int = 1       # 提及次数
    attributes: List[str] = field(default_factory=list)  # 属性标签（如 "NEG", "UNSAFE"）
    
    # 与头文件注入的关联
    resolved_by: Optional[str] = None  # "header_injector" / "kb" / "context"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "first_appearance": self.first_appearance,
            "last_appearance": self.last_appearance,
            "mention_count": self.mention_count,
            "attributes": self.attributes,
            "resolved_by": self.resolved_by,
        }


# ── 话语块 (DiscourseBlock) ───────────────────────────────────────
@dataclass
class DiscourseBlock:
    """话语块：一个或多个 EDU 的聚合。

    对应一个用户关注话题（子主题），是树中最小可寻址单元。
    """
    id: str                          # 全局唯一 ID（如 "block:T3:1"）
    
    # 组成
    edus: List[EDU] = field(default_factory=list)    # 按时间顺序排列
    
    # 元数据
    start_turn: int = 0              # 起始轮次
    end_turn: int = 0                # 结束轮次（含）
    state: BlockState = BlockState.ACTIVE
    
    # 摘要
    summary: Optional[ProgressiveSummary] = None
    
    # 实体签名
    entities: List[Entity] = field(default_factory=list)   # 去重实体列表
    entity_signature: str = ""       # 序列化实体签名（如 "Python [NEG]unsafe"）
    
    # 宏观特征（由 Segmenter 在切分时计算）
    macro_embedding: Optional[List[float]] = None   # 块级平均 embedding
    intent_label: Optional[str] = None            # 主导意图
    
    # 上下文构建（由 ContextBuilder 计算）
    cohesion_boundary: Optional[float] = None     # 与后继块的粘合度悬崖值
    
    # 树结构（由 Manager 管理）
    parent_id: Optional[str] = None              # 父块 ID（话题树节点）
    node_id: Optional[str] = None                # 在 TopicTree 中的节点 ID
    
    @property
    def turn_count(self) -> int:
        """块覆盖的轮次数。"""
        return self.end_turn - self.start_turn + 1

    @property
    def edu_count(self) -> int:
        """块内 EDU 数量。"""
        return len(self.edus)

    @property
    def text(self) -> str:
        """块内所有 EDU 原始文本拼接。"""
        return "\n".join(e.raw_text for e in self.edus)

    @property
    def latest_summary(self) -> Optional[str]:
        """返回最新可用摘要。"""
        if self.summary:
            return self.summary.latest
        return None

    @property
    def is_hot(self) -> bool:
        """是否为 Hot 块（最近 5 轮活跃）。"""
        return self.state == BlockState.ACTIVE

    @property
    def is_warm(self) -> bool:
        """是否为 Warm 块（5-10 轮）。"""
        return self.state == BlockState.COOLING

    @property
    def is_cold(self) -> bool:
        """是否为 Cold 块（> 10 轮）。"""
        return self.state == BlockState.COLD

    def add_edu(self, edu: EDU):
        """添加 EDU 到块。"""
        self.edus.append(edu)
        self.end_turn = max(self.end_turn, edu.turn_index)
        
        # 更新实体签名
        self._update_entity_signature()
    
    def _update_entity_signature(self):
        """基于 EDU 实体重新计算实体签名。"""
        all_entities = []
        for edu in self.edus:
            all_entities.extend(edu.raw_entities)
        seen = set()
        deduped = []
        for e in all_entities:
            if e not in seen:
                seen.add(e)
                deduped.append(e)
        self.entity_signature = " ".join(deduped) if deduped else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start_turn": self.start_turn,
            "end_turn": self.end_turn,
            "turn_count": self.turn_count,
            "edu_count": self.edu_count,
            "state": self.state.value,
            "latest_summary": self.latest_summary,
            "entity_signature": self.entity_signature,
            "intent_label": self.intent_label,
            "cohesion_boundary": self.cohesion_boundary,
        }

    def to_detailed_dict(self) -> Dict[str, Any]:
        """完整序列化（包含所有 EDU 和实体）。"""
        d = self.to_dict()
        d["edus"] = [e.to_dict() for e in self.edus]
        d["entities"] = [e.to_dict() for e in self.entities]
        d["summary"] = self.summary.to_dict() if self.summary else None
        return d
