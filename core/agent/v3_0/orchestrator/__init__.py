# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/__init__.py
────────────────────────────────────────
DialogMesh Agent v3.0 Orchestrator 包初始化。

用途：
- 导出 Orchestrator 核心类与 SystemBootstrap 启动器。
- 统一入口：process_turn、start_system、health_check。

版本：3.0.0
"""

from __future__ import annotations

from core.agent.v3_0.orchestrator.models import (
    DialogMeshSystem,
    OrchestratorConfig,
    OrchestratorResult,
    SystemHealth,
    TurnContext,
    TurnPhase,
)
from core.agent.v3_0.orchestrator.orchestrator import Orchestrator
from core.agent.v3_0.orchestrator.bootstrap import SystemBootstrap

__version__ = "3.0.0"

__all__ = [
    "Orchestrator",
    "SystemBootstrap",
    "DialogMeshSystem",
    "OrchestratorConfig",
    "OrchestratorResult",
    "TurnContext",
    "TurnPhase",
    "SystemHealth",
]
