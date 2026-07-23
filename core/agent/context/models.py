# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/models.py
─────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文管理器数据模型

用途：
- 定义上下文切片、快照、摘要、窗口配置、实体解析状态等数据模型。
- 使用 Pydantic v2 做严格校验与序列化，兼容 FastAPI Schema 生成。
- 所有模型支持异步验证钩子 ``async_validate``。

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    CognitiveProfile_v3,
    Intent_v3,
    UserMessage_v3,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════

class ContextPriority(str, Enum):
    """上下文优先级 — 用于窗口截断时决定保留权重。"""
    SYSTEM = "system"      # 系统指令，最高优先级
    USER_GOAL = "user_goal"  # 用户明确目标
    CLARIFICATION = "clarification"  # 澄清请求与答复
    TASK_RESULT = "task_result"  # 任务执行结果
    INTERMEDIATE = "intermediate"  # 中间推理
    CHITCHAT = "chitchat"  # 闲聊，最低优先级


class TruncationStrategy(str, Enum):
    """截断策略 — 上下文窗口溢出时的丢弃策略。"""
    FIFO = "fifo"                # 先进先出，丢弃最旧消息
    RECENCY = "recency"          # 保留最近 N 条
    RELEVANCE = "relevance"      # 按相关性评分丢弃低分
    SUMMARY = "summary"          # 将旧内容压缩为摘要后丢弃原文
    HYBRID = "hybrid"            # 混合：先 FIFO 到阈值，再 SUMMARY


# ═══════════════════════════════════════════════════════════════════════════
# 基础模型
# ═══════════════════════════════════════════════════════════════════════════

class WindowConfig(BaseModel):
    """窗口配置 — 控制上下文窗口的行为参数。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    max_tokens: int = Field(default=4096, ge=256)
    token_reserve: int = Field(default=512, ge=0)  # 为响应预留的 token 数
    strategy: TruncationStrategy = TruncationStrategy.HYBRID
    enable_compression: bool = True
    compression_threshold: int = Field(default=2048, ge=0)  # 超过此 token 数触发压缩
    max_history_messages: int = Field(default=100, ge=1)
    min_messages_to_keep: int = Field(default=4, ge=1)
    summary_interval: int = Field(default=10, ge=1)  # 每 N 轮生成一次摘要

    @field_validator("token_reserve", mode="before")
    @classmethod
    def _reserve_not_exceed_max(cls, v: int, info) -> int:
        """确保预留 token 不超过 max_tokens 的 50%。"""
        try:
            max_tokens = info.data.get("max_tokens", 4096)
            return min(int(v), max_tokens // 2)
        except Exception as exc:
            logger.warning(f"token_reserve validation error ({exc}), defaulting to 512")
            return 512

    @property
    def effective_max_tokens(self) -> int:
        """实际可用于上下文的最大 token 数。"""
        return max(0, self.max_tokens - self.token_reserve)


class ContextSlice(BaseModel):
    """上下文切片 — 某个时间窗口内的消息、意图与元数据。

    对应设计文档: 将线性对话历史切分为可管理的块。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    slice_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    messages: List[Union[AgentMessage_v3, UserMessage_v3]] = Field(default_factory=list)
    intents: List[Intent_v3] = Field(default_factory=list)
    priority: ContextPriority = ContextPriority.INTERMEDIATE
    tags: Set[str] = Field(default_factory=set)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    token_estimate: int = Field(default=0, ge=0)

    def append_message(self, msg: Union[AgentMessage_v3, UserMessage_v3]) -> None:
        """追加消息到切片。"""
        self.messages.append(msg)
        self._recalculate_tokens()

    def append_intent(self, intent: Intent_v3) -> None:
        """追加意图到切片。"""
        self.intents.append(intent)

    def _recalculate_tokens(self) -> None:
        """重新估算 token 数（基于字符数 / 4 的启发式）。"""
        try:
            total_chars = 0
            for msg in self.messages:
                content = getattr(msg, "content", "")
                total_chars += len(content)
            for intent in self.intents:
                total_chars += len(intent.raw_input) + len(intent.normalized_input)
            self.token_estimate = total_chars // 4
        except Exception as exc:
            logger.error(f"ContextSlice token recalculation failed: {exc}")

    def to_prompt_text(self) -> str:
        """将切片转换为 prompt 文本（按角色拼接）。"""
        lines: List[str] = []
        for msg in self.messages:
            role = getattr(msg, "role", None)
            role_str = role.value if role else "unknown"
            lines.append(f"[{role_str.upper()}]: {msg.content}")
        return "\n".join(lines)


