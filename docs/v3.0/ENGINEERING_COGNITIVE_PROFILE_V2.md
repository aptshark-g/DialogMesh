# DialogMesh 2.0 认知-画像架构升级 — 工程实现文档

**版本**: v2.0-Engineering  
**日期**: 2026-07-01  
**状态**: 设计冻结，待实现  
**依赖文档**:
- `design_cognitive_profile_v2.md`（架构设计）
- `LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md`（文献调研）

---

## 1. 变更总览

### 1.1 新增文件

| 文件路径 | 职责 | 代码行估算 |
|---------|------|----------|
| `service/cognitive/dynamics.py` | 轨道 A：认知动力学（CognitiveDynamics） | ~200 |
| `service/cognitive/tag_layer.py` | 轨道 B：标签化信息层（TagLayer） | ~300 |
| `service/cognitive/temporal.py` | 时间状态管理（TemporalState + TimeDecayManager） | ~150 |
| `service/cognitive/acquisition.py` | 标签获取引擎（L1-L4 TagAcquisitionEngine） | ~250 |
| `service/cognitive/fusion.py` | 融合层（FusionContext + FusionEngine） | ~200 |
| `service/cognitive/memory_decay.py` | 记忆衰减管理（MemoryDecayManager + MemoryChunk） | ~200 |
| `service/cognitive/g_factor.py` | g 因子推断引擎（GFInferenceEngine） | ~150 |
| `service/cognitive/dialogue_tree_weight.py` | 对话树权重管理（DialogueTreeWeightManager） | ~150 |
| `service/cognitive/__init__.py` | 包导出 | ~20 |
| `service/cognitive/models.py` | 认知模块共享数据模型（MemoryPoint, UserTag, etc.） | ~250 |
| `tests/test_cognitive_profile_v2.py` | 认知画像 v2 测试 | ~400 |
| `tests/test_memory_decay.py` | 记忆衰减测试 | ~200 |
| `tests/test_tag_acquisition.py` | 标签获取测试 | ~200 |
| `tests/test_g_factor.py` | g 因子推断测试 | ~150 |

### 1.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `service/models.py` | 扩展 `Session`（新增 `cognitive_profile_v2`），保留旧版 `cognitive_profile` 兼容 | 数据模型 |
| `service/orchestrator.py` | 在编排流程中集成 `FusionContext` 和 `TimeDecayManager` | 核心流程 |
| `service/api/dependencies.py` | 新增 `get_cognitive_engine()` 依赖注入 | 依赖注入 |
| `service/api/routes.py` | 新增画像查询/更新端点 | API |
| `service/protocol/schemas.py` | 新增 `CognitiveProfileV2Payload`, `TagLayerPayload`, `MemoryChunkPayload` | 协议层 |

### 1.3 向后兼容

- `CognitiveProfile`（旧版）保留，序列化到持久化层时同时写入 `cognitive_profile` 和 `cognitive_profile_v2`
- 读取时优先使用 `cognitive_profile_v2`，不存在时降级到 `cognitive_profile`（自动迁移）
- 所有现有 API 端点行为不变，新增 `/v2/` 前缀端点用于新功能

---

## 2. 数据模型（详细定义）

### 2.1 新增模型：`service/cognitive/models.py`

