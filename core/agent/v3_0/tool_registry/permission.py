# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/permission.py
──────────────────────────────────────────
DialogMesh v3.0 工具权限管理模块。

用途：
- 控制哪些 LLM 可以调用哪些工具，基于权限矩阵实现访问控制。
- 支持默认权限矩阵与运行时动态修改。
- 与 ToolExecutor 联动，在执行前进行权限校验。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PermissionManager:
    """工具权限管理 — 控制哪些 LLM 可以调用哪些工具。

    默认权限矩阵（对齐设计文档 §12）：
        PCR-LLM:          [web_search, file_read]          只读
        Intent-LLM:       [web_search, file_read]          只读
        Planning-LLM:     [*]                              所有工具
        Meta-Cognitive-LLM: []                             无工具
        Reflective-LLM:   [web_search]                     只搜索
        Answer-LLM:       [web_search, file_read, code_execute]  回复工具
    """

    DEFAULT_PERMISSIONS: Dict[str, List[str]] = {
        "PCR-LLM": ["web_search", "file_read"],
        "Intent-LLM": ["web_search", "file_read"],
        "Planning-LLM": ["*"],           # 所有工具
        "Meta-Cognitive-LLM": [],        # 不调用工具
        "Reflective-LLM": ["web_search"],
        "Answer-LLM": ["web_search", "file_read", "code_execute"],
    }

    def __init__(self, permissions: Optional[Dict[str, List[str]]] = None) -> None:
        self._permissions: Dict[str, List[str]] = (
            permissions if permissions is not None else dict(self.DEFAULT_PERMISSIONS)
        )
        self._lock: Optional[asyncio.Lock] = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── 权限查询 ───────────────────────────────────────────────────────────

    def can_call(self, llm_name: str, tool_name: str) -> bool:
        """检查 LLM 是否可以调用工具。

        参数:
            llm_name: LLM 实例标识（如 "Planning-LLM"）。
            tool_name: 工具名。

        返回:
            True 表示允许调用。
        """
        allowed = self._permissions.get(llm_name, [])
        if "*" in allowed:
            return True
        return tool_name in allowed

    async def async_can_call(self, llm_name: str, tool_name: str) -> bool:
        """异步权限检查。"""
        try:
            async with self._ensure_lock():
                await asyncio.sleep(0)
                return self.can_call(llm_name, tool_name)
        except Exception as exc:
            logger.error(f"async_can_call failed ({llm_name} -> {tool_name}): {exc}")
            raise

    def get_allowed_tools(self, llm_name: str) -> List[str]:
        """获取指定 LLM 的所有允许工具列表。"""
        return list(self._permissions.get(llm_name, []))

    def list_llms(self) -> List[str]:
        """列出所有已配置权限的 LLM 名称。"""
        return list(self._permissions.keys())

    # ── 权限修改 ───────────────────────────────────────────────────────────

    def set_permission(self, llm_name: str, tool_name: str, allowed: bool) -> None:
        """动态修改权限。

        参数:
            llm_name: LLM 实例标识。
            tool_name: 工具名。
            allowed: True 表示允许，False 表示禁止。
        """
        try:
            if llm_name not in self._permissions:
                self._permissions[llm_name] = []

            current = self._permissions[llm_name]
            if allowed:
                if tool_name not in current:
                    current.append(tool_name)
                    logger.info(f"Permission granted: {llm_name} -> {tool_name}")
            else:
                self._permissions[llm_name] = [
                    t for t in current if t != tool_name
                ]
                logger.info(f"Permission revoked: {llm_name} -> {tool_name}")
        except Exception as exc:
            logger.error(f"set_permission failed ({llm_name} -> {tool_name}): {exc}")
            raise

    async def async_set_permission(self, llm_name: str, tool_name: str, allowed: bool) -> None:
        """异步动态修改权限。"""
        try:
            async with self._ensure_lock():
                await asyncio.sleep(0)
                self.set_permission(llm_name, tool_name, allowed)
        except Exception as exc:
            logger.error(f"async_set_permission failed: {exc}")
            raise

    def remove_llm(self, llm_name: str) -> bool:
        """移除某 LLM 的所有权限配置。"""
        if llm_name in self._permissions:
            del self._permissions[llm_name]
            logger.info(f"Removed all permissions for {llm_name}")
            return True
        return False

    # ── 工具方法 ───────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, List[str]]:
        """导出为字典（深拷贝）。"""
        return {k: list(v) for k, v in self._permissions.items()}

    def __repr__(self) -> str:
        return f"PermissionManager(llms={len(self._permissions)})"


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/permission self-test ===")

        pm = PermissionManager()

        # 1. 默认权限检查
        assert pm.can_call("Planning-LLM", "memory_scan") is True   # * 通配
        assert pm.can_call("PCR-LLM", "web_search") is True       # 显式允许
        assert pm.can_call("PCR-LLM", "memory_scan") is False     # 未授权
        assert pm.can_call("Meta-Cognitive-LLM", "web_search") is False  # 空列表
        print(f"[PASS] default permission checks")

        # 2. 动态修改权限
        pm.set_permission("PCR-LLM", "memory_scan", True)
        assert pm.can_call("PCR-LLM", "memory_scan") is True
        pm.set_permission("PCR-LLM", "memory_scan", False)
        assert pm.can_call("PCR-LLM", "memory_scan") is False
        print(f"[PASS] dynamic permission modification")

        # 3. 获取允许工具列表
        planning_tools = pm.get_allowed_tools("Planning-LLM")
        assert planning_tools == ["*"]
        pcr_tools = pm.get_allowed_tools("PCR-LLM")
        assert "web_search" in pcr_tools and "file_read" in pcr_tools
        print(f"[PASS] get_allowed_tools")

        # 4. 异步权限检查
        ok = await pm.async_can_call("Answer-LLM", "code_execute")
        assert ok is True
        print(f"[PASS] async_can_call")

        # 5. 导出
        data = pm.to_dict()
        assert "Planning-LLM" in data
        print(f"[PASS] to_dict")

        logger.info("=== All v3.0 tool_registry/permission self-tests passed ===")

    asyncio.run(_self_test())
