# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_tree/__init__.py
────────────────────────────────────────
Cognitive Tree v3.0 — 包导出

对外暴露的核心类:
  - CognitiveTreeNode    认知节点
  - CognitiveTreeEdge    认知边
  - CognitiveTree        认知树管理器
  - CrossRefManager      交叉引用管理器
  - AccessControlMatrix  访问控制矩阵
  - LLMPermissions       LLM 权限配置
  - CogType              认知节点类型枚举
  - CogNodeStatus        认知节点状态枚举
  - CogEdgeType          认知边类型枚举

版本: 3.0.0
"""

from core.agent.v3_0.cognitive_tree.models import (
    AccessControlMatrix,
    CognitiveTreeEdge,
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
    CogType,
    LLMPermissions,
)
from core.agent.v3_0.cognitive_tree.manager import CognitiveTree
from core.agent.v3_0.cognitive_tree.cross_ref import CrossRefManager

__all__ = [
    "CognitiveTreeNode",
    "CognitiveTreeEdge",
    "CognitiveTree",
    "CrossRefManager",
    "AccessControlMatrix",
    "LLMPermissions",
    "CogType",
    "CogNodeStatus",
    "CogEdgeType",
]