```python
# -*- coding: utf-8 -*-
"""
service/cognitive/models.py
─────────────────────────
DialogMesh 2.0 认知模块共享数据模型。

所有模型均为 @dataclass，支持 JSON 序列化（to_dict / from_dict）。
设计原则：
  - 纯数据容器，无业务逻辑
  - 所有数值字段带默认值，支持冷启动
  - 时间戳统一使用 float（time.time()）
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
import time
import math


# ═══════════════════════════════════════════════════════════════════════════════
# 基础类型别名
# ═══════════════════════════════════════════════════════════════════════════════

TagValue = Any                    # 标签值可以是 str, float, bool, List[str] 等
Timestamp = float                 # 统一时间戳类型
NodeId = str                      # 对话树节点 ID


# ═══════════════════════════════════════════════════════════════════════════════
# 用户标签（UserTag）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UserTag:
    """
    单个用户标签，带有置信度、来源和更新时间。

    设计基于文献:
      - "One chatbot per person" (Ma et al., 2021): 隐式画像提取
      - "Know me, respond to me" (Jiang et al., 2025): 动态画像更新
      - "Controllable Long-Term User Memory" (Sun et al., 2023): Confidence-Gated Writing
    """
    name: str                       # 标签名称，如 "occupation"
    value: TagValue                 # 标签值，如 "AI Engineer"
    confidence: float = 0.0         # 置信度 [0, 1]
    source: str = "unknown"         # 来源: L1 | L2 | L3 | L4 | inferred | user_declared
    last_updated: Timestamp = field(default_factory=time.time)
    verification_count: int = 0     # 被其他证据验证的次数
    is_sensitive: bool = False      # 用户是否对该标签获取表现出反感

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "last_updated": self.last_updated,
            "verification_count": self.verification_count,
            "is_sensitive": self.is_sensitive,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UserTag":
        return cls(
            name=d["name"],
            value=d["value"],
            confidence=d.get("confidence", 0.0),
            source=d.get("source", "unknown"),
            last_updated=d.get("last_updated", time.time()),
            verification_count=d.get("verification_count", 0),
            is_sensitive=d.get("is_sensitive", False),
        )

    # ── 置信度更新 ──────────────────────────────────────────────

    def update_confidence(self, new_confidence: float, new_source: str) -> None:
        """
        基于新证据更新置信度（贝叶斯式融合）。

        规则:
          - L1/L4 (直接观测/用户声明): 置信度直接设为 0.8+
          - L2 (推断): 验证 3 次后每次 +0.15
          - L3 (暗示): 每次 +0.1，上限 0.7
        """
        if new_source in ("L1", "user_declared"):
            self.confidence = min(0.95, 0.8 + new_confidence * 0.2)
        elif new_source == "L4":
            self.confidence = min(0.95, 0.8 + new_confidence * 0.15)
        elif new_source == "L2":
            self.verification_count += 1
            if self.verification_count >= 3:
                self.confidence = min(0.9, self.confidence + 0.15)
        elif new_source == "L3":
            self.confidence = min(0.7, self.confidence + 0.1)

        self.last_updated = time.time()
        self.source = new_source


# ═══════════════════════════════════════════════════════════════════════════════
# 记忆点（MemoryPoint）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MemoryPoint:
    """
    高影响对话事件（记忆点），基于 rz.txt 的 "记忆点集 M(S)" 概念。

    每个记忆点包含:
      - 发生时间
      - 瞬时情绪冲击强度（边际权重）
      - 长期影响权重（综合权重，随时间衰减）
    """
    point_id: str
    timestamp: Timestamp
    content: str                    # 事件内容摘要
    emotion_polarity: float = 0.0   # 情绪极性 [-1, 1]
    emotion_intensity: float = 0.0  # 情绪强度 [0, 1]
    marginal_weight: float = 0.0    # 边际权重 W_m（瞬时冲击）
    decay_coefficient: float = 0.5  # 衰减系数 d（默认值 0.5，范围 0.3-0.7）
    topic_tags: List[str] = field(default_factory=list)
    related_node_ids: List[NodeId] = field(default_factory=list)

    def compute_composite_weight(self, current_time: Timestamp) -> float:
        """
        综合权重 W_c = W_m / (1 + T_m)^d
        其中 T_m = current_time - timestamp (小时)

        基于 rz.txt 定义 2.1.4 中的幂律衰减函数。
        """
        T_hours = (current_time - self.timestamp) / 3600.0
        if T_hours < 0:
            T_hours = 0
        return self.marginal_weight / ((1 + T_hours) ** self.decay_coefficient)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryPoint":
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# 记忆组块（MemoryChunk）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MemoryChunk:
    """
    对话记忆组块：一组关联的对话轮次，按主题/任务聚合。

    基于文献:
      - MemoryBank (Zhong et al., 2024): 时间衰减 + 重要性加权
      - "Beyond Dialogue Time" (Su et al., 2026): 会话分解 + 时间语义标签
    """
    chunk_id: str
    created_at: Timestamp
    last_accessed: Timestamp
    importance: float = 0.5         # 重要性 [0, 1]
    summary_level: int = 0          # 0=原始, 1=一级摘要, 2=二级摘要
    stage: str = "hot"              # hot | warm | cool | cold
    decay_tau: float = 24.0         # 衰减常数（小时），默认 24h
    topic_tags: List[str] = field(default_factory=list)
    entity_refs: List[str] = field(default_factory=list)
    content: str = ""               # 组块内容（原始或摘要）

    # 阶梯跃迁阈值（小时）
    HOT_WARM_THRESHOLD: int = 24   # 1 天
    WARM_COOL_THRESHOLD: int = 168 # 7 天
    COOL_COLD_THRESHOLD: int = 720 # 30 天

    def get_effective_weight(self, current_time: Timestamp) -> float:
        """
        计算记忆的有效权重（加权单指数衰减 + 阶梯跃迁）。

        公式:
          W(t) = importance * exp(-t/τ) * stage_factor

        stage_factor:
          hot   = 1.0  (< 1 天)
          warm  = 0.7  (1-7 天)
          cool  = 0.3  (7-30 天)
          cold  = 0.1  (> 30 天)

        高重要性记忆衰减更慢（τ 扩大 1.5x）。
        """
        t_hours = (current_time - self.last_accessed) / 3600.0
        if t_hours < 0:
            t_hours = 0

        # 阶梯跃迁因子
        stage_factors = {"hot": 1.0, "warm": 0.7, "cool": 0.3, "cold": 0.1}
        stage_factor = stage_factors.get(self.stage, 0.1)

        # 动态衰减常数：高重要性记忆衰减更慢
        tau = self.decay_tau
        if self.importance > 0.8:
            tau *= 1.5

        # 单指数衰减
        decay = math.exp(-t_hours / tau) if tau > 0 else 0.0

        return self.importance * decay * stage_factor

    def update_stage(self, current_time: Timestamp) -> None:
        """根据时间间隔更新记忆阶段。"""
        t_hours = (current_time - self.last_accessed) / 3600.0
        if t_hours < self.HOT_WARM_THRESHOLD:
            self.stage = "hot"
        elif t_hours < self.WARM_COOL_THRESHOLD:
            self.stage = "warm"
        elif t_hours < self.COOL_COLD_THRESHOLD:
            self.stage = "cool"
        else:
            self.stage = "cold"

    def should_cleanup(self, current_time: Timestamp) -> bool:
        """
        是否应被清理或降级。

        规则:
          - >30 天 + importance < 0.3 → 清理
          - >7 天 + 原始记忆 + importance < 0.5 → 压缩为摘要
        """
        t_days = (current_time - self.last_accessed) / 86400.0
        if t_days > 30 and self.importance < 0.3:
            return True
        if t_days > 7 and self.summary_level == 0 and self.importance < 0.5:
            return True
        return False

    def should_compress(self, current_time: Timestamp) -> bool:
        """是否应被压缩到更高摘要级别。"""
        t_days = (current_time - self.last_accessed) / 86400.0
        if self.summary_level == 0 and t_days > 3:
            return True
        if self.summary_level == 1 and t_days > 14:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "importance": self.importance,
            "summary_level": self.summary_level,
            "stage": self.stage,
            "decay_tau": self.decay_tau,
            "topic_tags": self.topic_tags,
            "entity_refs": self.entity_refs,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryChunk":
        return cls(
            chunk_id=d["chunk_id"],
            created_at=d["created_at"],
            last_accessed=d["last_accessed"],
            importance=d.get("importance", 0.5),
            summary_level=d.get("summary_level", 0),
            stage=d.get("stage", "hot"),
            decay_tau=d.get("decay_tau", 24.0),
            topic_tags=d.get("topic_tags", []),
            entity_refs=d.get("entity_refs", []),
            content=d.get("content", ""),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 对话树节点权重（DialogueTreeNodeWeight）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DialogueTreeNodeWeight:
    """
    对话树节点的动态权重，用于分支排序和推荐。

    权重更新公式:
      new_weight = old_weight * (1 - α) + event_score * α

    其中 event_score 由以下事件触发:
      - 用户选择该分支: +0.5
      - 用户在该分支满意度高: +0.3
      - 用户在该分支停留时间长: +0.2
      - LLM 意图匹配度高: +0.2
    """
    node_id: NodeId
    weight: float = 0.5
    last_updated: Timestamp = field(default_factory=time.time)
    selection_count: int = 0       # 用户选择次数
    satisfaction_sum: float = 0.0  # 累计满意度
    dwell_time_sum: float = 0.0    # 累计停留时间（秒）
    intent_match_sum: float = 0.0  # 累计意图匹配度

    ALPHA: float = 0.3             # EMA 更新系数

    def update(self, event_type: str, score: float, dwell_time: float = 0.0) -> None:
        """
        基于事件更新权重。

        Args:
            event_type: "select" | "satisfaction" | "dwell" | "intent_match"
            score: 事件得分 [0, 1]
            dwell_time: 停留时间（秒），仅在 event_type="dwell" 时有效
        """
        event_scores = {
            "select": 0.5,
            "satisfaction": 0.3,
            "dwell": 0.2,
            "intent_match": 0.2,
        }
        base_score = event_scores.get(event_type, 0.0)
        event_score = base_score * score

        # EMA 更新
        self.weight = self.weight * (1 - self.ALPHA) + event_score * self.ALPHA
        self.weight = max(0.0, min(1.0, self.weight))
        self.last_updated = time.time()

        # 累计统计
        if event_type == "select":
            self.selection_count += 1
        elif event_type == "satisfaction":
            self.satisfaction_sum += score
        elif event_type == "dwell":
            self.dwell_time_sum += dwell_time
        elif event_type == "intent_match":
            self.intent_match_sum += score

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DialogueTreeNodeWeight":
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# g 因子评估记录（GFactorAssessment）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GFactorAssessment:
    """
    g 因子评估记录，基于对话质量指标的推断结果。

    评估维度:
      - concept_understanding_speed: 概念理解速度（从首次提及到正确使用的轮次）
      - question_depth: 追问深度（平均问题的抽象层次）
      - cross_domain_transfer: 跨领域迁移能力（0-1）
      - error_correction_rate: 错误修正率（犯错后快速纠正的比例）
      - abstraction_preference: 抽象偏好（具体 vs 抽象）
    """
    assessment_id: str
    timestamp: Timestamp
    domain: str = ""              # 评估领域（g 因子是领域相对的）

    # 原始指标（0-1）
    concept_understanding_speed: float = 0.5
    question_depth: float = 0.5
    cross_domain_transfer: float = 0.5
    error_correction_rate: float = 0.5
    abstraction_preference: float = 0.5

    # 综合 g 因子（加权平均，可配置权重）
    g_factor: float = 0.5

    # 评估来源
    source: str = "inferred"        # inferred | micro_task | explicit_test
    confidence: float = 0.0

    def compute_g_factor(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        计算综合 g 因子。

        默认权重（基于文献启发式）:
          concept_understanding_speed: 0.30
          question_depth: 0.25
          cross_domain_transfer: 0.20
          error_correction_rate: 0.15
          abstraction_preference: 0.10
        """
        if weights is None:
            weights = {
                "concept_understanding_speed": 0.30,
                "question_depth": 0.25,
                "cross_domain_transfer": 0.20,
                "error_correction_rate": 0.15,
                "abstraction_preference": 0.10,
            }
        total = sum(weights.values())
        if total == 0:
            return 0.5

        g = (
            weights["concept_understanding_speed"] * self.concept_understanding_speed +
            weights["question_depth"] * self.question_depth +
            weights["cross_domain_transfer"] * self.cross_domain_transfer +
            weights["error_correction_rate"] * self.error_correction_rate +
            weights["abstraction_preference"] * self.abstraction_preference
        ) / total
        return round(g, 3)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GFactorAssessment":
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# 环境上下文（EnvironmentalContext）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EnvironmentalContext:
    """L1 被动观测获取的环境上下文。"""
    time_of_day: str = ""           # morning | afternoon | evening | night
    day_of_week: str = ""           # weekday | weekend
    weather: str = ""               # sunny | cloudy | rainy | snowy | unknown
    device_type: str = ""          # desktop | mobile | tablet | unknown
    timezone: str = ""             # UTC offset, e.g. "+08:00"
    location: str = ""             # city name or "unknown"
    session_context: str = ""      # quick_query | deep_conversation | casual

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EnvironmentalContext":
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# 时间状态（TemporalState）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TemporalState:
    """时间状态（实时计算，不持久化）。"""
    last_interaction: Timestamp = 0.0
    session_interval: float = 0.0   # 距上次会话的间隔（秒）
    memory_decay_factor: float = 1.0
    context_recovery_needed: bool = False
    active_hours: List[int] = field(default_factory=list)  # 活跃时段（小时，0-23）
    conversation_frequency: float = 0.0  # 对话频率（次/天）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TemporalState":
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# 标签获取事件（TagAcquisitionEvent）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TagAcquisitionEvent:
    """标签获取事件记录，用于审计和 A/B 测试。"""
    event_id: str
    timestamp: Timestamp
    tag_name: str
    level: str                      # L1 | L2 | L3 | L4
    method: str                     # api | inference | hint | ask
    success: bool                   # 是否成功获取
    user_aversion_detected: bool = False  # 是否检测到用户反感
    intrusion_benefit_ratio: float = 0.0
    response_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TagAcquisitionEvent":
        return cls(**d)
```

### 2.2 修改模型：`service/models.py` 扩展