class ContextSummary(BaseModel):
    """上下文摘要 — 对多个 ContextSlice 的高层压缩表示。

    用于长时间会话中替代被丢弃的旧切片，保留关键目标、实体与决策。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    text: str = ""  # 摘要文本（如 "用户希望扫描 0x1000 附近的内存，已找到 3 个候选地址"）
    key_entities: Dict[str, Any] = Field(default_factory=dict)  # 关键实体快照
    key_decisions: List[str] = Field(default_factory=list)  # 关键决策列表
    source_slice_ids: List[str] = Field(default_factory=list)  # 来源切片 ID
    token_estimate: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def to_prompt_text(self) -> str:
        """转换为 prompt 中的 summary 文本。"""
        parts: List[str] = [f"[SUMMARY]: {self.text}"]
        if self.key_entities:
            parts.append(f"Key entities: {self.key_entities}")
        if self.key_decisions:
            parts.append(f"Key decisions: {self.key_decisions}")
        return "\n".join(parts)


class EntityResolutionState(BaseModel):
    """实体解析状态 — 会话中已解析、待澄清、已失效的实体追踪。

    与 v2.x 的 resolved_entities 语义兼容，但增加生命周期与溯源。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    entity_type: str
    value: Any
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = "resolved"  # resolved, pending, ambiguous, invalidated
    source_intent_id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)  # 变更历史
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=time.time)

    def update_value(self, new_value: Any, new_confidence: float, intent_id: str) -> None:
        """更新实体值并记录历史。"""
        try:
            self.history.append({
                "from": self.value,
                "to": new_value,
                "confidence": new_confidence,
                "intent_id": intent_id,
                "at": time.time(),
            })
            self.value = new_value
            self.confidence = new_confidence
            self.source_intent_id = intent_id
            self.updated_at = time.time()
        except Exception as exc:
            logger.error(f"EntityResolutionState update_value failed: {exc}")
            raise


class ContextSnapshot(BaseModel):
    """上下文快照 — 用于保存 / 恢复会话的完整上下文状态。

    可序列化为 JSON 存入持久化层，支持跨进程恢复。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    slices: List[ContextSlice] = Field(default_factory=list)
    summaries: List[ContextSummary] = Field(default_factory=list)
    entity_states: List[EntityResolutionState] = Field(default_factory=list)
    cognitive_profile: Optional[CognitiveProfile_v3] = None
    window_config: WindowConfig = Field(default_factory=WindowConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    @property
    def total_token_estimate(self) -> int:
        """估算当前快照的总 token 数。"""
        try:
            slice_tokens = sum(s.token_estimate for s in self.slices)
            summary_tokens = sum(s.token_estimate for s in self.summaries)
            return slice_tokens + summary_tokens
        except Exception as exc:
            logger.error(f"total_token_estimate failed: {exc}")
            return 0

    async def async_validate(self) -> None:
        """异步验证：确保 slices 与 summaries 的 session_id 一致。"""
        try:
            await asyncio.sleep(0)
            for s in self.slices:
                if s.session_id != self.session_id:
                    raise ValueError(
                        f"Slice {s.slice_id} session_id mismatch: "
                        f"{s.session_id} != {self.session_id}"
                    )
            for summary in self.summaries:
                if summary.session_id != self.session_id:
                    raise ValueError(
                        f"Summary {summary.summary_id} session_id mismatch: "
                        f"{summary.session_id} != {self.session_id}"
                    )
        except Exception as exc:
            logger.error(f"ContextSnapshot async_validate failed: {exc}")
            raise
