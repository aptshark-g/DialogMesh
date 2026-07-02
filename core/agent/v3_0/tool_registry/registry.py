# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/registry.py
─────────────────────────────────────────
DialogMesh v3.0 工具注册中心。

用途：
- 统一管理所有可用工具的注册、注销、查询与 Schema 导出。
- 支持按标签索引、关键词搜索，以及 LLM 可用的 JSON Schema 生成。
- 线程安全（使用 asyncio.Lock），支持异步并发访问。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from core.agent.v3_0.tool_registry.models import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心 — 统一管理所有可用工具。

    提供注册、注销、按名获取、按标签/关键词查询、以及导出 LLM Schema 的能力。
    内部使用字典存储工具定义，并为标签维护反向索引以加速查询。
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._tags: Dict[str, Set[str]] = defaultdict(set)  # tag -> tool_names
        self._lock: Optional[asyncio.Lock] = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── 注册与注销 ────────────────────────────────────────────────────────

    async def register(self, tool: ToolDefinition) -> bool:
        """注册工具。

        参数:
            tool: 待注册的工具定义。

        返回:
            True 表示注册成功；False 表示同名工具已存在（需先注销）。
        """
        try:
            async with self._ensure_lock():
                if tool.name in self._tools:
                    logger.warning(f"Tool '{tool.name}' already registered, skipping")
                    return False

                self._tools[tool.name] = tool

                # 更新标签索引
                for tag in tool.tags:
                    self._tags[tag].add(tool.name)

                logger.info(f"Tool registered: {tool.name} (tags={tool.tags})")
                return True
        except Exception as exc:
            logger.error(f"register failed for {tool.name}: {exc}")
            raise

    def register_sync(self, tool: ToolDefinition) -> bool:
        """同步注册工具（用于非异步上下文，如模块初始化）。

        注意：此方法不获取锁，仅在单线程初始化阶段使用。
        """
        try:
            if tool.name in self._tools:
                logger.warning(f"Tool '{tool.name}' already registered (sync), skipping")
                return False

            self._tools[tool.name] = tool
            for tag in tool.tags:
                self._tags[tag].add(tool.name)

            logger.info(f"Tool registered (sync): {tool.name}")
            return True
        except Exception as exc:
            logger.error(f"register_sync failed for {tool.name}: {exc}")
            raise

    async def unregister(self, tool_name: str) -> bool:
        """注销工具。

        返回:
            True 表示注销成功；False 表示工具不存在。
        """
        try:
            async with self._ensure_lock():
                if tool_name not in self._tools:
                    return False

                tool = self._tools.pop(tool_name)
                for tag in tool.tags:
                    self._tags[tag].discard(tool_name)
                    if not self._tags[tag]:
                        del self._tags[tag]

                logger.info(f"Tool unregistered: {tool_name}")
                return True
        except Exception as exc:
            logger.error(f"unregister failed for {tool_name}: {exc}")
            raise

    async def get(self, tool_name: str) -> Optional[ToolDefinition]:
        """按名称获取工具定义。"""
        try:
            async with self._ensure_lock():
                return self._tools.get(tool_name)
        except Exception as exc:
            logger.error(f"get failed for {tool_name}: {exc}")
            raise

    def get_sync(self, tool_name: str) -> Optional[ToolDefinition]:
        """同步获取工具定义（非异步上下文使用）。"""
        return self._tools.get(tool_name)

    # ── 查询 ───────────────────────────────────────────────────────────────

    async def query(
        self,
        tags: Optional[List[str]] = None,
        keyword: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """查询工具。

        示例::

            # 查询所有内存相关工具
            tools = await registry.query(tags=["memory"])

            # 查询包含 "scan" 的工具
            tools = await registry.query(keyword="scan")
        """
        try:
            async with self._ensure_lock():
                candidates = list(self._tools.values())

                # 标签过滤
                if tags:
                    tag_matched: Set[str] = set()
                    for tag in tags:
                        for tname in self._tags.get(tag, set()):
                            tag_matched.add(tname)
                    candidates = [t for t in candidates if t.name in tag_matched]

                # 关键词过滤
                if keyword:
                    keyword_lower = keyword.lower()
                    candidates = [
                        t for t in candidates
                        if keyword_lower in t.name.lower()
                        or keyword_lower in t.description.lower()
                        or any(keyword_lower in tg.lower() for tg in t.tags)
                    ]

                return candidates
        except Exception as exc:
            logger.error(f"query failed (tags={tags}, keyword={keyword}): {exc}")
            raise

    async def list_all(self) -> List[ToolDefinition]:
        """列出所有已注册工具。"""
        try:
            async with self._ensure_lock():
                return list(self._tools.values())
        except Exception as exc:
            logger.error(f"list_all failed: {exc}")
            raise

    async def list_tags(self) -> List[str]:
        """列出所有已注册的标签。"""
        try:
            async with self._ensure_lock():
                return list(self._tags.keys())
        except Exception as exc:
            logger.error(f"list_tags failed: {exc}")
            raise

    # ── LLM Schema 导出 ────────────────────────────────────────────────────

    async def get_schema_for_llm(self) -> List[Dict[str, Any]]:
        """生成 LLM 可用的工具描述列表（JSON Schema 格式）。

        用于 Planning-LLM 的 tool_choice / functions 参数。
        """
        try:
            async with self._ensure_lock():
                return [tool.to_llm_schema() for tool in self._tools.values()]
        except Exception as exc:
            logger.error(f"get_schema_for_llm failed: {exc}")
            raise

    async def get_schema_for_llm_filtered(
        self, allowed_tools: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """生成过滤后的 LLM Schema。

        参数:
            allowed_tools: 允许导出的工具名列表；None 表示全部导出。
        """
        try:
            async with self._ensure_lock():
                tools = self._tools.values()
                if allowed_tools is not None:
                    allowed_set = set(allowed_tools)
                    tools = [t for t in tools if t.name in allowed_set]
                return [tool.to_llm_schema() for tool in tools]
        except Exception as exc:
            logger.error(f"get_schema_for_llm_filtered failed: {exc}")
            raise

    # ── 统计 ───────────────────────────────────────────────────────────────

    async def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息。"""
        try:
            async with self._ensure_lock():
                total = len(self._tools)
                dangerous = sum(1 for t in self._tools.values() if t.dangerous)
                by_source: Dict[str, int] = {}
                for t in self._tools.values():
                    by_source[t.source.value] = by_source.get(t.source.value, 0) + 1
                return {
                    "total_tools": total,
                    "dangerous_tools": dangerous,
                    "by_source": by_source,
                    "total_tags": len(self._tags),
                }
        except Exception as exc:
            logger.error(f"get_registry_stats failed: {exc}")
            raise

    # ── 工具方法 ───────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self._tools)}, tags={len(self._tags)})"


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/registry self-test ===")

        registry = ToolRegistry()

        # 1. 注册
        tool_a = ToolDefinition(name="test_a", description="Tool A", tags=["test", "memory"])
        tool_b = ToolDefinition(name="test_b", description="Tool B", tags=["test", "scan"])
        assert await registry.register(tool_a) is True
        assert await registry.register(tool_b) is True
        assert await registry.register(tool_a) is False  # 重复注册
        print(f"[PASS] register: {len(registry)} tools")

        # 2. 获取
        fetched = await registry.get("test_a")
        assert fetched is not None and fetched.name == "test_a"
        print(f"[PASS] get")

        # 3. 查询
        by_tag = await registry.query(tags=["memory"])
        assert len(by_tag) == 1 and by_tag[0].name == "test_a"
        by_keyword = await registry.query(keyword="scan")
        assert len(by_keyword) == 1 and by_keyword[0].name == "test_b"
        print(f"[PASS] query")

        # 4. Schema 导出
        schema = await registry.get_schema_for_llm()
        assert len(schema) == 2
        assert schema[0]["function"]["name"] in ("test_a", "test_b")
        print(f"[PASS] get_schema_for_llm")

        # 5. 统计
        stats = await registry.get_registry_stats()
        assert stats["total_tools"] == 2
        print(f"[PASS] stats: {stats}")

        # 6. 注销
        assert await registry.unregister("test_a") is True
        assert await registry.unregister("test_a") is False
        assert len(registry) == 1
        print(f"[PASS] unregister")

        # 7. list_tags
        tags = await registry.list_tags()
        assert "scan" in tags and "test" in tags
        print(f"[PASS] list_tags: {tags}")

        logger.info("=== All v3.0 tool_registry/registry self-tests passed ===")

    asyncio.run(_self_test())
