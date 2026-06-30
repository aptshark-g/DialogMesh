# -*- coding: utf-8 -*-
"""
core/agent/context_window/__init__.py
───────────────────────────────────
增量式上下文窗口管理入口。

只导出 context_window/ 目录下的组件（增量管理 API）。
批量压缩 API（ContextWindowManager, HierarchicalCompressor）在 window/ 目录下。
"""

from __future__ import annotations

from core.agent.context_window.models import WindowTurn, CompressedSummary
from core.agent.context_window.compressor import RuleBasedCompressor, CompressionLevel
from core.agent.context_window.window_manager import WindowManager, WindowConfig

__all__ = [
    "WindowManager",
    "WindowConfig",
    "WindowTurn",
    "CompressedSummary",
    "RuleBasedCompressor",
    "CompressionLevel",
]
