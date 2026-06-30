# -*- coding: utf-8 -*-
"""
core/agent/topic_tree/models.py
──────────────────────────────
Topic tree / graph data models.

设计要点：
  - TopicNode: 树节点，含父节点、实体、轮次、本地画像
  - TopicEdge: 图边，支持多种关系类型
  - 双结构：树投影（推理层） + 图关联（记忆层）
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TopicEdgeType(Enum):
    """话题边类型。"""
    PARENT_CHILD = "parent_child"      # 树结构：父 → 子
    ENTITY_REFERENCE = "entity_reference"  # 图结构：共享实体引用
    SIMILARITY = "similarity"          # 图结构：语义相似
    USER_LINK = "user_link"            # 图结构：用户主动关联
    TEMPORAL = "temporal"              # 图结构：时间顺序


@dataclass(frozen=False)
class TopicNode:
    """话题节点 — 树结构中的节点。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    name: str = ""                    # 话题名称（如"内存扫描"）
    description: str = ""             # 话题描述

    # 实体集合
    entities: List[Dict[str, Any]] = field(default_factory=list)
    # 关联的轮次
    turn_ids: List[int] = field(default_factory=list)
    # 本地画像（继承父节点但可覆盖）
    local_profile: Dict[str, Any] = field(default_factory=dict)
    # 深度（树根 = 0）
    depth: int = 0
    # 活跃度（最近使用时间戳）
    last_active_at: float = field(default_factory=time.time)
    # 创建时间
    created_at: float = field(default_factory=time.time)
    # 子节点列表
    children_ids: List[str] = field(default_factory=list)
    # 元数据（用于路径压缩标记等）
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── V2 极致化增强字段 ──────────────────────────────────────
    # 语义向量 (embedding 相似度计算)
    embedding: Optional[List[float]] = None
    # 意图类别 (ADVISOR/DIRECTIVE/QUERY/COMPANION/TOOL/FALLBACK)
    intent_category: str = ""
    # 节点自动摘要 (1-2句，用于跨话题上下文构建)
    summary: str = ""
    # 分支标识 (支持同一话题下多分支并行)
    branch_id: Optional[str] = None
    # 状态快照 (用于跨话题上下文继承)
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    # 合并元数据 (三路合并时记录冲突/解决状态)
    merge_metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "description": self.description,
            "entities": self.entities,
            "turn_ids": self.turn_ids,
            "local_profile": self.local_profile,
            "depth": self.depth,
            "last_active_at": self.last_active_at,
            "created_at": self.created_at,
            "children_ids": self.children_ids,
            "metadata": self.metadata,
            # V2 fields
            "embedding": self.embedding,
            "intent_category": self.intent_category,
            "summary": self.summary,
            "branch_id": self.branch_id,
            "state_snapshot": self.state_snapshot,
            "merge_metadata": self.merge_metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TopicNode":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            parent_id=d.get("parent_id"),
            name=d.get("name", ""),
            description=d.get("description", ""),
            entities=d.get("entities", []),
            turn_ids=d.get("turn_ids", []),
            local_profile=d.get("local_profile", {}),
            depth=d.get("depth", 0),
            last_active_at=d.get("last_active_at", time.time()),
            created_at=d.get("created_at", time.time()),
            children_ids=d.get("children_ids", []),
            metadata=d.get("metadata", {}),
            # V2 fields
            embedding=d.get("embedding"),
            intent_category=d.get("intent_category", ""),
            summary=d.get("summary", ""),
            branch_id=d.get("branch_id"),
            state_snapshot=d.get("state_snapshot", {}),
            merge_metadata=d.get("merge_metadata"),
        )

    def __repr__(self) -> str:
        return f"TopicNode({self.id}, {self.name!r}, depth={self.depth})"


@dataclass(frozen=False)
class TopicEdge:
    """话题边 — 图结构中的边。"""
    source_id: str
    target_id: str
    edge_type: TopicEdgeType = TopicEdgeType.ENTITY_REFERENCE
    weight: float = 1.0               # 关联强度 (0-1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TopicEdge":
        return cls(
            source_id=d["source_id"],
            target_id=d["target_id"],
            edge_type=TopicEdgeType(d.get("edge_type", "entity_reference")),
            weight=d.get("weight", 1.0),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", time.time()),
        )

    def __repr__(self) -> str:
        return f"TopicEdge({self.source_id} -> {self.target_id}, {self.edge_type.value})"