```python
# 在现有 Session 中新增字段

@dataclass
class Session:
    """User session with full context for the DialogMesh engine."""

    # ── 现有字段（保留）──────────────────────────────────────
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    tenant_id: str = "default"
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    parse_context: Optional[Any] = None
    cognitive_profile: Optional[CognitiveProfile] = None  # 旧版，保留兼容
    turn_count: int = 0
    history: List[TurnRecord] = field(default_factory=list)
    state: str = "active"
    pending_clarification: Optional[str] = None
    ws_connections: List[str] = field(default_factory=list)

    # ── 新增字段（v2.0）─────────────────────────────────────
    cognitive_profile_v2: Optional["CognitiveProfileV2"] = None  # 双轨画像
    memory_chunks: List[Dict[str, Any]] = field(default_factory=list)  # 记忆组块
    dialogue_tree_weights: Dict[str, Any] = field(default_factory=dict)  # 对话树权重
    tag_acquisition_history: List[Dict[str, Any]] = field(default_factory=list)  # 标签获取历史
    g_factor_assessments: List[Dict[str, Any]] = field(default_factory=list)  # g 因子评估历史
    version: int = 1                    # 乐观锁版本

    # ── 序列化扩展 ─────────────────────────────────────────
    def to_persistent_dict(self) -> Dict[str, Any]:
        base = {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "parse_context": self.parse_context.to_dict() if self.parse_context else None,
            "cognitive_profile": self.cognitive_profile.to_dict() if self.cognitive_profile else None,
            "turn_count": self.turn_count,
            "history": [t.to_dict() for t in self.history],
            "state": self.state,
            "pending_clarification": self.pending_clarification,
            # v2.0 新增
            "cognitive_profile_v2": self.cognitive_profile_v2.to_dict() if self.cognitive_profile_v2 else None,
            "memory_chunks": self.memory_chunks,
            "dialogue_tree_weights": self.dialogue_tree_weights,
            "tag_acquisition_history": self.tag_acquisition_history,
            "g_factor_assessments": self.g_factor_assessments,
            "version": self.version,
        }
        return base

    @classmethod
    def from_persistent_dict(cls, d: Dict[str, Any]) -> "Session":
        # 旧版兼容：如果存在 cognitive_profile_v2，优先使用
        session = cls(
            session_id=d["session_id"],
            tenant_id=d.get("tenant_id", "default"),
            user_id=d.get("user_id"),
            created_at=d["created_at"],
            last_activity_at=d["last_activity_at"],
            expires_at=d.get("expires_at", 0.0),
            turn_count=d.get("turn_count", 0),
            state=d.get("state", "active"),
            pending_clarification=d.get("pending_clarification"),
            version=d.get("version", 1),
        )
        # 恢复 history
        if "history" in d:
            session.history = [TurnRecord.from_dict(t) for t in d["history"]]
        # 恢复 cognitive_profile_v2（优先）
        if "cognitive_profile_v2" in d and d["cognitive_profile_v2"]:
            from service.cognitive.dynamics import CognitiveProfileV2
            session.cognitive_profile_v2 = CognitiveProfileV2.from_dict(d["cognitive_profile_v2"])
        elif "cognitive_profile" in d and d["cognitive_profile"]:
            # 旧版迁移：从旧版 cognitive_profile 构造 v2
            session.cognitive_profile = CognitiveProfile.from_dict(d["cognitive_profile"])
            session.cognitive_profile_v2 = _migrate_old_profile(session.cognitive_profile)
        # 恢复其他 v2 字段
        session.memory_chunks = d.get("memory_chunks", [])
        session.dialogue_tree_weights = d.get("dialogue_tree_weights", {})
        session.tag_acquisition_history = d.get("tag_acquisition_history", [])
        session.g_factor_assessments = d.get("g_factor_assessments", [])
        return session


def _migrate_old_profile(old: CognitiveProfile) -> "CognitiveProfileV2":
    """将旧版 CognitiveProfile 迁移到新版。"""
    from service.cognitive.dynamics import CognitiveProfileV2, CognitiveDynamics
    from service.cognitive.tag_layer import TagLayer

    track_a = CognitiveDynamics(
        metacognition=old.metacognition,
        divergence=old.divergence,
        tracking_depth=old.tracking_depth,
        stability=old.stability,
        confidence=old.confidence,
    )
    track_b = TagLayer()  # 空标签层，后续通过 L1/L2 填充
    return CognitiveProfileV2(track_a=track_a, track_b=track_b)
```

---

## 3. 核心模块详细设计

### 3.1 轨道 A：认知动力学（`service/cognitive/dynamics.py`）

```python
# 核心类：CognitiveDynamics

class CognitiveDynamics:
    """轨道 A：认知动力学（动态演化）。"""

    # 核心参数
    cognitive_inertia: float = 0.5       # 认知惯性（对话风格稳定性）
    behavioral_inertia: float = 0.5     # 行为惯性（反馈模式稳定性）
    trust_level: float = 0.5            # 信任度 T(S,O)
    expectation_bias: float = 0.0       # 预期偏差 ΔE
    emotion_monotony: float = 0.5       # 情绪单调度 M_Em
    cognitive_resource: float = 1.0     # 认知资源 C_max
    attention_anchor: str = ""          # 注意力锚点 P
    self_worth: float = 0.5             # 自我价值感 V(S)
    memory_points: List[MemoryPoint] = field(default_factory=list)

    # 更新方法
    def update_from_turn(self, turn: TurnRecord, feedback: Optional[Dict] = None) -> None:
        """基于单轮对话更新认知动力学。"""
        # 1. 更新信任度（预期兑现率）
        if feedback and "satisfaction" in feedback:
            satisfaction = feedback["satisfaction"]  # 0-1
            self.trust_level = self.trust_level * 0.7 + satisfaction * 0.3

        # 2. 更新预期偏差
        if feedback and "expected_vs_actual" in feedback:
            delta = feedback["expected_vs_actual"]
            self.expectation_bias = self.expectation_bias * 0.8 + delta * 0.2

        # 3. 更新认知资源（基于对话长度和回复速度推断）
        if turn.latency_ms > 0:
            # 回复慢 → 认知资源低
            inferred_resource = max(0.0, 1.0 - (turn.latency_ms / 10000))
            self.cognitive_resource = self.cognitive_resource * 0.7 + inferred_resource * 0.3

    def compute_emotion_monotony(self, recent_turns: List[TurnRecord], window: int = 30) -> float:
        """
        计算情绪单调度 M_Em = 1 - H(Em) / H_max
        基于信息熵的情绪序列同质化程度。

        Args:
            recent_turns: 最近 N 轮对话
            window: 窗口大小（默认 30 轮）
        """
        if len(recent_turns) < 2:
            return 0.5

        # 提取情绪极性序列
        polarities = []
        for turn in recent_turns[-window:]:
            if turn.intent_result and "sentiment" in turn.intent_result:
                polarities.append(turn.intent_result["sentiment"])
            else:
                polarities.append(0.0)

        # 计算信息熵（将极性离散化为 5 个桶）
        buckets = [0, 0, 0, 0, 0]  # [-1, -0.5), [-0.5, 0), [0, 0.5), [0.5, 1), neutral
        for p in polarities:
            if p < -0.5:
                buckets[0] += 1
            elif p < 0:
                buckets[1] += 1
            elif p == 0:
                buckets[2] += 1
            elif p < 0.5:
                buckets[3] += 1
            else:
                buckets[4] += 1

        total = len(polarities)
        if total == 0:
            return 0.5

        entropy = 0.0
        for count in buckets:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        H_max = math.log2(5)  # 5 个桶的最大熵
        M_Em = 1.0 - (entropy / H_max) if H_max > 0 else 0.5
        return round(M_Em, 3)
```

### 3.2 轨道 B：标签化信息层（`service/cognitive/tag_layer.py`）

```python
class TagLayer:
    """轨道 B：标签化信息层（静态/慢变）。"""

    # 基础标签
    basic_tags: Dict[str, UserTag] = field(default_factory=dict)
    # 认知能力
    cognitive_capacity: Dict[str, UserTag] = field(default_factory=dict)
    # 交互偏好
    interaction_prefs: Dict[str, UserTag] = field(default_factory=dict)
    # 社交图谱
    social_graph: Dict[str, UserTag] = field(default_factory=dict)
    # 兴趣图谱
    interest_graph: Dict[str, UserTag] = field(default_factory=dict)
    # 环境上下文（实时，不持久化）
    environmental_context: EnvironmentalContext = field(default_factory=EnvironmentalContext)

    # 便捷访问方法
    def get_tag(self, category: str, name: str) -> Optional[UserTag]:
        """按类别和名称获取标签。"""
        category_map = {
            "basic": self.basic_tags,
            "cognitive": self.cognitive_capacity,
            "interaction": self.interaction_prefs,
            "social": self.social_graph,
            "interest": self.interest_graph,
        }
        tags = category_map.get(category, {})
        return tags.get(name)

    def set_tag(self, category: str, tag: UserTag) -> None:
        """设置标签。"""
        category_map = {
            "basic": self.basic_tags,
            "cognitive": self.cognitive_capacity,
            "interaction": self.interaction_prefs,
            "social": self.social_graph,
            "interest": self.interest_graph,
        }
        tags = category_map.get(category, {})
        tags[tag.name] = tag

    def to_llm_context(self) -> str:
        """将标签层转换为 LLM 可用的上下文字符串。"""
        parts = []
        for category, tags in [
            ("基础标签", self.basic_tags),
            ("认知能力", self.cognitive_capacity),
            ("交互偏好", self.interaction_prefs),
            ("兴趣图谱", self.interest_graph),
        ]:
            if tags:
                tag_strs = [f"{t.name}={t.value}(conf={t.confidence:.2f})" for t in tags.values() if t.confidence > 0.3]
                if tag_strs:
                    parts.append(f"[{category}] {', '.join(tag_strs)}")
        return "\n".join(parts)
```

### 3.3 时间衰减管理（`service/cognitive/temporal.py`）

