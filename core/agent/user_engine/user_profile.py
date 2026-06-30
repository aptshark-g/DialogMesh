# core/agent/user_engine/user_profile.py
"""用户画像数据模型 —— 可序列化、可增量更新，支持多维度画像。

Phase 2 扩展维度：
- 情绪/耐心（patience_level: impatient/neutral/patient）
- 纠错频率（correction_count + correction_rate）
- 偏好工具（preferred_tools: Python, VSCode, PyCharm, etc.）
- 注意力跨度（attention_span: short/medium/long，从切换频率推断）
- 话题切换率（topic_switch_rate: 切换次数 / 总轮次）
- 意图连续性（last_intent + consecutive_same_intent）
- 语言偏好（language_preference: zh/en/mixed）

注入方式：
- 旧方式：inject_context() 字符串拼接（保留向后兼容）
- 新方式：get_system_context() 返回结构化字典，用于 system prompt 注入
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PersistentSnapshot:
    """持久化快照 —— 跨会话恢复时必须保存的数据。

    vs RuntimeState（仅内存，新会话重置）：
    - active_task: Optional[Task] = None
    - current_turn_index: int = 0
    - session_start_time: float = 0.0
    """
    user_id: str
    tech_level: str = "unknown"
    domains: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    style: str = "unknown"
    language: str = "zh"
    patience_level: str = "neutral"
    correction_count: int = 0
    correction_rate: float = 0.0
    preferred_tools: List[str] = field(default_factory=list)
    attention_span: str = "medium"
    topic_switch_rate: float = 0.0
    last_intent: str = "unknown"
    consecutive_same_intent: int = 0
    turn_count: int = 0
    task_count: int = 0
    topic_switches: int = 0
    session_count: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    threshold_profile: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PersistentSnapshot:
        return cls(
            user_id=data.get("user_id", "anonymous"),
            tech_level=data.get("tech_level", "unknown"),
            domains=data.get("domains", []),
            entities=data.get("entities", []),
            style=data.get("style", "unknown"),
            language=data.get("language", "zh"),
            patience_level=data.get("patience_level", "neutral"),
            correction_count=data.get("correction_count", 0),
            correction_rate=data.get("correction_rate", 0.0),
            preferred_tools=data.get("preferred_tools", []),
            attention_span=data.get("attention_span", "medium"),
            topic_switch_rate=data.get("topic_switch_rate", 0.0),
            last_intent=data.get("last_intent", "unknown"),
            consecutive_same_intent=data.get("consecutive_same_intent", 0),
            turn_count=data.get("turn_count", 0),
            task_count=data.get("task_count", 0),
            topic_switches=data.get("topic_switches", 0),
            session_count=data.get("session_count", 1),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            threshold_profile=data.get("threshold_profile", None),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UserProfile:
    """用户画像 —— 多维度用户模型。"""

    # ── 基础标识 ──────────────────────────────────────────────────
    user_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ── 核心维度（Phase 1）───────────────────────────────────────
    tech_level: str = "unknown"           # beginner / intermediate / expert / unknown
    domains: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    style: str = "unknown"                # concise / detailed / tutorial / unknown
    language: str = "zh"                  # zh / en / mixed / unknown

    # ── 扩展维度（Phase 2）───────────────────────────────────────
    patience_level: str = "neutral"     # impatient / neutral / patient
    correction_count: int = 0            # 累计纠错次数
    correction_rate: float = 0.0       # 纠错频率（0.0-1.0）
    preferred_tools: List[str] = field(default_factory=list)  # Python, VSCode, PyCharm, etc.
    attention_span: str = "medium"       # short / medium / long
    topic_switch_rate: float = 0.0       # 话题切换频率（0.0-1.0）
    last_intent: str = "unknown"         # 最近检测到的意图
    consecutive_same_intent: int = 0    # 连续相同意图计数

    # ── 统计 ────────────────────────────────────────────────────
    turn_count: int = 0                  # 总交互轮次
    task_count: int = 0                  # 参与过的任务数
    topic_switches: int = 0              # 话题切换次数
    session_count: int = 1               # 会话次数（跨会话累积）

    # ── 自适应阈值（Phase 3）───────────────────────────────────
    threshold_profile: Optional[Dict[str, Any]] = None  # 阈值画像字典（由 ThresholdProfile 管理）

    # ── 元数据 ──────────────────────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── 增量更新 ──────────────────────────────────────────────────

    def _ensure_threshold_profile(self) -> Optional[Any]:
        """确保 threshold_profile 已初始化（懒加载）。"""
        if self.threshold_profile is not None:
            return self.threshold_profile
        try:
            from core.agent.coordinator.adaptive_threshold import ThresholdProfile
            self.threshold_profile = ThresholdProfile(user_id=self.user_id).to_dict()
            return self.threshold_profile
        except ImportError:
            return None

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """从字典增量更新字段。"""
        # 基础维度
        if "tech_level" in data and data["tech_level"] != "unknown":
            self.tech_level = data["tech_level"]
        if "domains" in data:
            for d in data["domains"]:
                if d not in self.domains:
                    self.domains.append(d)
        if "entities" in data:
            for e in data["entities"]:
                if e not in self.entities:
                    self.entities.append(e)
        if "style" in data and data["style"] != "unknown":
            self.style = data["style"]
        if "language" in data and data["language"] != "unknown":
            self.language = data["language"]

        # Phase 2 扩展维度
        if "patience_level" in data and data["patience_level"] != "unknown":
            self.patience_level = data["patience_level"]
        if "preferred_tools" in data:
            for t in data["preferred_tools"]:
                if t not in self.preferred_tools:
                    self.preferred_tools.append(t)
        if "attention_span" in data and data["attention_span"] != "unknown":
            self.attention_span = data["attention_span"]
        if "last_intent" in data:
            self.last_intent = data["last_intent"]

        # 数值更新
        if "correction_count" in data:
            self.correction_count += data["correction_count"]
        if "topic_switches" in data:
            self.topic_switches += data["topic_switches"]
        if "task_count" in data:
            self.task_count += data["task_count"]
        if "turn_count" in data:
            self.turn_count += data["turn_count"]
        if "session_count" in data:
            self.session_count += data["session_count"]

        # 派生指标计算
        self._compute_derived_metrics()

        if "metadata" in data:
            self.metadata.update(data["metadata"])
        self.updated_at = time.time()

    def _compute_derived_metrics(self) -> None:
        """计算派生指标（切换率、纠错率等）。"""
        if self.turn_count > 0:
            self.topic_switch_rate = round(self.topic_switches / self.turn_count, 3)
        if self.turn_count > 0:
            self.correction_rate = round(self.correction_count / self.turn_count, 3)

    # ── 结构化上下文注入（Phase 2 新方式）──────────────────────────

    def get_system_context(self) -> Dict[str, Any]:
        """获取结构化系统上下文（用于注入 LLM system prompt）。

        Returns:
            字典格式，便于 LLM 理解用户偏好
        """
        context = {
            "user_profile": {
                "user_id": self.user_id,
                "tech_level": self.tech_level,
                "domains": self.domains[:5],
                "style": self.style,
                "language": self.language,
            }
        }

        # Phase 2 扩展维度（仅非默认值时添加，减少 token 占用）
        if self.patience_level != "neutral":
            context["user_profile"]["patience_level"] = self.patience_level
        if self.preferred_tools:
            context["user_profile"]["preferred_tools"] = self.preferred_tools[:3]
        if self.attention_span != "medium":
            context["user_profile"]["attention_span"] = self.attention_span
        if self.correction_rate > 0.05:
            context["user_profile"]["correction_rate"] = self.correction_rate
        if self.topic_switch_rate > 0.1:
            context["user_profile"]["topic_switch_rate"] = self.topic_switch_rate
        if self.last_intent != "unknown":
            context["user_profile"]["last_intent"] = self.last_intent

        return context

    def format_system_context(self) -> str:
        """将结构化上下文格式化为 system prompt 字符串。

        格式：JSON 风格，LLM 易于解析
        """
        import json
        ctx = self.get_system_context()
        return json.dumps(ctx, ensure_ascii=False, indent=None)

    # ── 旧方式：字符串拼接（保留向后兼容）──────────────────────────

    def inject_context(self, query: str) -> str:
        """将用户画像注入查询文本（作为上下文前缀）。

        Returns:
            带用户画像前缀的查询文本，用于 HeaderInjector 和 LLM 输入
        """
        parts = []
        if self.tech_level != "unknown":
            parts.append(f"[技术水平:{self.tech_level}]")
        if self.domains:
            parts.append(f"[关注领域:{','.join(self.domains[:3])}]")
        if self.style != "unknown":
            parts.append(f"[偏好风格:{self.style}]")
        if self.preferred_tools:
            parts.append(f"[偏好工具:{','.join(self.preferred_tools[:2])}]")
        if not parts:
            return query
        prefix = "".join(parts)
        return f"{prefix} {query}"

    # ── 统计更新 ──────────────────────────────────────────────────

    def record_turn(self, intent: str = "unknown", is_correction: bool = False, is_switch: bool = False) -> None:
        """记录一轮交互的统计信息。

        Args:
            intent: 本轮意图标签
            is_correction: 是否包含纠错信号
            is_switch: 是否发生话题切换
        """
        self.turn_count += 1

        # 话题切换统计（独立于意图连续性）
        if is_switch:
            self.topic_switches += 1

        # 意图连续性
        if intent == self.last_intent and intent != "unknown":
            self.consecutive_same_intent += 1
        else:
            self.consecutive_same_intent = 0
        self.last_intent = intent

        if is_correction:
            self.correction_count += 1

        # 注意力跨度推断（基于切换频率）
        if self.turn_count > 5:
            rate = self.topic_switches / self.turn_count
            if rate >= 0.4:
                self.attention_span = "short"
            elif rate <= 0.15:
                self.attention_span = "long"
            else:
                self.attention_span = "medium"

        self._compute_derived_metrics()
        self.updated_at = time.time()

    # ── Snapshot 序列化（P0 跨会话一致性修复）──────────────────────

    def to_snapshot(self) -> PersistentSnapshot:
        """生成持久化快照（只包含跨会话恢复数据）。"""
        return PersistentSnapshot(
            user_id=self.user_id,
            tech_level=self.tech_level,
            domains=list(self.domains),
            entities=list(self.entities),
            style=self.style,
            language=self.language,
            patience_level=self.patience_level,
            correction_count=self.correction_count,
            correction_rate=self.correction_rate,
            preferred_tools=list(self.preferred_tools),
            attention_span=self.attention_span,
            topic_switch_rate=self.topic_switch_rate,
            last_intent=self.last_intent,
            consecutive_same_intent=self.consecutive_same_intent,
            turn_count=self.turn_count,
            task_count=self.task_count,
            topic_switches=self.topic_switches,
            session_count=self.session_count,
            created_at=self.created_at,
            updated_at=self.updated_at,
            threshold_profile=self.threshold_profile.copy() if self.threshold_profile else None,
            metadata=dict(self.metadata),
        )

    @classmethod
    def from_snapshot(cls, snapshot: PersistentSnapshot) -> UserProfile:
        """从持久化快照恢复。"""
        return cls(
            user_id=snapshot.user_id,
            tech_level=snapshot.tech_level,
            domains=list(snapshot.domains),
            entities=list(snapshot.entities),
            style=snapshot.style,
            language=snapshot.language,
            patience_level=snapshot.patience_level,
            correction_count=snapshot.correction_count,
            correction_rate=snapshot.correction_rate,
            preferred_tools=list(snapshot.preferred_tools),
            attention_span=snapshot.attention_span,
            topic_switch_rate=snapshot.topic_switch_rate,
            last_intent=snapshot.last_intent,
            consecutive_same_intent=snapshot.consecutive_same_intent,
            turn_count=snapshot.turn_count,
            task_count=snapshot.task_count,
            topic_switches=snapshot.topic_switches,
            session_count=snapshot.session_count,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            threshold_profile=snapshot.threshold_profile.copy() if snapshot.threshold_profile else None,
            metadata=dict(snapshot.metadata),
        )

    # ── 兼容序列化（底层使用 Snapshot）────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """序列化（兼容旧接口，底层使用 Snapshot）。"""
        return self.to_snapshot().__dict__

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserProfile:
        """反序列化（兼容旧接口，底层使用 Snapshot）。"""
        snapshot = PersistentSnapshot.from_dict(data)
        return cls.from_snapshot(snapshot)
