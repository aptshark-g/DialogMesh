# -*- coding: utf-8 -*-
"""
core/agent/mcp/client.py
────────────────────────
MCP Client：连接外部 MCP Server，将其工具注册到 CognitiveTools。

支持：
  - 工具发现（ListTools）
  - 工具调用（CallTool）
  - 自动注册到 CognitiveTools 注册表（带前缀）
  - 白名单/黑名单过滤

传输：Streamable HTTP（推荐）或 stdio。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Callable

from core.agent.mcp.config import MCPClientConfig
from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext

try:
    from mcp.client import Client
    from mcp.transports import StreamableHTTPTransport
    HAS_MCP = True
except ImportError:
    try:
        # mcp 1.28+ 路径变化
        from mcp.client.session import ClientSession as Client
        from mcp.client.streamable_http import StreamableHTTPTransport
        HAS_MCP = True
    except ImportError:
        try:
            from mcp import Client
            from mcp import StreamableHTTPTransport
            HAS_MCP = True
        except ImportError:
            HAS_MCP = False
            Client = None
            StreamableHTTPTransport = None

import logging
logger = logging.getLogger(__name__)


class MCPClientAdapter:
    """
    连接外部 MCP Server，将其工具注册为 CognitiveTools 的别名。
    """

    def __init__(self, config: MCPClientConfig):
        self.config = config
        self._client: Optional[Any] = None
        self._tools: Dict[str, Any] = {}  # 缓存发现的工具元数据
        self._connected = False

    async def connect(self, max_retries: int = 3) -> bool:
        """
        连接 MCP Server 并发现工具，支持重试。
        返回是否成功。
        """
        if not HAS_MCP or Client is None:
            logger.warning("mcp package not installed — MCP Client unavailable")
            return False

        if self._connected:
            return True

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if self.config.transport == "streamable_http":
                    transport = StreamableHTTPTransport(self.config.server_url)
                else:
                    logger.error("Unsupported transport: %s", self.config.transport)
                    return False

                self._client = Client(transport=transport)
                await self._client.connect()

                # 发现工具
                tools = await self._client.list_tools()
                self._tools = {t.name: t for t in tools}
                self._connected = True

                logger.info(
                    "MCP Client connected (attempt %d/%d): %s — discovered %d tools",
                    attempt, max_retries, self.config.server_url, len(self._tools),
                )
                return True

            except Exception as exc:
                last_error = exc
                self._connected = False
                logger.warning(
                    "MCP Client connection attempt %d/%d failed: %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    wait = min(2 ** attempt, 30)  # 指数退避：2, 4, 8... 最大30秒
                    logger.info("Retrying in %.0fs...", wait)
                    import asyncio
                    await asyncio.sleep(wait)

        logger.error(
            "MCP Client connection failed after %d attempts: %s",
            max_retries, last_error,
        )
        return False

    async def reconnect(self) -> bool:
        """断开并重新连接。"""
        await self.disconnect()
        return await self.connect()

    def list_discovered_tools(self) -> List[str]:
        """返回已发现的工具名列表。"""
        return list(self._tools.keys())

    def is_tool_allowed(self, tool_name: str) -> bool:
        """检查工具是否通过白名单/黑名单。"""
        if self.config.blocklist and tool_name in self.config.blocklist:
            return False
        if self.config.allowlist and tool_name not in self.config.allowlist:
            return False
        return True

    def register_as_cognitive_tools(self) -> List[str]:
        """
        将外部工具注册到 CognitiveTools 注册表。
        返回成功注册的工具名列表。
        """
        registered: List[str] = []
        for name, meta in self._tools.items():
            if not self.is_tool_allowed(name):
                logger.debug("Tool blocked: %s", name)
                continue

            local_name = f"{self.config.tool_prefix}{name}"
            wrapper = self._create_wrapper(name, meta)
            CognitiveTools.register(local_name, wrapper)
            registered.append(local_name)
            logger.info("Registered external tool: %s -> %s", name, local_name)

        return registered

    def _create_wrapper(self, tool_name: str, meta: Any) -> Callable:
        """
        创建符合 CognitiveTools 签名的包装函数。
        外部工具参数通过 ExecutionContext 和 state 提取。
        """
        async def wrapper(ctx: ExecutionContext, state: Dict[str, Any]) -> Any:
            if not self._connected or self._client is None:
                raise RuntimeError(f"MCP Client not connected — cannot call {tool_name}")

            # 从 ExecutionContext 和 state 构建参数
            args = self._build_arguments(ctx, state, meta)

            # 调用外部工具
            start = time.time()
            try:
                result = await self._client.call_tool(tool_name, args)
            except Exception as exc:
                latency = (time.time() - start) * 1000
                logger.error(
                    "External tool call failed: %s (args=%s) in %.1fms: %s",
                    tool_name, args, latency, exc,
                )
                raise

            latency = (time.time() - start) * 1000
            logger.debug(
                "External tool call: %s in %.1fms", tool_name, latency
            )
            return result

        return wrapper

    def _build_arguments(
        self,
        ctx: ExecutionContext,
        state: Dict[str, Any],
        meta: Any,
    ) -> Dict[str, Any]:
        """
        从 ExecutionContext 和 state 构建外部工具的参数。

        策略：
          1. 如果 state 中有与外部工具同名的结果，直接传递
          2. 否则提取 ctx.raw_input 和已有实体作为参数
        """
        # 尝试从外部工具的 input_schema 获取参数名
        schema = getattr(meta, "input_schema", {}) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

        args: Dict[str, Any] = {}

        # 默认参数：raw_input
        if "query" in properties or "input" in properties:
            key = "query" if "query" in properties else "input"
            args[key] = ctx.raw_input

        # 传递 state 中的 PCR 结果
        pcr_out = state.get("pcr_evaluate")
        if pcr_out is not None:
            if "expectation" in properties:
                args["expectation"] = getattr(pcr_out, "expectation", "UNKNOWN")
            if "noise_level" in properties:
                args["noise_level"] = getattr(pcr_out, "noise_level", 0.0)

        # 传递实体列表
        entities = state.get("extract_entities", [])
        if entities and "entities" in properties:
            args["entities"] = [
                {"type": e.type, "value": e.value}
                for e in entities
                if hasattr(e, "type") and hasattr(e, "value")
            ]

        return args

    async def disconnect(self) -> None:
        """断开连接。"""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._client = None


# ═══════════════════════════════════════════════════════════════════════════════
# 多 Client 管理器
# ═══════════════════════════════════════════════════════════════════════════════

class MCPClientManager:
    """
    管理多个外部 MCP Server 连接。
    从环境变量读取配置，自动连接并注册工具。
    """

    def __init__(self):
        self._adapters: List[MCPClientAdapter] = []
        self._registered_tools: List[str] = []

    async def connect_all(self) -> None:
        """
        从环境变量读取所有 MCP_CLIENT_* 配置，连接并注册。

        支持多 Server：
          MCP_CLIENT_1_URL=...
          MCP_CLIENT_2_URL=...
        """
        import os

        # 默认配置（无前缀）
        default_url = os.getenv("MCP_CLIENT_URL", "")
        if default_url:
            await self._connect_one(MCPClientConfig.from_env("MCP_CLIENT"))

        # 枚举带数字前缀的配置
        idx = 1
        while True:
            prefix = f"MCP_CLIENT_{idx}"
            url = os.getenv(f"{prefix}_URL", "")
            if not url:
                break
            await self._connect_one(MCPClientConfig.from_env(prefix))
            idx += 1

    async def _connect_one(self, config: MCPClientConfig) -> None:
        adapter = MCPClientAdapter(config)
        success = await adapter.connect()
        if success:
            registered = adapter.register_as_cognitive_tools()
            self._adapters.append(adapter)
            self._registered_tools.extend(registered)
            logger.info(
                "MCP Client connected: %s — registered %d tools",
                config.server_url, len(registered),
            )
        else:
            logger.warning("Failed to connect MCP Client: %s", config.server_url)

    def list_registered_tools(self) -> List[str]:
        """返回所有已注册的外部工具名。"""
        return list(self._registered_tools)

    async def disconnect_all(self) -> None:
        """断开所有连接。"""
        for adapter in self._adapters:
            await adapter.disconnect()
        self._adapters.clear()
        self._registered_tools.clear()
