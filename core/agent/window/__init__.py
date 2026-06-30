# -*- coding: utf-8 -*-
"""
window/__init__.py — 上下文窗口批量压缩入口

只导出 window/ 目录下的组件（批量压缩 API）。
增量管理 API（WindowManager, WindowConfig）在 context_window/ 目录下。
"""

from __future__ import annotations

from core.agent.window.context_window_manager import ContextWindowManager, WindowBudget
from core.agent.window.token_counter import TokenCounter
from core.agent.window.compressor import (
    Compressor,
    CompressionResult,
    PassThroughCompressor,
    TruncationCompressor,
    HierarchicalCompressor,
)
from core.agent.window.llm_compressor import LLMCompressor

__all__ = [
    "ContextWindowManager",
    "WindowBudget",
    "TokenCounter",
    "Compressor",
    "CompressionResult",
    "PassThroughCompressor",
    "TruncationCompressor",
    "HierarchicalCompressor",
    "LLMCompressor",
]
