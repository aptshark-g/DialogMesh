# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/__init__.py
──────────────────────────────────────────
DialogMesh v3.0 Tool Registry 包入口。

导出的所有符号按功能分组：
  - 数据模型（models）
  - 注册中心（registry）
  - 执行器（executor）
  - 筛选器（shortlister）
  - 绑定引擎（binding）
  - 发现模块（discovery）
  - 权限管理（permission）

版本：3.0.0
"""

from __future__ import annotations

from core.agent.v3_0.tool_registry.models import (
    BindingResult,
    BindingStrategy,
    ShortlistResult,
    ToolCall,
    ToolDefinition,
    ToolExecutionStats,
    ToolResult,
    ToolSource,
    ToolType,
)
from core.agent.v3_0.tool_registry.registry import ToolRegistry
from core.agent.v3_0.tool_registry.executor import ToolExecutor
from core.agent.v3_0.tool_registry.shortlister import ToolShortlister
from core.agent.v3_0.tool_registry.binding import ToolBindingEngine
from core.agent.v3_0.tool_registry.discovery import ToolDiscovery
from core.agent.v3_0.tool_registry.permission import PermissionManager

__version__ = "3.0.0"

__all__ = [
    # 数据模型
    "BindingResult",
    "BindingStrategy",
    "ShortlistResult",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutionStats",
    "ToolResult",
    "ToolSource",
    "ToolType",
    # 注册中心
    "ToolRegistry",
    # 执行器
    "ToolExecutor",
    # 筛选器
    "ToolShortlister",
    # 绑定引擎
    "ToolBindingEngine",
    # 发现模块
    "ToolDiscovery",
    # 权限管理
    "PermissionManager",
]
