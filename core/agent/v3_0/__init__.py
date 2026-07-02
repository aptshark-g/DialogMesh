# -*- coding: utf-8 -*-
"""
core/agent/v3_0/__init__.py
──────────────────────────
DialogMesh Agent v3.0 包初始化。

版本：3.0.0
"""

from __future__ import annotations

__version__ = "3.0.0"

from core.agent.v3_0.system_bootstrap import SystemBootstrap, DialogMeshSystem, SystemStartupError
from core.agent.v3_0.orchestrator import Orchestrator, OrchestratorResult

__all__ = [
    "SystemBootstrap",
    "DialogMeshSystem",
    "SystemStartupError",
    "Orchestrator",
    "OrchestratorResult",
]
