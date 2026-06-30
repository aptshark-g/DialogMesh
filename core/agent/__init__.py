# -*- coding: utf-8 -*-
"""
core/agent/__init__.py
─────────────────────
Agent package exports.
"""

from __future__ import annotations

from core.agent.integration_bridge import AgentPipeline

# v2.4 架构修复：新增模块导出（按需导入，默认不自动加载以保持启动速度）
__all__ = [
    "AgentPipeline",
]

# Optional exports for new architecture-gap fixes (lazy-import to avoid
# increasing cold-start time for users who don't use these features):
#   adaptive_threshold  – Bayesian PCR threshold (Gap #9)
#   intent_rule_registry – conflict detection engine (Gap #3)
