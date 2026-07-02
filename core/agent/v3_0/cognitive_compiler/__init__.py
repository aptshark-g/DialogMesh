# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/__init__.py
────────────────────────────────────────────
Cognitive Compiler v3.0 — 包导出

认知编译器是 v3.0 多层 LLM 认知架构的核心枢纽，
负责将 6 个 LLM 实例的推理结果编译为 Cognitive Tree 节点，
管理节点生命周期、边关系、访问控制和事件通知。

对外暴露的核心类:
  - CognitiveCompiler      认知编译器主类
  - CognitiveTreeStore     多会话存储管理器
  - NodeLifecycleManager   节点生命周期管理器
  - EdgeManager            边关系管理器
  - EventBus               异步事件总线
  - Querier                查询与遍历引擎
  - CogEventType           认知事件类型枚举
  - Event                  认知事件
  - Subscription           事件订阅

版本: 3.0.0
"""

from core.agent.v3_0.cognitive_compiler.compiler import (
    CognitiveCompiler,
    CognitiveTreeStore,
)
from core.agent.v3_0.cognitive_compiler.edge_manager import EdgeManager
from core.agent.v3_0.cognitive_compiler.event_bus import (
    CogEventType,
    Event,
    EventBus,
    Subscription,
)
from core.agent.v3_0.cognitive_compiler.lifecycle import NodeLifecycleManager
from core.agent.v3_0.cognitive_compiler.querier import Querier

__all__ = [
    "CognitiveCompiler",
    "CognitiveTreeStore",
    "NodeLifecycleManager",
    "EdgeManager",
    "EventBus",
    "CogEventType",
    "Event",
    "Subscription",
    "Querier",
]
