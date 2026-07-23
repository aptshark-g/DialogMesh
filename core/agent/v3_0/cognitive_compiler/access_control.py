# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/access_control.py
────────────────────────────────────────────────────
认知编译器访问控制层。

职责:
  - 从 cognitive_tree.models 重新导出 AccessControlMatrix
  - 提供编译器专用的权限快捷方法
  - 保持与底层访问控制模型的语义一致

版本: 3.0.0
"""

from __future__ import annotations

from typing import Set

from core.agent.v3_0.cognitive_tree.models import (
    AccessControlMatrix as _AccessControlMatrix,
    CogType,
)

__all__ = ["AccessControlMatrix"]


class AccessControlMatrix(_AccessControlMatrix):
    """
    认知编译器访问控制矩阵 — 运行时权限检查。

    继承自 cognitive_tree.models.AccessControlMatrix，
    增加编译器专用的便捷方法，不改变原有权限语义。
    """

    def get_allowed_types(self, llm_name: str) -> Set[str]:
        """获取某 LLM 可以创建的节点类型字符串列表。

        Args:
            llm_name: LLM 实例名称

        Returns:
            允许创建的 CogType 值集合，如 {"perception", "hypothesis"}
        """
        perms = self.permissions.get(llm_name)
        if not perms:
            return set()
        return {t.value for t in perms.can_create}
