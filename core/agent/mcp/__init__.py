# -*- coding: utf-8 -*-
"""
core/agent/mcp — MCP 协议对接层（Layer 4）。

增量层，不修改任何现有核心引擎代码。

包含：
  - MCP Server：把内部 CognitiveTools 暴露为 MCP 标准工具
  - MCP Client：连接外部 MCP Server，将其工具注册到 CognitiveTools
  - Security：认证、审计、脱敏、速率限制
  - Config：环境变量驱动的配置

依赖：
  - mcp >= 1.27, < 2（pip install "mcp[cli]")
  - 现有核心引擎（已完成，345 测试通过）

示例：
  # 启动 stdio Server（Claude Desktop）
  from core.agent.mcp import run_stdio_server
  run_stdio_server()

  # 连接外部 MCP Server
  from core.agent.mcp import MCPClientManager
  manager = MCPClientManager()
  await manager.connect_all()
"""

from __future__ import annotations

from core.agent.mcp.config import MCPServerConfig, MCPClientConfig, MCPSecurityConfig
from core.agent.mcp.security import SecurityManager, AuditLogger, Sanitizer, AuthGuard, RateLimitGuard, PathGuard

try:
    from core.agent.mcp.server import create_mcp_server, run_stdio_server, get_streamable_http_app
except ImportError:
    create_mcp_server = None
    run_stdio_server = None
    get_streamable_http_app = None

try:
    from core.agent.mcp.client import MCPClientAdapter, MCPClientManager
except ImportError:
    MCPClientAdapter = None
    MCPClientManager = None

__all__ = [
    # Config
    "MCPServerConfig",
    "MCPClientConfig",
    "MCPSecurityConfig",
    # Security
    "SecurityManager",
    "AuditLogger",
    "Sanitizer",
    "AuthGuard",
    "RateLimitGuard",
    "PathGuard",
    # Server
    "create_mcp_server",
    "run_stdio_server",
    "get_streamable_http_app",
    # Client
    "MCPClientAdapter",
    "MCPClientManager",
]