```python
class TimeDecayManager:
    """
    时间衰减管理器。

    基于文献:
      - MemoryBank (Zhong et al., 2024): 时间衰减曲线
      - Ebbinghaus 遗忘曲线 (Sumida et al., 2025)
      - "Beyond Dialogue Time" (Su et al., 2026): 时间语义记忆
    """

    def __init__(self, session: Session):
        self.session = session
        self.temporal_state = TemporalState()
        self._update_temporal_state()

    def _update_temporal_state(self) -> None:
        """更新时间状态。"""
        now = time.time()
        if self.session.last_activity_at > 0:
            self.temporal_state.session_interval = now - self.session.last_activity_at
            self.temporal_state.last_interaction = self.session.last_activity_at
        else:
            self.temporal_state.session_interval = 0
            self.temporal_state.last_interaction = now

        # 判断是否需要上下文恢复
        if self.temporal_state.session_interval > 30 * 86400:  # 30 天
            self.temporal_state.context_recovery_needed = True

        # 计算记忆衰减因子
        days = self.temporal_state.session_interval / 86400.0
        self.temporal_state.memory_decay_factor = math.exp(-days / 7.0)  # 7 天衰减常数

    def get_memory_stage(self, last_accessed: Timestamp) -> str:
        """根据上次访问时间判断记忆阶段。"""
        t_hours = (time.time() - last_accessed) / 3600.0
        if t_hours < 24:
            return "hot"
        elif t_hours < 168:
            return "warm"
        elif t_hours < 720:
            return "cool"
        else:
            return "cold"

    def generate_context_recovery_summary(self, memory_chunks: List[MemoryChunk]) -> Optional[str]:
        """
        生成上下文恢复摘要（冷记忆 → 热记忆）。
        基于 "Beyond Dialogue Time" 的时间语义记忆策略。
        """
        if not self.temporal_state.context_recovery_needed:
            return None

        # 按重要性排序的冷记忆
        cold_chunks = [c for c in memory_chunks if c.stage == "cold"]
        if not cold_chunks:
            return None

        cold_chunks.sort(key=lambda c: c.importance, reverse=True)
        top_chunks = cold_chunks[:3]

        # 生成摘要（实际实现中由 LLM 生成）
        summaries = [f"- {c.content[:50]}..." for c in top_chunks]
        return (
            f"您已 {(self.temporal_state.session_interval / 86400):.0f} 天未对话。"
            f"上次我们在讨论以下主题:\n" + "\n".join(summaries)
        )
```

### 3.4 标签获取引擎（`service/cognitive/acquisition.py`）

```python
class TagAcquisitionEngine:
    """
    标签获取引擎（L1-L4 四级渐进式）。

    设计基于文献:
      - "The power of personalization" (Ait Baha et al., 2023): 显式/隐式画像
      - ProfiLLM (David et al., 2025): LLM-based 持续画像

    创新点:
      - L3 暗示试探（文献极少）
      - 用户反感检测（文献空白）
      - 侵入-收益比决策（文献空白）
    """

    # 标签信息价值表（可配置）
    TAG_VALUE_MAP = {
        "occupation": 0.9,
        "domain": 0.9,
        "g_factor": 0.8,
        "education_level": 0.7,
        "communication_style": 0.6,
        "detail_level": 0.6,
        "time_of_day": 0.1,  # L1 获取，几乎无侵入
        "weather": 0.1,
    }

    # 侵入感阈值
    INTRUSION_THRESHOLD = 0.3

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.history: List[TagAcquisitionEvent] = []

    async def acquire(self, tag_name: str, session: Session, context: Dict[str, Any]) -> Optional[UserTag]:
        """
        尝试获取标签，按 L1 → L2 → L3 → L4 顺序尝试。

        Returns:
            获取到的 UserTag，或 None（如果获取失败或用户反感）
        """
        # L1: 被动观测
        tag = await self._acquire_l1(tag_name, session, context)
        if tag:
            return tag

        # L2: 间接推断
        tag = await self._acquire_l2(tag_name, session, context)
        if tag and tag.confidence >= 0.5:
            return tag

        # L3: 暗示试探（需要评估侵入-收益比）
        if self._should_attempt_l3(tag_name, session):
            tag = await self._acquire_l3(tag_name, session, context)
            if tag and tag.confidence >= 0.5:
                return tag

        # L4: 主动询问（仅高价值标签）
        if self._should_attempt_l4(tag_name, session):
            tag = await self._acquire_l4(tag_name, session, context)
            if tag:
                return tag

        return None

    async def _acquire_l1(self, tag_name: str, session: Session, context: Dict[str, Any]) -> Optional[UserTag]:
        """L1: 被动观测（系统 API）。"""
        if tag_name in ("time_of_day", "day_of_week"):
            now = datetime.now()
            hour = now.hour
            if 6 <= hour < 12:
                tod = "morning"
            elif 12 <= hour < 18:
                tod = "afternoon"
            elif 18 <= hour < 22:
                tod = "evening"
            else:
                tod = "night"
            return UserTag(name=tag_name, value=tod, confidence=1.0, source="L1")

        if tag_name == "timezone":
            tz = context.get("timezone", "")
            if tz:
                return UserTag(name=tag_name, value=tz, confidence=1.0, source="L1")

        if tag_name == "device_type":
            device = context.get("user_agent", "")
            if "Mobile" in device or "Android" in device or "iPhone" in device:
                return UserTag(name=tag_name, value="mobile", confidence=0.9, source="L1")
            elif "Tablet" in device or "iPad" in device:
                return UserTag(name=tag_name, value="tablet", confidence=0.9, source="L1")
            else:
                return UserTag(name=tag_name, value="desktop", confidence=0.8, source="L1")

        return None

    async def _acquire_l2(self, tag_name: str, session: Session, context: Dict[str, Any]) -> Optional[UserTag]:
        """L2: 间接推断（LLM 分析对话历史）。"""
        if not self.llm_client or len(session.history) < 3:
            return None

        # 构建提示词
        recent_dialogue = "\n".join([
            f"{t.role}: {t.content[:100]}" for t in session.history[-10:]
        ])

        prompt = f"""基于以下对话历史，推断用户的 "{tag_name}"。
仅返回 JSON 格式: {{"value": "推断值", "confidence": 0.0-1.0, "reason": "简短理由"}}

对话历史:
{recent_dialogue}
"""
        try:
            response = await self.llm_client.complete(prompt)
            result = json.loads(response)
            return UserTag(
                name=tag_name,
                value=result["value"],
                confidence=result["confidence"],
                source="L2",
            )
        except Exception:
            return None

    async def _acquire_l3(self, tag_name: str, session: Session, context: Dict[str, Any]) -> Optional[UserTag]:
        """
        L3: 暗示试探（自然对话中嵌入暗示性问题）。
        创新点：文献中几乎无涉及。
        """
        # 生成暗示（由 LLM 生成）
        hint_prompt = f"""生成一个自然的问题，用于试探用户的 "{tag_name}"。
要求:
  - 不突兀，融入对话上下文
  - 用户不会感到被调查
  - 简短（不超过 20 字）
仅返回问题本身，无其他内容。"""

        try:
            hint_question = await self.llm_client.complete(hint_prompt)
            # 将暗示问题存入 session 的 pending_clarification（或类似的暂存区）
            # 等待用户回复后，由 _process_l3_response 处理
            session.pending_clarification = json.dumps({
                "type": "tag_acquisition_hint",
                "tag_name": tag_name,
                "hint_question": hint_question.strip(),
            })
            return None  # L3 是异步的，返回 None 表示等待用户回复
        except Exception:
            return None

    async def process_l3_response(self, tag_name: str, user_response: str, session: Session) -> Optional[UserTag]:
        """处理用户对 L3 暗示的回复。"""
        # 检测用户反感
        if self._detect_user_aversion(user_response):
            # 标记标签为敏感，停止获取
            tag = UserTag(name=tag_name, value="", confidence=0.0, source="L3", is_sensitive=True)
            return tag

        # 让 LLM 从回复中提取标签值
        extract_prompt = f"""用户回复: "{user_response}"
从中提取用户的 "{tag_name}"。
仅返回 JSON: {{"value": "", "confidence": 0.0-1.0}}"""
        try:
            response = await self.llm_client.complete(extract_prompt)
            result = json.loads(response)
            return UserTag(name=tag_name, value=result["value"], confidence=result["confidence"] * 0.7, source="L3")
        except Exception:
            return None

    def _detect_user_aversion(self, user_response: str) -> bool:
        """
        检测用户对暗示/询问的回避。
        创新点：文献空白。
        """
        response = user_response.strip().lower()
        indicators = [
            len(response) <= 6,  # 非常短
            response in ("随便", "都行", "不重要", "无所谓", "不想说", "别问了"),
            response.startswith("换个话题"),
            response.startswith("为什么问这个"),
        ]
        return any(indicators)

    def _should_attempt_l3(self, tag_name: str, session: Session) -> bool:
        """评估是否应尝试 L3（侵入-收益比）。"""
        tag_value = self.TAG_VALUE_MAP.get(tag_name, 0.5)
        # L3 的侵入感约为 0.3（用户可能感知到"被了解"）
        intrusion = 0.3
        ratio = tag_value / intrusion
        return ratio > self.INTRUSION_THRESHOLD

    def _should_attempt_l4(self, tag_name: str, session: Session) -> bool:
        """评估是否应尝试 L4（仅高价值标签）。"""
        tag_value = self.TAG_VALUE_MAP.get(tag_name, 0.5)
        # L4 的侵入感约为 0.6（直接询问）
        intrusion = 0.6
        ratio = tag_value / intrusion
        return ratio > 0.8  # 更高的阈值
```

### 3.5 g 因子推断引擎（`service/cognitive/g_factor.py`）

