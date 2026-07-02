# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/__init__.py
──────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文管理器包导出

用途：
- 统一管理对话上下文的存储、检索、窗口截断与压缩。
- 支持多轮会话的上下文继承、跨会话认知树集成。
- 提供内存与持久化双写接口，便于服务层接入 SQLite / Redis。

对外暴露的核心类:
  - ContextManager       上下文管理器主入口
  - ContextWindow        上下文窗口管理器（Token 估算 / 截断 / 压缩）
  - ContextStore         存储抽象基类
  - InMemoryContextStore 内存存储实现
  - SQLiteContextStore   SQLite 持久化实现
  - ContextSnapshot      上下文快照模型
  - ContextSummary       上下文摘要模型
  - WindowConfig         窗口配置模型
  - TruncationStrategy   截断策略枚举

版本: 3.0.0
"""

from core.agent.v3_0.context_manager.models import (
    ContextPriority,
    ContextSlice,
    ContextSnapshot,
    ContextSummary,
    EntityResolutionState,
    WindowConfig,
)
from core.agent.v3_0.context_manager.store import (
    ContextStore,
    InMemoryContextStore,
    SQLiteContextStore,
)
from core.agent.v3_0.context_manager.window import (
    ContextCompressor,
    ContextWindow,
    RelevanceScorer,
    TokenEstimator,
    TruncationStrategy,
)
from core.agent.v3_0.context_manager.manager import ContextManager

__all__ = [
    "ContextManager",
    "ContextWindow",
    "ContextStore",
    "InMemoryContextStore",
    "SQLiteContextStore",
    "ContextSnapshot",
    "ContextSummary",
    "ContextSlice",
    "WindowConfig",
    "EntityResolutionState",
    "ContextPriority",
    "TruncationStrategy",
    "TokenEstimator",
    "ContextCompressor",
    "RelevanceScorer",
]
