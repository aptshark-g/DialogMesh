# -*- coding: utf-8 -*-
"""
core/agent/v3_0/__init__.py
──────────────────────────
DialogMesh Agent v3.0 包初始化。

版本：3.0.0
"""

from __future__ import annotations

__version__ = "3.0.0"

# system_bootstrap moved to un_use/ — no longer auto-imported

__all__ = [
    "SystemBootstrap",
    "DialogMeshSystem",
    "SystemStartupError",
    "Orchestrator",
    "OrchestratorResult",
]