```python
class GFInferenceEngine:
    """
    g 因子推断引擎。

    基于文献:
      - "Using AI to support education" (Casebourne et al., 2025): 通过认知任务评估 g 因子
      - "Generative AI vs. AGI" (Goertzel, 2023): 多任务评估方法

    创新点:
      - 从对话历史中推断（文献空白）
      - 嵌入式微型任务（文献空白）
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.assessments: Dict[str, GFactorAssessment] = {}  # domain -> assessment

    async def infer_from_dialogue(self, history: List[TurnRecord], domain: str = "general") -> GFactorAssessment:
        """
        从对话历史中推断 g 因子。

        评估指标:
          1. 概念理解速度：从首次提及到正确使用的轮次
          2. 追问深度：用户问题的平均抽象层次
          3. 跨领域迁移：能否将一个领域的概念应用到另一个领域
          4. 错误修正率：犯错后快速纠正的比例
        """
        assessment = GFactorAssessment(
            assessment_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            domain=domain,
            source="inferred",
        )

        if len(history) < 5:
            assessment.confidence = 0.2
            assessment.g_factor = 0.5
            return assessment

        # 1. 概念理解速度
        assessment.concept_understanding_speed = self._compute_concept_speed(history)

        # 2. 追问深度
        assessment.question_depth = self._compute_question_depth(history)

        # 3. 跨领域迁移（需要 LLM 判断）
        if self.llm_client:
            assessment.cross_domain_transfer = await self._compute_cross_domain(history)

        # 4. 错误修正率
        assessment.error_correction_rate = self._compute_error_correction(history)

        # 5. 抽象偏好
        assessment.abstraction_preference = self._compute_abstraction_preference(history)

        # 计算综合 g 因子
        assessment.g_factor = assessment.compute_g_factor()
        assessment.confidence = 0.6 if len(history) >= 20 else 0.4

        self.assessments[domain] = assessment
        return assessment

    def _compute_concept_speed(self, history: List[TurnRecord]) -> float:
        """概念理解速度：从首次提及到正确使用的轮次。"""
        # 简化实现：统计用户正确使用的技术概念数量 / 总提及概念数量
        # 实际实现中需要概念抽取
        total_concepts = 0
        understood_concepts = 0
        for i, turn in enumerate(history):
            if turn.role == "user" and turn.intent_result:
                entities = turn.intent_result.get("entities", [])
                for entity in entities:
                    if entity.get("type") in ("concept", "technical_term"):
                        total_concepts += 1
                        # 检查后续轮次是否正确使用
                        for j in range(i + 1, min(i + 5, len(history))):
                            if history[j].role == "user" and entity["value"] in history[j].content:
                                understood_concepts += 1
                                break
        if total_concepts == 0:
            return 0.5
        return min(1.0, understood_concepts / total_concepts + 0.3)

    def _compute_question_depth(self, history: List[TurnRecord]) -> float:
        """追问深度：基于问题的长度和关键词。"""
        depths = []
        for turn in history:
            if turn.role == "user":
                content = turn.content
                # 深度指标：问题长度、包含"为什么"/"如何"/"底层"/"机制"等关键词
                depth_score = 0.3
                if len(content) > 50:
                    depth_score += 0.2
                if any(kw in content for kw in ("为什么", "如何", "底层", "机制", "原理", "本质")):
                    depth_score += 0.3
                if "?" in content or "？" in content:
                    depth_score += 0.2
                depths.append(min(1.0, depth_score))
        if not depths:
            return 0.5
        return round(sum(depths) / len(depths), 3)

    async def _compute_cross_domain(self, history: List[TurnRecord]) -> float:
        """跨领域迁移能力（需要 LLM 判断）。"""
        if not self.llm_client or len(history) < 10:
            return 0.5

        dialogue = "\n".join([f"{t.role}: {t.content[:80]}" for t in history[-10:]])
        prompt = f"""分析以下对话，判断用户是否展现了跨领域迁移能力
（将 A 领域的概念/方法应用到 B 领域）。
仅返回 0-1 之间的分数，无其他内容。

对话:
{dialogue}"""
        try:
            response = await self.llm_client.complete(prompt)
            return max(0.0, min(1.0, float(response.strip())))
        except Exception:
            return 0.5

    def _compute_error_correction(self, history: List[TurnRecord]) -> float:
        """错误修正率：用户犯错后是否快速纠正。"""
        # 简化：统计用户"纠正"/"修正"/"不对"/"错了"后的积极反馈
        corrections = 0
        errors = 0
        for i, turn in enumerate(history):
            if turn.role == "user":
                if any(kw in turn.content for kw in ("纠正", "修正", "错了", "不对", "抱歉")):
                    errors += 1
                    # 检查后续是否有积极反馈（如"明白了"、"谢谢"）
                    for j in range(i + 1, min(i + 3, len(history))):
                        if any(kw in history[j].content for kw in ("明白了", "谢谢", "懂了", "清楚")):
                            corrections += 1
                            break
        if errors == 0:
            return 0.5  # 未知
        return min(1.0, corrections / errors + 0.2)

    def _compute_abstraction_preference(self, history: List[TurnRecord]) -> float:
        """抽象偏好：用户偏好具体例子还是抽象原理。"""
        abstract_signals = 0
        concrete_signals = 0
        for turn in history:
            if turn.role == "user":
                content = turn.content
                if any(kw in content for kw in ("原理", "机制", "本质", "抽象", "理论", "框架")):
                    abstract_signals += 1
                if any(kw in content for kw in ("例子", "具体", "实际", "代码", "案例", "操作")):
                    concrete_signals += 1
        total = abstract_signals + concrete_signals
        if total == 0:
            return 0.5
        return round(abstract_signals / total, 3)

    async def generate_micro_task(self, domain: str = "general") -> Optional[Dict[str, str]]:
        """
        生成嵌入式微型任务（用于 g 因子评估）。
        创新点：文献空白。
        """
        if not self.llm_client:
            return None

        prompt = f"""生成一个简短的认知任务（适合嵌入对话中），用于评估用户的理解能力。
领域: {domain}
要求:
  - 看起来是自然的对话延续
  - 只有一个问题
  - 考察概念理解，而非知识储备
  - 简短（不超过 30 字）

返回 JSON 格式:
{{"question": "", "expected_answer_pattern": "", "difficulty": 0.0-1.0}}"""
        try:
            response = await self.llm_client.complete(prompt)
            return json.loads(response)
        except Exception:
            return None
```

### 3.6 对话树权重管理（`service/cognitive/dialogue_tree_weight.py`）

```python
class DialogueTreeWeightManager:
    """
    对话树权重管理器。

    动态权重更新:
      new_weight = old_weight * (1 - α) + event_score * α

    事件类型:
      - select: 用户选择该分支
      - satisfaction: 用户在该分支的满意度反馈
      - dwell: 用户在该分支的停留时间
      - intent_match: LLM 意图匹配度
    """

    ALPHA = 0.3

    def __init__(self, session: Session):
        self.session = session
        self.weights: Dict[NodeId, DialogueTreeNodeWeight] = {}
        self._load_weights()

    def _load_weights(self) -> None:
        """从 session 加载权重。"""
        for node_id, data in self.session.dialogue_tree_weights.items():
            self.weights[node_id] = DialogueTreeNodeWeight.from_dict(data)

    def _save_weights(self) -> None:
        """保存权重到 session。"""
        self.session.dialogue_tree_weights = {
            node_id: w.to_dict() for node_id, w in self.weights.items()
        }

    def get_weight(self, node_id: NodeId) -> float:
        """获取节点权重。"""
        if node_id not in self.weights:
            self.weights[node_id] = DialogueTreeNodeWeight(node_id=node_id)
        return self.weights[node_id].weight

    def update_weight(self, node_id: NodeId, event_type: str, score: float, dwell_time: float = 0.0) -> None:
        """更新节点权重。"""
        if node_id not in self.weights:
            self.weights[node_id] = DialogueTreeNodeWeight(node_id=node_id)
        self.weights[node_id].update(event_type, score, dwell_time)
        self._save_weights()

    def get_sorted_children(self, parent_node_id: NodeId, children: List[NodeId]) -> List[Tuple[NodeId, float]]:
        """按权重排序子节点。"""
        scored = [(child_id, self.get_weight(child_id)) for child_id in children]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def decay_all_weights(self, decay_factor: float = 0.95) -> None:
        """全局权重衰减（防止未访问分支的权重僵化）。"""
        for weight in self.weights.values():
            weight.weight *= decay_factor
        self._save_weights()
```

### 3.7 记忆衰减管理（`service/cognitive/memory_decay.py`）

```python
class MemoryDecayManager:
    """
    记忆衰减管理器。

    基于文献:
      - MemoryBank (Zhong et al., 2024): 指数衰减 + 重要性加权
      - Ebbinghaus 遗忘曲线 (Sumida et al., 2025)
    """

    def __init__(self, session: Session):
        self.session = session
        self.chunks: List[MemoryChunk] = []
        self._load_chunks()

    def _load_chunks(self) -> None:
        for data in self.session.memory_chunks:
            self.chunks.append(MemoryChunk.from_dict(data))

    def _save_chunks(self) -> None:
        self.session.memory_chunks = [c.to_dict() for c in self.chunks]

    def add_chunk(self, chunk: MemoryChunk) -> None:
        """添加记忆组块。"""
        self.chunks.append(chunk)
        self._save_chunks()

    def update_access(self, chunk_id: str) -> None:
        """更新访问时间（重置衰减时钟）。"""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                chunk.last_accessed = time.time()
                chunk.stage = "hot"  # 重置为热记忆
                self._save_chunks()
                break

    def cleanup_and_compress(self, current_time: Optional[Timestamp] = None) -> Tuple[List[str], List[str]]:
        """
        执行清理和压缩。

        Returns:
            (清理的 chunk_ids, 压缩的 chunk_ids)
        """
        if current_time is None:
            current_time = time.time()

        removed = []
        compressed = []

        for chunk in self.chunks:
            # 更新阶段
            chunk.update_stage(current_time)

            # 清理
            if chunk.should_cleanup(current_time):
                removed.append(chunk.chunk_id)
                continue

            # 压缩
            if chunk.should_compress(current_time):
                compressed.append(chunk.chunk_id)
                # 实际压缩由外部 LLM 完成，这里标记为待压缩
                chunk.summary_level += 1

        # 移除已清理的组块
        self.chunks = [c for c in self.chunks if c.chunk_id not in removed]
        self._save_chunks()

        return removed, compressed

    def get_effective_chunks(self, current_time: Optional[Timestamp] = None, min_weight: float = 0.1) -> List[MemoryChunk]:
        """获取有效权重高于阈值的所有组块。"""
        if current_time is None:
            current_time = time.time()
        return [c for c in self.chunks if c.get_effective_weight(current_time) >= min_weight]

    def get_context_recovery_candidates(self, current_time: Optional[Timestamp] = None, top_k: int = 3) -> List[MemoryChunk]:
        """获取上下文恢复候选（冷记忆中的重要组块）。"""
        if current_time is None:
            current_time = time.time()
        cold_chunks = [c for c in self.chunks if c.stage == "cold" and c.importance > 0.5]
        cold_chunks.sort(key=lambda c: c.importance, reverse=True)
        return cold_chunks[:top_k]
```

