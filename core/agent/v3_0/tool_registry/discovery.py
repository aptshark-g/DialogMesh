# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/discovery.py
──────────────────────────────────────────
DialogMesh v3.0 工具发现模块。

用途：
- 动态扫描目录中的工具模块，自动注册满足约定的工具定义。
- 扫描约定：每个模块定义 TOOL_DEFINITIONS 列表，列表包含 ToolDefinition 对象。
- 预留 MCP 协议与 OpenAPI 文档发现接口（Phase 2）。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import glob
import importlib.util
import logging
import os
from typing import Any, Dict, List, Optional

from core.agent.v3_0.tool_registry.models import ToolDefinition
from core.agent.v3_0.tool_registry.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolDiscovery:
    """工具发现 — 动态扫描和注册工具。

    扫描约定：
        - 每个模块定义 ``TOOL_DEFINITIONS`` 列表
        - 列表包含 ToolDefinition 对象
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._logger = logging.getLogger("tool_discovery")

    # ── 目录扫描 ───────────────────────────────────────────────────────────

    async def scan_directory(self, directory: str) -> int:
        """扫描目录中的工具模块，自动注册。

        参数:
            directory: 待扫描的目录路径。

        返回:
            成功注册的工具数量。
        """
        registered = 0
        try:
            await asyncio.sleep(0)
            pattern = os.path.join(directory, "*.py")
            for filepath in glob.glob(pattern):
                if not os.path.isfile(filepath):
                    continue
                try:
                    count = await self._scan_file(filepath)
                    registered += count
                except Exception as exc:
                    self._logger.warning(
                        f"Failed to scan tool module: {filepath}, error: {exc}"
                    )
            return registered
        except Exception as exc:
            self._logger.error(f"scan_directory failed for {directory}: {exc}")
            raise

    def scan_directory_sync(self, directory: str) -> int:
        """同步扫描目录（用于非异步初始化阶段）。

        注意：此方法不获取锁，仅在单线程初始化阶段使用。
        """
        registered = 0
        try:
            pattern = os.path.join(directory, "*.py")
            for filepath in glob.glob(pattern):
                if not os.path.isfile(filepath):
                    continue
                try:
                    count = self._scan_file_sync(filepath)
                    registered += count
                except Exception as exc:
                    self._logger.warning(
                        f"Failed to scan tool module (sync): {filepath}, error: {exc}"
                    )
            return registered
        except Exception as exc:
            self._logger.error(f"scan_directory_sync failed for {directory}: {exc}")
            raise

    async def _scan_file(self, filepath: str) -> int:
        """扫描单个文件并注册工具（异步包装）。"""
        try:
            await asyncio.sleep(0)
            return self._scan_file_sync(filepath)
        except Exception as exc:
            self._logger.error(f"_scan_file failed: {filepath}: {exc}")
            raise

    def _scan_file_sync(self, filepath: str) -> int:
        """扫描单个文件并注册工具。"""
        module_name = os.path.basename(filepath)[:-3]
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载模块: {filepath}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        registered = 0
        if hasattr(module, "TOOL_DEFINITIONS"):
            definitions = getattr(module, "TOOL_DEFINITIONS")
            if isinstance(definitions, list):
                for tool in definitions:
                    if isinstance(tool, ToolDefinition):
                        if self._registry.register_sync(tool):
                            registered += 1
                            self._logger.info(
                                f"Auto-registered tool: {tool.name} from {filepath}"
                            )
                        else:
                            self._logger.warning(
                                f"Tool '{tool.name}' already registered, skipped"
                            )
                    else:
                        self._logger.warning(
                            f"Ignored non-ToolDefinition item in {filepath}"
                        )
            else:
                self._logger.warning(
                    f"TOOL_DEFINITIONS is not a list in {filepath}"
                )
        return registered

    # ── MCP 发现（Phase 2） ───────────────────────────────────────────────

    async def discover_mcp_tools(self, mcp_server_url: str) -> int:
        """从 MCP 服务器发现工具（Phase 2）。

        MCP (Model Context Protocol) 是 Anthropic 推出的工具协议。
        """
        raise NotImplementedError("MCP discovery will be implemented in Phase 2")

    async def discover_openapi_tools(self, openapi_url: str) -> int:
        """从 OpenAPI 文档发现工具（Phase 2）。

        将 REST API 自动转换为 ToolDefinition。
        """
        raise NotImplementedError("OpenAPI discovery will be implemented in Phase 2")

    # ── 模块内联注册（便捷方法） ───────────────────────────────────────────

    async def register_from_module(
        self, module: Any, prefix: Optional[str] = None
    ) -> int:
        """从已加载的模块对象注册工具。

        参数:
            module: 已导入的 Python 模块。
            prefix: 可选的工具名前缀（避免命名冲突）。

        返回:
            成功注册的工具数量。
        """
        registered = 0
        try:
            await asyncio.sleep(0)
            if not hasattr(module, "TOOL_DEFINITIONS"):
                self._logger.warning(f"Module {module.__name__} has no TOOL_DEFINITIONS")
                return 0

            definitions = getattr(module, "TOOL_DEFINITIONS")
            for tool in definitions:
                if isinstance(tool, ToolDefinition):
                    if prefix:
                        # 创建副本并添加前缀
                        tool = tool.model_copy(update={"name": f"{prefix}_{tool.name}"})
                    if self._registry.register_sync(tool):
                        registered += 1
                        self._logger.info(f"Registered from module: {tool.name}")
            return registered
        except Exception as exc:
            self._logger.error(f"register_from_module failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio
    import tempfile

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/discovery self-test ===")

        from core.agent.v3_0.tool_registry.registry import ToolRegistry

        registry = ToolRegistry()
        discovery = ToolDiscovery(registry)

        # 1. 创建临时模块文件
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = os.path.join(tmpdir, "demo_tools.py")
            with open(module_path, "w", encoding="utf-8") as f:
                f.write(
                    "from core.agent.v3_0.tool_registry.models import ToolDefinition\n"
                    "TOOL_DEFINITIONS = [\n"
                    "    ToolDefinition(name='demo_tool_a', description='Demo A', tags=['demo']),\n"
                    "    ToolDefinition(name='demo_tool_b', description='Demo B', tags=['demo']),\n"
                    "]\n"
                )

            # 2. 扫描目录
            count = await discovery.scan_directory(tmpdir)
            assert count == 2
            print(f"[PASS] scan_directory: registered {count} tools")

            # 3. 验证注册结果
            assert await registry.get("demo_tool_a") is not None
            assert await registry.get("demo_tool_b") is not None
            print(f"[PASS] registry verification")

        # 4. MCP 与 OpenAPI 预留接口
        try:
            await discovery.discover_mcp_tools("http://localhost:8080")
        except NotImplementedError:
            print(f"[PASS] MCP discovery NotImplementedError (expected)")

        try:
            await discovery.discover_openapi_tools("http://localhost:8080/openapi.json")
        except NotImplementedError:
            print(f"[PASS] OpenAPI discovery NotImplementedError (expected)")

        logger.info("=== All v3.0 tool_registry/discovery self-tests passed ===")

    asyncio.run(_self_test())
