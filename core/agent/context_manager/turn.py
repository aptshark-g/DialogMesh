# core/agent/context_manager/turn.py
"""Turn 数据模型 —— 将用户输入的"轮次"与"话语块"分离。

核心设计：
- Turn: 用户的一次完整输入（不可修改的原始查询）
- ContextBlock: 系统注入的上下文（独立字段，不污染原始查询）
- DiscourseBlock: 话语分割结果（引用 Turn 的原始查询）

数据流：
    user_query → Turn(raw_query=query) → 系统添加上下文 → 话语分割 → 组装输出

vs 旧架构：
    user_query → inject_prefix + query → 污染后的字符串进入所有下游
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextBlock:
    """系统注入的上下文块 —— 结构化数据，不进入原始查询。"""
    type: str  # "user_profile" | "task_progress" | "system_prompt" | "retrieval"
    content: Any  # 结构化内容（Dict / List / str）
    priority: int = 0  # 渲染优先级（高值优先）
    source: str = "system"  # 来源标识

    def to_text(self, format: str = "json") -> str:
        """转换为文本表示（用于 LLM 输入）。"""
        if format == "json":
            import json
            return f"[{self.type}] {json.dumps(self.content, ensure_ascii=False)}"
        elif format == "yaml":
            import yaml
            return f"[{self.type}]\n{yaml.dump(self.content, allow_unicode=True)}"
        else:
            return f"[{self.type}] {str(self.content)}"


@dataclass
class TurnMeta:
    """Turn 的元数据（每轮一次）。"""
    turn_index: int = 0
    timestamp: float = 0.0
    router_mode: Optional[str] = None
    user_profile_snapshot: Dict[str, Any] = field(default_factory=dict)
    task_snapshot: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0


@dataclass
class Turn:
    """用户输入的一轮完整交互。

    不可变性约束：
    - raw_query: 创建后不可修改（防止注入污染）
    - context_blocks: 系统追加，不进入原始查询
    - discourse_blocks: 话语分割结果，引用原始查询

    使用方式：
        turn = Turn(turn_index=0, raw_query="帮我写Python")
        turn.context_blocks.append(ContextBlock(type="user_profile", content={...}))
        turn.discourse_blocks = pipeline.split_blocks(turn.raw_query)  # 在干净文本上分割
    """
    turn_index: int
    raw_query: str
    context_blocks: List[ContextBlock] = field(default_factory=list)
    discourse_blocks: List[Any] = field(default_factory=list)
    metadata: TurnMeta = field(default_factory=TurnMeta)
    router_context: Optional[Dict[str, Any]] = None  # 给路由器的结构化上下文
    consistency_adjusted: bool = False  # 是否经过一致性校验
    topic_id: int = 0  # 所属话题分支 ID（0=根话题）

    def __post_init__(self):
        if self.metadata.timestamp == 0.0:
            import time
            self.metadata.timestamp = time.time()
        self.metadata.turn_index = self.turn_index

    @property
    def clean_text(self) -> str:
        """获取干净的原始查询文本（用于语义搜索、NER、任务检测）。"""
        return self.raw_query

    @property
    def rendered_text(self) -> str:
        """获取完整的渲染文本（包含所有上下文，用于 LLM 输入）。"""
        parts = []
        # 按优先级排序上下文块
        sorted_blocks = sorted(self.context_blocks, key=lambda b: b.priority, reverse=True)
        for block in sorted_blocks:
            parts.append(block.to_text())
        parts.append(self.raw_query)
        return "\n".join(parts)

    def add_context(self, block: ContextBlock) -> None:
        """安全地添加上下文块。"""
        self.context_blocks.append(block)

    def get_context_by_type(self, type_name: str) -> List[ContextBlock]:
        """按类型获取上下文块。"""
        return [b for b in self.context_blocks if b.type == type_name]

    def to_dict(self) -> Dict[str, Any]:
        """序列化（用于调试）。"""
        return {
            "turn_index": self.turn_index,
            "raw_query": self.raw_query,
            "context_blocks": [
                {"type": b.type, "content": b.content, "priority": b.priority}
                for b in self.context_blocks
            ],
            "metadata": {
                "turn_index": self.metadata.turn_index,
                "timestamp": self.metadata.timestamp,
                "router_mode": self.metadata.router_mode,
            },
            "discourse_count": len(self.discourse_blocks),
        }