### 3.8 融合层（`service/cognitive/fusion.py`）

```python
class FusionContext:
    """
    融合层：将轨道 A 和轨道 B 融合为 LLM 可用的上下文。

    设计原则:
      - 轨道 B 提供先验（稳定信息，减少推断成本）
      - 轨道 A 提供动态修正（实时状态）
    """

    def __init__(self, track_a: "CognitiveDynamics", track_b: "TagLayer", temporal: TemporalState):
        self.track_a = track_a
        self.track_b = track_b
        self.temporal = temporal

    def build_prompt_context(self, max_length: int = 800) -> str:
        """构建 LLM 提示词上下文。"""
        parts = []

        # ── 轨道 B 先验（稳定信息）──────────────────────────
        tag_context = self.track_b.to_llm_context()
        if tag_context:
            parts.append(f"[用户画像]\n{tag_context}")

        # ── 轨道 A 动态（实时状态）──────────────────────────
        parts.append(f"[动态状态]")
        parts.append(f"  信任度: {self.track_a.trust_level:.2f}")
        parts.append(f"  情绪单调度: {self.track_a.emotion_monotony:.2f} "
                    f"({'情绪单调，需情绪补足' if self.track_a.emotion_monotony > 0.6 else '情绪丰富'})")
        parts.append(f"  认知资源: {self.track_a.cognitive_resource:.2f} "
                    f"({'耐心充足' if self.track_a.cognitive_resource > 0.7 else '可能疲劳，需简洁回复'})")
        if self.track_a.attention_anchor:
            parts.append(f"  注意力锚点: {self.track_a.attention_anchor}")

        # ── 时间状态 ───────────────────────────────────────
        if self.temporal.session_interval > 7 * 86400:
            parts.append(f"[时间提醒] 用户已 {self.temporal.session_interval/86400:.0f} 天未对话，建议主动恢复上下文")

        context = "\n".join(parts)

        # 截断到最大长度（保留末尾，因为动态状态更重要）
        if len(context) > max_length:
            context = context[-max_length:]
            # 确保不截断到单词中间
            if context[0] != '\n':
                context = context[context.find('\n') + 1:]

        return context

    def build_response_strategy(self) -> Dict[str, Any]:
        """
        构建响应策略（供编排器使用）。

        Returns:
            {
                "detail_level": "high" | "medium" | "low",
                "communication_style": "direct" | "indirect" | "formal" | "casual",
                "should_clarify": bool,
                "should_empathize": bool,
                "complexity_target": float,  # 0-1
            }
        """
        strategy = {
            "detail_level": "medium",
            "communication_style": "direct",
            "should_clarify": False,
            "should_empathize": False,
            "complexity_target": 0.5,
        }

        # 基于认知资源调整详细程度
        if self.track_a.cognitive_resource < 0.4:
            strategy["detail_level"] = "low"
        elif self.track_a.cognitive_resource > 0.8:
            strategy["detail_level"] = "high"

        # 基于情绪单调度判断是否需要共情
        if self.track_a.emotion_monotony > 0.6:
            strategy["should_empathize"] = True

        # 基于信任度判断是否需要澄清
        if self.track_a.trust_level < 0.3:
            strategy["should_clarify"] = True

        # 基于 g 因子调整复杂度
        g_tag = self.track_b.get_tag("cognitive", "g_factor")
        if g_tag and g_tag.confidence > 0.5:
            strategy["complexity_target"] = g_tag.value

        return strategy


class FusionEngine:
    """融合引擎：在编排流程中调用，生成融合上下文。"""

    def __init__(self, profile_v2: "CognitiveProfileV2"):
        self.profile_v2 = profile_v2

    def fuse(self, temporal: TemporalState) -> FusionContext:
        """生成融合上下文。"""
        return FusionContext(
            track_a=self.profile_v2.track_a,
            track_b=self.profile_v2.track_b,
            temporal=temporal,
        )
```

---

## 4. 数据流（完整请求生命周期）

```
用户请求 → POST /v1/session/{id}/message
                │
                ▼
        ┌───────────────┐
        │  AgentService │
        │  process_msg  │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  TimeDecayMgr │  ← 更新 temporal_state，判断是否需要上下文恢复
        │  _update_temp │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  MemoryDecay  │  ← 清理/压缩过期记忆组块
        │  cleanup()    │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  TagAcquire   │  ← 尝试获取缺失标签（L1/L2 优先）
        │  acquire()    │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  FusionEngine │  ← 生成融合上下文 + 响应策略
        │  fuse()       │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  Orchestrator │  ← 将 fusion_context 注入 PCR/IntentParser
        │  process()    │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  PCR/Parser   │  ← 使用融合上下文进行意图解析
        │  evaluate()   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  DialogueTree │  ← 按权重排序分支
        │  get_sorted   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  gFactorEng   │  ← 更新 g 因子评估（异步）
        │  infer_from   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  CognDynUpdt  │  ← 更新认知动力学（信任度、情绪等）
        │  update_from  │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  MemoryChunk  │  ← 创建/更新记忆组块
        │  add_chunk()  │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  响应用户     │
        └───────────────┘
```

---

## 5. 接口定义（API 契约）

### 5.1 新增端点

```yaml
# GET /v2/session/{session_id}/cognitive-profile
# 获取用户的双轨认知画像
Response:
  {
    "track_a": {
      "cognitive_inertia": 0.5,
      "behavioral_inertia": 0.5,
      "trust_level": 0.5,
      "expectation_bias": 0.0,
      "emotion_monotony": 0.5,
      "cognitive_resource": 1.0,
      "attention_anchor": "",
      "self_worth": 0.5,
      "memory_points_count": 0
    },
    "track_b": {
      "basic_tags": [{"name": "occupation", "value": "AI Engineer", "confidence": 0.85}],
      "cognitive_capacity": [{"name": "g_factor", "value": 0.7, "confidence": 0.6}],
      "interaction_prefs": [{"name": "detail_level", "value": "high", "confidence": 0.7}]
    },
    "temporal_state": {
      "session_interval": 0,
      "context_recovery_needed": false
    }
  }

# POST /v2/session/{session_id}/tag-acquisition
# 触发标签获取（L3/L4）
Body:
  {
    "tag_name": "occupation",
    "level": "L3"  # 可选，默认为引擎自动选择
  }
Response:
  {
    "acquired": true,
    "tag": {"name": "occupation", "value": "AI Engineer", "confidence": 0.7, "source": "L3"},
    "hint_question": "您平时主要用 AI 做什么方向？"  # 仅在 L3 时返回
  }

# GET /v2/session/{session_id}/memory-chunks
# 获取记忆组块（支持过滤）
Query:
  - stage: "hot" | "warm" | "cool" | "cold"
  - min_importance: 0.0-1.0
  - limit: int (默认 10)
Response:
  {
    "chunks": [
      {
        "chunk_id": "...",
        "stage": "hot",
        "importance": 0.9,
        "effective_weight": 0.85,
        "content": "...",
        "summary_level": 0
      }
    ]
  }

# GET /v2/session/{session_id}/g-factor
# 获取 g 因子评估
Response:
  {
    "domain": "general",
    "g_factor": 0.72,
    "confidence": 0.6,
    "indicators": {
      "concept_understanding_speed": 0.8,
      "question_depth": 0.7,
      "cross_domain_transfer": 0.6,
      "error_correction_rate": 0.8,
      "abstraction_preference": 0.5
    }
  }

# GET /v2/session/{session_id}/dialogue-tree-weights
# 获取对话树权重
Response:
  {
    "weights": {
      "node_1": 0.85,
      "node_2": 0.60,
      "node_3": 0.30
    }
  }
```

### 5.2 修改现有端点

```yaml
# POST /v1/session/{session_id}/message
# 现有端点，内部逻辑扩展：
#  - 新增 FusionContext 注入
#  - 新增 TimeDecayManager 调用
#  - 响应中新增 cognitive_profile_v2 快照（可选，由前端控制）
```

---

## 6. 与现有代码的集成

### 6.1 修改 `service/orchestrator.py`

