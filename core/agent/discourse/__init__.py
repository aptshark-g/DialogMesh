# -*- coding: utf-8 -*-
"""discourse/ 兼容层 — C4 修复（审计: discourse/ 只有 models.py 薄壳，
inspect_v3_cmd 的 ``from core.agent.discourse import DiscourseBlockTree``
因缺符号被 try/except 吞掉 → 静默 "module not found"）。

真实实现：``core.agent.discourse_block_tree.manager.DiscourseBlockTreeManager``
（R6 D3 内核组装后的 B 内核）。这里 re-export 兼容符号，保证旧引用可导入；
新代码请直接使用 discourse_block_tree 包。
"""
from __future__ import annotations

from core.agent.discourse_block_tree.manager import (
    DiscourseBlockTreeManager as DiscourseBlockTree,
)

__all__ = ["DiscourseBlockTree"]
