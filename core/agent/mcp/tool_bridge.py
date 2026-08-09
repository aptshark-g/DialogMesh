# -*- coding: utf-8 -*-
"""MCP 工具接入 core ToolRegistry — P1-5 (FLOW_SELF_GROWTH §5.5 OpenClaw 对齐).

现有 mcp/integration.py 把外部 MCP 工具注册进 planning 侧的
ToolRegistryBridge（tool_registry.registry）; 本模块补缺口: 注册进
blueprint 执行侧使用的 core.agent.tools.registry.ToolRegistry
（ToolAdapter + handler → MCP client.call_tool）, 使:
  - discover() 能发现 MCP 工具（LLM 语义决策可选中）
  - blueprint tool 节点可执行 MCP 工具
  - availability signal（连接状态 = env 条件）过滤可见性

同步桥: MCP client 是 async 的, ToolAdapter.handler 是同步的 —
用 run_until_complete 桥接（每次调用独立 event loop, 防线程串扰）.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.agent.tools.registry import ToolAdapter, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

MCP_TOOL_PREFIX = "mcp_"


class MCPToolAdapter(ToolAdapter):
    """包装一个外部 MCP 工具的 ToolAdapter.

    handler 同步桥接: MCPClientAdapter._client.call_tool(name, args).
    availability.env = ["<server_label>_CONNECTED"] — 由 register_mcp_tools
    设置; 未连接时不可见（LLM 不会选中不可用工具）.
    """

    def __init__(self, adapter, tool_name: str, server_label: str,
                 description: str = "", input_schema: Optional[dict] = None,
                 category: str = "mcp"):
        local = f"{MCP_TOOL_PREFIX}{server_label}_{tool_name}"
        super().__init__(
            name=local,
            description=description or f"[MCP:{server_label}] {tool_name}",
            category=category,
            keywords_zh=[],
            input_schema=input_schema or {},
            auto_install=False,
            availability={"env": [f"{server_label.upper()}_CONNECTED"],
                          "note": f"需 MCP server '{server_label}' 已连接"},
        )
        self._adapter = adapter
        self._mcp_tool = tool_name
        self._server_label = server_label
        self.handler = self._call_mcp

    def _call_mcp(self, **kwargs) -> ToolResult:
        client = getattr(self._adapter, "_client", None)
        if client is None:
            return ToolResult(self.name, False,
                              error="MCP client not connected")
        try:
            result = asyncio.run(client.call_tool(self._mcp_tool, kwargs))
            return ToolResult(self.name, True, data=result)
        except Exception as e:
            return ToolResult(self.name, False, error=str(e)[:300])


def register_mcp_tools(adapter, server_label: str,
                       tools: List[Dict[str, Any]]) -> int:
    """把已发现的 MCP 工具注册进 core ToolRegistry.

    tools: [{"name": str, "description": str, "input_schema": dict}]
    返回注册数。连接状态写入 ToolRegistry env 条件（可用性信号）。
    """
    env_key = f"{server_label.upper()}_CONNECTED"
    import os
    os.environ.setdefault(env_key, "1")
    count = 0
    for t in tools:
        name = t.get("name", "")
        if not name:
            continue
        try:
            ToolRegistry.register(MCPToolAdapter(
                adapter=adapter,
                tool_name=name,
                server_label=server_label,
                description=t.get("description", ""),
                input_schema=t.get("input_schema") or {},
            ))
            count += 1
        except Exception as e:
            logger.debug("MCP tool register failed %s: %s", name, e)
    logger.info("MCP: registered %d tools from server %s into ToolRegistry",
                count, server_label)
    return count


def sync_discover_and_register(adapter, server_label: str,
                               tools: Optional[List[Dict[str, Any]]] = None) -> int:
    """便捷入口: 已有工具列表 → 注册; 无列表则从 adapter 缓存读取."""
    if tools is None:
        tools = []
        discovered = getattr(adapter, "_tools", {}) or {}
        for mcp_name, meta in discovered.items():
            schema = getattr(meta, "input_schema", None) or {}
            tools.append({
                "name": mcp_name,
                "description": getattr(meta, "description", ""),
                "input_schema": schema if isinstance(schema, dict) else {},
            })
    return register_mcp_tools(adapter, server_label, tools)