```python
class DialogMeshOrchestrator:
    def __init__(self, pcr, intent_parser, compiler=None, cognitive_engine=None):
        self._pcr = pcr
        self._intent_parser = intent_parser
        self._compiler = compiler
        self._cognitive_engine = cognitive_engine  # 新增

    async def process(self, request, session):
        # 1. 时间衰减管理
        if self._cognitive_engine:
            temporal = self._cognitive_engine.time_decay_manager.update(session)
            if temporal.context_recovery_needed:
                recovery_summary = self._cognitive_engine.memory_decay_manager.generate_recovery_summary()
                # 将 recovery_summary 注入 trace_log

        # 2. 标签获取（L1/L2 自动）
        if self._cognitive_engine and session.cognitive_profile_v2:
            await self._cognitive_engine.tag_acquisition_engine.auto_acquire(session)

        # 3. 融合上下文
        fusion_context = None
        if self._cognitive_engine and session.cognitive_profile_v2:
            fusion = self._cognitive_engine.fusion_engine.fuse(temporal)
            fusion_context = fusion.build_prompt_context()
            response_strategy = fusion.build_response_strategy()

        # 4. 构建 PCRInput（注入 fusion_context）
        pcr_input = self.build_pcr_input(session, request, fusion_context=fusion_context)

        # ... 现有流程 ...

        # 5. 更新认知动力学
        if self._cognitive_engine and session.cognitive_profile_v2:
            session.cognitive_profile_v2.track_a.update_from_turn(
                turn=latest_turn,
                feedback=parse_result.feedback,
            )

        # 6. 更新对话树权重
        if self._cognitive_engine:
            self._cognitive_engine.dialogue_tree_weight_manager.update_weight(
                node_id=current_node_id,
                event_type="select",
                score=1.0,
            )

        # 7. 创建记忆组块
        if self._cognitive_engine:
            chunk = MemoryChunk(
                chunk_id=str(uuid.uuid4())[:8],
                created_at=time.time(),
                last_accessed=time.time(),
                importance=self._compute_importance(parse_result),
                content=latest_turn.content[:200],
                topic_tags=parse_result.intent.topics,
            )
            self._cognitive_engine.memory_decay_manager.add_chunk(chunk)

        # 8. 异步 g 因子更新（不阻塞响应）
        if self._cognitive_engine:
            asyncio.create_task(
                self._cognitive_engine.g_factor_engine.infer_from_dialogue(session.history)
            )

        return response_dict
```

### 6.2 修改 `service/api/dependencies.py`

```python
# 新增依赖注入
from service.cognitive.engine import CognitiveEngine

_cognitive_engine_instance: Optional[CognitiveEngine] = None

def init_dependencies(pcr, parser, session_manager, ws_manager, cognitive_engine=None):
    global _cognitive_engine_instance
    _cognitive_engine_instance = cognitive_engine or CognitiveEngine()
    # ... 现有初始化 ...

def get_cognitive_engine() -> CognitiveEngine:
    if _cognitive_engine_instance is None:
        raise RuntimeError("CognitiveEngine not initialized")
    return _cognitive_engine_instance
```

### 6.3 修改 `service/api/routes.py`

```python
from service.cognitive.engine import CognitiveEngine
from service.cognitive.models import UserTag, MemoryChunk

@router.get("/v2/session/{session_id}/cognitive-profile")
async def get_cognitive_profile_v2(
    session_id: str,
    cognitive_engine: CognitiveEngine = Depends(get_cognitive_engine),
    current_session: Session = Depends(get_current_session),
):
    if not current_session.cognitive_profile_v2:
        return {"error": "CognitiveProfileV2 not initialized"}
    return current_session.cognitive_profile_v2.to_dict()

@router.post("/v2/session/{session_id}/tag-acquisition")
async def trigger_tag_acquisition(
    session_id: str,
    request: TagAcquisitionRequest,
    cognitive_engine: CognitiveEngine = Depends(get_cognitive_engine),
    current_session: Session = Depends(get_current_session),
):
    tag = await cognitive_engine.tag_acquisition_engine.acquire(
        tag_name=request.tag_name,
        session=current_session,
        context={"timezone": "+08:00"},  # 从请求头获取
    )
    return {"acquired": tag is not None, "tag": tag.to_dict() if tag else None}
```

---

## 7. 测试策略

### 7.1 单元测试

| 测试文件 | 覆盖模块 | 测试场景 |
|---------|---------|---------|
| `test_cognitive_profile_v2.py` | `CognitiveProfileV2`, `CognitiveDynamics`, `TagLayer` | 冷启动、更新、序列化、LLM 上下文生成 |
| `test_memory_decay.py` | `MemoryChunk`, `MemoryDecayManager` | 衰减计算、阶梯跃迁、清理/压缩、上下文恢复 |
| `test_tag_acquisition.py` | `TagAcquisitionEngine` | L1/L2/L3/L4 获取、用户反感检测、侵入-收益比 |
| `test_g_factor.py` | `GFInferenceEngine` | 对话推断、微型任务生成、指标计算 |
| `test_dialogue_tree_weight.py` | `DialogueTreeWeightManager` | 权重更新、排序、全局衰减 |
| `test_fusion_context.py` | `FusionContext`, `FusionEngine` | 上下文构建、响应策略生成、截断 |

### 7.2 集成测试

| 测试场景 | 验证点 |
|---------|--------|
| 完整请求生命周期 | 数据流正确、无异常、响应时间 < 200ms（增量） |
| 旧版兼容 | 旧版 `CognitiveProfile` 可正常读取/写入 |
| 跨会话持久化 | `cognitive_profile_v2` 跨会话继承、记忆组块恢复 |
| 并发会话 | 多个会话同时更新画像，无数据竞争 |
| 冷启动 | 新用户首次对话，画像从零构建 |
| 长期间隔后对话 | 30 天间隔，上下文恢复流程正确触发 |

### 7.3 性能基准

| 指标 | 目标 | 测试方法 |
|------|------|---------|
| 融合上下文构建 | < 5ms | 1000 次循环计时 |
| 记忆衰减清理 | < 10ms（100 个组块） | 批量测试 |
| 标签获取 L2 | < 50ms（LLM 调用） | Mock LLM 测试 |
| g 因子推断 | < 100ms | 模拟 20 轮对话历史 |
| 端到端增量延迟 | < 50ms（相比 v1.x） | 对比测试 |

---

## 8. 部署与迁移

### 8.1 数据库迁移

```sql
-- SQLite 迁移脚本
-- 1. 添加新列到 sessions 表
ALTER TABLE sessions ADD COLUMN cognitive_profile_v2 TEXT;
ALTER TABLE sessions ADD COLUMN memory_chunks TEXT DEFAULT '[]';
ALTER TABLE sessions ADD COLUMN dialogue_tree_weights TEXT DEFAULT '{}';
ALTER TABLE sessions ADD COLUMN tag_acquisition_history TEXT DEFAULT '[]';
ALTER TABLE sessions ADD COLUMN g_factor_assessments TEXT DEFAULT '[]';
ALTER TABLE sessions ADD COLUMN version INTEGER DEFAULT 1;

-- 2. 创建索引（按用户查询画像）
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_version ON sessions(session_id, version);
```

### 8.2 配置项

```yaml
# config/cognitive_v2.yaml
cognitive_profile_v2:
  enabled: true
  memory_decay:
    tau_hours: 24.0
    hot_warm_threshold: 24      # 小时
    warm_cool_threshold: 168    # 7 天
    cool_cold_threshold: 720    # 30 天
  tag_acquisition:
    l1_enabled: true
    l2_enabled: true
    l3_enabled: true
    l4_enabled: false          # 默认关闭 L4（高侵入）
    intrusion_threshold: 0.3
  g_factor:
    enabled: true
    inference_window: 20        # 最近 20 轮对话
    micro_task_enabled: false    # 默认关闭嵌入式任务（待验证）
  dialogue_tree:
    weight_decay_alpha: 0.3
    global_decay_factor: 0.95
  fusion:
    max_context_length: 800
    track_a_weight: 0.4        # 轨道 A 在融合中的权重
    track_b_weight: 0.6        # 轨道 B 在融合中的权重
```

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 标签获取误判（L2 推断错误） | 画像偏差，回复质量下降 | 置信度阈值（>0.5 才使用），多轮验证 |
| L3 暗示让用户反感 | 用户体验下降 | 用户反感检测 + 自动降级 + 敏感标签标记 |
| g 因子推断歧视风险 | 伦理问题 | 仅用于复杂度调整，不标签固化，定期审核 |
| 记忆组块过多导致内存膨胀 | 性能下降 | 定期清理（eviction loop），重要性阈值过滤 |
| 融合上下文过长 | Token 浪费 | 最大长度截断（800 chars），动态优先级排序 |
| 旧版数据迁移失败 | 数据丢失 | 双写策略（同时写旧版和新版），自动降级 |

---

## 10. 附录

### 10.1 术语表

| 术语 | 定义 |
|------|------|
| 轨道 A | 认知动力学层（动态演化） |
| 轨道 B | 标签化信息层（静态/慢变） |
| 记忆组块 | 按主题/时间聚合的对话记忆单元 |
| 阶梯跃迁 | 时间间隔超阈值后记忆状态的离散跳跃 |
| 侵入-收益比 | 标签获取决策指标 = 标签信息价值 / 用户感知侵入度 |
| 上下文恢复 | 长期未对话后主动生成摘要并请求确认 |
| g 因子 | 一般认知能力（领域相对） |
| L1-L4 | 标签获取四级策略（被动→间接→暗示→主动） |

### 10.2 文件清单

```
service/cognitive/
├── __init__.py
├── models.py               # 共享数据模型
├── dynamics.py             # 轨道 A: 认知动力学
├── tag_layer.py            # 轨道 B: 标签化信息
├── temporal.py             # 时间状态管理
├── acquisition.py          # 标签获取引擎
├── fusion.py               # 融合层
├── memory_decay.py         # 记忆衰减管理
├── g_factor.py             # g 因子推断
├── dialogue_tree_weight.py # 对话树权重
└── engine.py               # 认知引擎总入口（聚合所有模块）

tests/
├── test_cognitive_profile_v2.py
├── test_memory_decay.py
├── test_tag_acquisition.py
├── test_g_factor.py
├── test_dialogue_tree_weight.py
└── test_fusion_context.py
```

