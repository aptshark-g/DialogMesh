# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_tree/models.py
────────────────────────────────────────
Cognitive Tree v3.0 — 数据模型定义

定义 LLM 心智空间的核心数据结构：认知节点、认知边、访问控制矩阵。
对应工程文档: ENGINEERING_DATA_MODEL.md §12
对应设计文档: DESIGN_MULTILAYER_LLM_COGNITIVE.md §4.2

版本: 3.0.0
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# 引用现有核心模型（保持与上层系统的一致性）
from core.agent.models import IntentCategory, EntityType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class CogType(Enum):
    """认知节点类型 — 设计文档 §4.2.2"""
    PERCEPTION = "perception"      # 对外部输入的感知
    HYPOTHESIS = "hypothesis"      # 对当前状态的假设
    REASONING = "reasoning"        # 中间推理过程
    DECISION = "decision"          # 最终决策
    ACTION = "action"            # 产生的行动记录
    OBSERVATION = "observation"    # 行动结果的观察
    REFLECTION = "reflection"      # 对前述认知的反思
    VALIDATION = "validation"      # 对认知的验证结果
    LEARNING = "learning"        # 长期学习结论
    COMMUNICATION = "communication"  # LLM 间通信消息


class CogNodeStatus(Enum):
    """认知节点生命周期状态"""
    CREATED = "created"          # 刚创建，未验证
    ACTIVE = "active"            # 被采纳，正在影响决策
    VALIDATED = "validated"      # 验证通过
    INVALIDATED = "invalidated"  # 验证失败
    SUPERSEDED = "superseded"    # 被新版本替代
    ARCHIVED = "archived"        # 已归档


class CogEdgeType(Enum):
    """认知边类型 — 设计文档 §4.2.2"""
    DERIVES = "derives"          # 推导: A → B
    SUPPORTS = "supports"        # 支持: A ← B
    CONTRADICTS = "contradicts"  # 矛盾: A ↔ B
    CONDITIONAL = "conditional"  # 条件: A ⇒ B
    ALTERNATIVE = "alternative"  # 备选: A ∥ B
    REFINES = "refines"          # 细化: A ⊃ B
    SUMMARIZES = "summarizes"    # 摘要: A ⊂ B
    CROSS_REF = "cross_ref"      # 跨引用: A ~~ B


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class CognitiveTreeNode:
    """认知节点 — LLM 心智空间中的单个认知事件

    对应工程文档: ENGINEERING_DATA_MODEL.md §12.1
    """

    node_id: str = field(
        default_factory=lambda: f"C-{uuid.uuid4().hex[:8]}"
    )

    # 认知类型与来源
    cog_type: CogType = CogType.REASONING
    source_llm: str = ""           # 产生此节点的 LLM 实例，如 "Planning-LLM"

    # 时间戳
    timestamp: float = field(default_factory=time.time)

    # 内容与置信度
    content: str = ""              # 认知内容（推理文本、决策理由、反思）
    confidence: float = 0.5          # 该认知的置信度 [0, 1]

    # 证据与行动
    evidence: List[str] = field(default_factory=list)     # 引用的其他节点 ID 或外部数据源
    action: Optional[str] = None     # 由此认知产生的行动描述
    action_result: Optional[str] = None  # 行动结果

    # 状态
    status: CogNodeStatus = CogNodeStatus.CREATED

    # 元认知层
    reflections: List[str] = field(default_factory=list)   # 反思列表（Meta-Cognitive 添加）
    validations: List[str] = field(default_factory=list)   # 验证结果
    version_history: List[str] = field(default_factory=list)  # 内容历史版本
    cross_refs: List[str] = field(default_factory=list)    # 跨会话硬拷贝节点 ID

    # 性能与元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 示例: {"latency_ms": 150, "token_cost": 500, "model_version": "gpt-4o"}

    # 交叉引用（Topic Tree）
    topic_refs: List[str] = field(default_factory=list)  # 引用的 Topic Tree 节点 ID

    # 内部追踪
    parent_id: Optional[str] = None  # 逻辑父节点（用于快速树遍历）
    depth: int = 0                   # 节点在树中的深度

    def __post_init__(self) -> None:
        """初始化后校验"""
        try:
            if not (0.0 <= self.confidence <= 1.0):
                self.confidence = max(0.0, min(1.0, self.confidence))
        except Exception as e:
            logger.warning("CognitiveTreeNode 置信度校验失败: %s", e)

    # ── 元认知操作 ──────────────────────────────────────

    def add_reflection(self, reflection: str) -> None:
        """添加一条反思记录"""
        self.reflections.append(reflection)

    def add_validation(self, validation: str) -> None:
        """添加一条验证结果"""
        self.validations.append(validation)

    def add_evidence(self, evidence_ref: str) -> None:
        """添加一条证据引用"""
        self.evidence.append(evidence_ref)

    def create_version(self, new_content: str) -> str:
        """创建新版本，记录历史，并返回旧内容

        对应设计文档: 旧版本标记为 superseded 的语义，
        这里将旧内容存入 version_history，当前内容更新。
        """
        try:
            old_content = self.content
            self.version_history.append(old_content)
            self.content = new_content
            return old_content
        except Exception as e:
            logger.error("create_version 失败: %s", e)
            raise

    def update_status(self, new_status: CogNodeStatus) -> None:
        """更新节点状态，并记录状态变更到元数据"""
        try:
            old_status = self.status
            self.status = new_status
            if "status_history" not in self.metadata:
                self.metadata["status_history"] = []
            self.metadata["status_history"].append({
                "from": old_status.value,
                "to": new_status.value,
                "at": time.time(),
            })
        except Exception as e:
            logger.error("update_status 失败: %s", e)
            raise

    # ── 序列化 ───────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "node_id": self.node_id,
            "cog_type": self.cog_type.value,
            "source_llm": self.source_llm,
            "timestamp": self.timestamp,
            "content": self.content,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "action": self.action,
            "action_result": self.action_result,
            "status": self.status.value,
            "reflections": list(self.reflections),
            "validations": list(self.validations),
            "version_history": list(self.version_history),
            "cross_refs": list(self.cross_refs),
            "metadata": dict(self.metadata),
            "topic_refs": list(self.topic_refs),
            "parent_id": self.parent_id,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveTreeNode":
        """从字典反序列化"""
        try:
            return cls(
                node_id=d.get("node_id", f"C-{uuid.uuid4().hex[:8]}"),
                cog_type=CogType(d.get("cog_type", "reasoning")),
                source_llm=d.get("source_llm", ""),
                timestamp=d.get("timestamp", time.time()),
                content=d.get("content", ""),
                confidence=d.get("confidence", 0.5),
                evidence=list(d.get("evidence", [])),
                action=d.get("action"),
                action_result=d.get("action_result"),
                status=CogNodeStatus(d.get("status", "created")),
                reflections=list(d.get("reflections", [])),
                validations=list(d.get("validations", [])),
                version_history=list(d.get("version_history", [])),
                cross_refs=list(d.get("cross_refs", [])),
                metadata=dict(d.get("metadata", {})),
                topic_refs=list(d.get("topic_refs", [])),
                parent_id=d.get("parent_id"),
                depth=d.get("depth", 0),
            )
        except Exception as e:
            logger.error("CognitiveTreeNode.from_dict 失败: %s", e)
            raise

    def __repr__(self) -> str:
        return (
            f"CognitiveTreeNode({self.node_id}, "
            f"type={self.cog_type.value}, "
            f"status={self.status.value}, "
            f"llm={self.source_llm!r})"
        )