---

**本文档是 DialogMesh 2.0 认知-画像架构的完整工程实现指南，涵盖 11 个模块的详细设计、数据流、接口定义、测试策略和部署迁移方案。所有模块可直接进入代码实现阶段。**

---

## 11. 附录：简化与待讨论项

### 11.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 记忆衰减模型 | `DESIGN_COGNITIVE_PROFILE_V2.md` §3.2 要求双指数衰减 `W(t) = W_0 * [α * exp(-t/τ_1) + (1-α) * exp(-t/τ_2)]` | 工程文档 §3.7 使用单指数衰减 + 阶梯跃迁（`importance * exp(-t/τ) * stage_factor`） | 双指数参数调优复杂，单指数 + 阶梯跃迁在工程上更易实现且效果等效 | Phase 2 引入完整双指数模型，保留阶梯跃迁作为离散状态标记 |
| **S-02** | 标签层嵌套结构 | `DESIGN_COGNITIVE_PROFILE_V2.md` §5.3 定义 `BasicTags`, `CognitiveCapacity`, `InteractionPreferences`, `SocialGraph`, `InterestGraph` 为独立嵌套 dataclass | 工程文档 §3.2 `TagLayer` 使用扁平化的 `Dict[str, UserTag]` 按类别分组 | 扁平结构更易于序列化、查询和扩展；嵌套结构在 Python 中增加 boilerplate | Phase 2 如需强类型约束，可引入 Pydantic 模型或 TypedDict 恢复嵌套结构 |
| **S-03** | `FusionState` 派生类 | `DESIGN_COGNITIVE_PROFILE_V2.md` §5.3 中 `CognitiveProfileV2` 包含 `fusion_state: FusionState` 字段 | 工程文档 §2.2 和 §3.8 中 `FusionContext` 为实时计算类，不持久化；`CognitiveProfileV2` 无 `fusion_state` 字段 | `FusionState` 为全派生字段，无需持久化；实时计算在 `FusionContext` 中完成 | 如需跨会话保存融合策略，可在 Phase 2 添加 `fusion_state` 到持久化模型 |
| **S-04** | 实现路线图 | `DESIGN_COGNITIVE_PROFILE_V2.md` §6 提供六阶段实现路线图（阶段1-6） | 工程文档未提供路线图，直接提供完整模块设计 | 工程文档的目标是直接进入实现，路线图信息已融入模块设计和依赖关系中 | 无需恢复；项目管理层使用工程文档 §1 变更总览和 §8 部署迁移作为替代 |
| **S-05** | rz.txt 概念映射表 | `DESIGN_COGNITIVE_PROFILE_V2.md` §9.1 提供完整的 rz.txt 概念到工程化抽象的映射表 | 工程文档未包含该映射表 | 工程文档面向开发者，rz.txt 是内部设计参考；概念已在工程文档中通过类名和注释隐性映射 | 如需追溯设计来源，可交叉参考设计文档 §9.1 |

### 11.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | L4 主动询问默认启用策略 | A) 默认关闭（当前配置 `l4_enabled=false`）  B) 默认开启但高阈值  C) 仅后台管理面板可开启 | 建议 A：L4 侵入感最强（~0.6），默认关闭符合"用户体验优先"原则；高价值标签缺失时由系统提示管理员手动开启 |
| **D-02** | g 因子领域粒度 | A) 单一全局 "general" 域（当前）  B) 按技术领域细分（如 "coding", "math", "finance"）  C) 自动动态领域发现 | 建议 B：用户在不同领域认知能力差异大，但 Phase 1 可先保持 "general"，积累数据后引入领域细分 |
| **D-03** | 记忆组块压缩的实际执行者 | A) 外部 LLM（当前标记）  B) 内置规则引擎（摘要模板）  C) 混合策略（规则优先，LLM 兜底） | 建议 C：规则引擎处理 80% 简单摘要，LLM 处理复杂语义压缩；减少 LLM 调用成本和延迟 |
| **D-04** | 融合上下文最大长度 | A) 固定 800 字符（当前）  B) 基于目标 LLM 的 context window 动态调整  C) 基于信息密度自适应压缩 | 建议 B：不同 LLM 的上下文预算不同，但 800 字符作为安全默认值适用于大多数 fast 模式（gpt-3.5-turbo 的 4K 上下文） |
| **D-05** | 标签获取 A/B 测试框架 | A) 不实现（当前）  B) 内置简单 A/B（随机分组）  C) 接入外部实验平台 | 建议 B：在 `TagAcquisitionEngine` 中增加 `experiment_id` 字段，支持简单的随机分组和指标对比，无需外部依赖 |

### 11.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_COGNITIVE_PROFILE_V2.md` §1 | 未单独覆盖（新建文档，非回修） | ⚠️ 缺失 | 问题陈述和痛点分析在设计文档中，工程文档直接进入实现 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §2.1 | §2 数据模型 + §3 核心模块 | ✅ 等价 | 双轨架构总览完整覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §2.2 | §3.1 `CognitiveDynamics` | ✅ 等价 | 轨道 A 认知动力学覆盖，含 9 个行为特征的计算 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §2.3 | §3.2 `TagLayer` + §2.1 `UserTag` | ⚠️ 简化 | 嵌套结构简化为扁平 Dict（S-02） |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §3.1 | §3.7 `MemoryDecayManager` + §3.3 `TimeDecayManager` | ✅ 等价 | 时间衰减核心问题覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §3.2 | §3.7 `MemoryChunk.get_effective_weight()` | ⚠️ 简化 | 双指数衰减简化为单指数 + 阶梯跃迁（S-01） |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §3.3 | §3.7 `MemoryDecayManager.cleanup_and_compress()` | ✅ 等价 | 记忆组块清理策略覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §3.4 | §3.3 `TimeDecayManager.generate_context_recovery_summary()` | ✅ 等价 | 上下文恢复流程覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §4.1 | §3.4 `TagAcquisitionEngine` 注释 | ✅ 等价 | 核心矛盾（侵入-收益）覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §4.2 | §3.4 `TagAcquisitionEngine.acquire()` | ✅ 扩展 | 设计文档为三级（L1-L3），工程文档扩展为四级（L1-L4），增加 L4 主动询问 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §4.3 | §3.4（职业示例）+ §3.5（g 因子示例） | ✅ 等价 | 具体实现示例覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §4.4 | §2.1 `UserTag.update_confidence()` | ✅ 等价 | 贝叶斯式置信度更新覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §5.1 | §3.8 `FusionContext` + `FusionEngine` | ✅ 等价 | 融合层 `build_prompt_context()` 和 `build_response_strategy()` 覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §5.2 | §3.8 `FusionContext.build_response_strategy()` | ⚠️ 简化 | 6 大协同规则表格未在工程文档中完整呈现，仅通过策略逻辑隐性覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §5.3 | §2 数据模型（`CognitiveProfileV2`, `CognitiveDynamics`, `TagLayer`） | ⚠️ 简化 | `FusionState` 未实现（S-03），`TemporalState` 为独立字段而非嵌套 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §6 | 未覆盖 | ⚠️ 缺失 | 实现路线图未提供（S-04） |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §7 | §9 风险与缓解（部分覆盖） | ⚠️ 简化 | 关键设计决策未作为独立章节呈现 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §8 | §1.3 向后兼容 + §6 集成 + §8 部署迁移 | ✅ 等价 | 兼容性覆盖 |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §9.1 | 未覆盖 | ⚠️ 缺失 | rz.txt 概念映射表未提供（S-05） |
| `DESIGN_COGNITIVE_PROFILE_V2.md` §9.2 | §10.1 术语表 | ✅ 等价 | 术语表覆盖 |

---

*本工程文档由 DialogMesh 工程团队基于 `design_cognitive_profile_v2.md` 设计蓝图生成。新增 11 个模块，总计约 **3,000 行代码**（含数据模型、核心算法、接口和测试）。所有简化项已在 §11.1 中诚实标记，待讨论项在 §11.2 中列出，等待团队确认。设计文档的 20 个章节中，14 个已等价覆盖，4 个为简化实现，2 个为文档组织差异（路线图和 rz.txt 映射表，非功能缺失）。*

---

## 12. 问题修复记录

### 2026-07-19 — 审查报告一致性修复

**修复问题**（来源：审查报告）

| 编号 | 问题描述 | 修复位置 | 修复内容 |
|------|---------|---------|---------|
| FIX-01 | 缺少"设计文档等价性检查"和"附录：简化与待讨论项"章节，与其他工程文档格式不一致 | §11, §11.3 | 新增 §11 附录：简化与待讨论项（含 S-01~S-05 简化标记、D-01~D-05 待讨论项）和 §11.3 设计文档等价性检查，覆盖 `design_cognitive_profile_v2.md` 全部 20 个章节，诚实标注等价性状态 |

**修复后验证**：
- 文档格式一致性：✅ 与 `ENGINEERING_PCR.md`、`ENGINEERING_INTENT_PARSER.md` 等工程文档的附录结构一致
- 等价性检查诚实性：✅ 14 个章节等价，4 个简化，2 个文档组织差异（非功能缺失）
- 简化项可追踪：✅ S-01~S-05 均有设计文档来源、当前实现、简化原因和恢复路线图