@dataclass(frozen=False)
class CognitiveTreeEdge:
    """认知边 — 连接两个认知节点，表示推理关系

    对应工程文档: ENGINEERING_DATA_MODEL.md §12.3
    """

    edge_id: str = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )
    source_id: str = ""
    target_id: str = ""
    edge_type: CogEdgeType = CogEdgeType.DERIVES
    weight: float = 1.0              # 依赖强度 [0, 1]
    condition: Optional[str] = None   # 条件表达式（如 "如果验证通过"）
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """初始化后校验"""
        try:
            if not (0.0 <= self.weight <= 1.0):
                self.weight = max(0.0, min(1.0, self.weight))
        except Exception as e:
            logger.warning("CognitiveTreeEdge 权重校验失败: %s", e)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "condition": self.condition,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveTreeEdge":
        try:
            return cls(
                edge_id=d.get("edge_id", str(uuid.uuid4())[:8]),
                source_id=d.get("source_id", ""),
                target_id=d.get("target_id", ""),
                edge_type=CogEdgeType(d.get("edge_type", "derives")),
                weight=d.get("weight", 1.0),
                condition=d.get("condition"),
                metadata=dict(d.get("metadata", {})),
                created_at=d.get("created_at", time.time()),
            )
        except Exception as e:
            logger.error("CognitiveTreeEdge.from_dict 失败: %s", e)
            raise

    def __repr__(self) -> str:
        return (
            f"CognitiveTreeEdge({self.edge_id}, "
            f"{self.source_id} -> {self.target_id}, "
            f"type={self.edge_type.value})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 访问控制模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class LLMPermissions:
    """单个 LLM 实例对 Cognitive Tree 的访问权限

    对应工程文档: ENGINEERING_DATA_MODEL.md §12.4
    """

    llm_name: str = ""
    can_create: Set[CogType] = field(default_factory=set)
    can_read: Set[str] = field(default_factory=set)    # "all" 或节点类型值列表
    can_update: Set[str] = field(default_factory=set)  # "own" 或 "all"
    can_delete: Set[str] = field(default_factory=set)  # "own" 或 "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_name": self.llm_name,
            "can_create": [c.value for c in self.can_create],
            "can_read": list(self.can_read),
            "can_update": list(self.can_update),
            "can_delete": list(self.can_delete),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LLMPermissions":
        try:
            return cls(
                llm_name=d.get("llm_name", ""),
                can_create={CogType(c) for c in d.get("can_create", [])},
                can_read=set(d.get("can_read", [])),
                can_update=set(d.get("can_update", [])),
                can_delete=set(d.get("can_delete", [])),
            )
        except Exception as e:
            logger.error("LLMPermissions.from_dict 失败: %s", e)
            raise


@dataclass(frozen=False)
class AccessControlMatrix:
    """LLM 实例对 Cognitive Tree 的访问权限矩阵

    默认权限配置见设计文档 §6.2
    """

    permissions: Dict[str, LLMPermissions] = field(default_factory=dict)

    # 默认权限配置（类级别常量）
    DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "PCR-LLM": {
                "can_create": ["perception", "hypothesis"],
                "can_read": ["all"],
                "can_update": ["own"],
                "can_delete": ["none"],
            },
            "Intent-LLM": {
                "can_create": ["hypothesis", "reasoning"],
                "can_read": ["all"],
                "can_update": ["own"],
                "can_delete": ["none"],
            },
            "Planning-LLM": {
                "can_create": ["reasoning", "decision", "action"],
                "can_read": ["all"],
                "can_update": ["own"],
                "can_delete": ["none"],
            },
            "Meta-Cognitive-LLM": {
                "can_create": ["validation", "reflection"],
                "can_read": ["all"],
                "can_update": ["all"],  # 可修改所有节点的 status
                "can_delete": ["none"],
            },
            "Reflective-LLM": {
                "can_create": ["learning", "reflection"],
                "can_read": ["all"],
                "can_update": ["none"],  # 只读
                "can_delete": ["none"],
            },
            "Answer-LLM": {
                "can_create": ["hypothesis"],
                "can_read": ["all"],
                "can_update": ["own"],
                "can_delete": ["none"],
            },
        }
    )

    def __post_init__(self) -> None:
        """若 permissions 为空，初始化默认权限"""
        try:
            if not self.permissions:
                self._load_defaults()
        except Exception as e:
            logger.error("AccessControlMatrix 初始化失败: %s", e)

    def _load_defaults(self) -> None:
        """加载默认权限配置"""
        for llm_name, config in self.DEFAULT_CONFIG.items():
            self.permissions[llm_name] = LLMPermissions.from_dict(
                {"llm_name": llm_name, **config}
            )

    def check_create(self, llm_name: str, cog_type: CogType) -> bool:
        """检查 LLM 是否有权限创建某类型的认知节点"""
        perms = self.permissions.get(llm_name)
        if not perms:
            logger.warning("未找到 LLM 权限配置: %s", llm_name)
            return False
        return cog_type in perms.can_create

    def check_read(self, llm_name: str, node_id: str) -> bool:
        """检查 LLM 是否有权限读取某节点

        简化策略: 若 can_read 包含 "all"，则允许读取任何节点
        """
        perms = self.permissions.get(llm_name)
        if not perms:
            return False
        if "all" in perms.can_read:
            return True
        # 精细化控制可在此处扩展（如按节点类型过滤）
        return False

    def check_update(self, llm_name: str, node_id: str, node_creator: str = "") -> bool:
        """检查 LLM 是否有权限更新某节点

        Args:
            node_creator: 节点的创建者 LLM 名称，用于 own 判断
        """
        perms = self.permissions.get(llm_name)
        if not perms:
            return False
        if "all" in perms.can_update:
            return True
        if "own" in perms.can_update and llm_name == node_creator:
            return True
        return False

    def check_delete(self, llm_name: str, node_id: str, node_creator: str = "") -> bool:
        """检查 LLM 是否有权限删除某节点"""
        perms = self.permissions.get(llm_name)
        if not perms:
            return False
        if "all" in perms.can_delete:
            return True
        if "own" in perms.can_delete and llm_name == node_creator:
            return True
        return False

    def get_allowed_types(self, llm_name: str) -> Set[str]:
        """获取某 LLM 可以创建的节点类型列表（字符串值）"""
        perms = self.permissions.get(llm_name)
        if not perms:
            return set()
        return {t.value for t in perms.can_create}

    def register_llm(self, llm_name: str, permissions: LLMPermissions) -> None:
        """注册或更新 LLM 权限配置"""
        self.permissions[llm_name] = permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "permissions": {
                k: v.to_dict() for k, v in self.permissions.items()
            }
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AccessControlMatrix":
        try:
            perms = {}
            for k, v in d.get("permissions", {}).items():
                perms[k] = LLMPermissions.from_dict(v)
            return cls(permissions=perms)
        except Exception as e:
            logger.error("AccessControlMatrix.from_dict 失败: %s", e)
            raise
