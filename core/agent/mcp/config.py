# -*- coding: utf-8 -*-
"""
core/agent/mcp/config.py
────────────────────────
MCP 层配置管理。环境变量 + 配置文件 + 默认值三层优先级。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MCPServerConfig:
    """MCP Server 配置（暴露内部工具）。"""
    name: str = "memorygraph-agent"
    version: str = "1.0.0"
    transport: str = "stdio"  # stdio | streamable_http
    host: str = "0.0.0.0"
    port: int = 8080
    path: str = "/mcp"
    # 安全
    api_key: Optional[str] = None
    require_auth: bool = False
    # 速率限制（复用现有 RateLimiter 配置）
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10
    # 暴露的工具白名单（空 = 全部）
    exposed_tools: List[str] = field(default_factory=list)
    # 敏感信息脱敏
    sanitize_pids: bool = True
    sanitize_memory_addresses: bool = True

    @classmethod
    def from_env(cls) -> "MCPServerConfig":
        """从环境变量构建配置。"""
        return cls(
            name=os.getenv("MCP_SERVER_NAME", cls.name),
            version=os.getenv("MCP_SERVER_VERSION", cls.version),
            transport=os.getenv("MCP_TRANSPORT", cls.transport),
            host=os.getenv("MCP_HOST", cls.host),
            port=int(os.getenv("MCP_PORT", cls.port)),
            path=os.getenv("MCP_PATH", cls.path),
            api_key=os.getenv("MCP_API_KEY"),
            require_auth=os.getenv("MCP_REQUIRE_AUTH", "").lower() in ("1", "true", "yes"),
            rate_limit_requests_per_minute=int(
                os.getenv("MCP_RATE_LIMIT_RPM", cls.rate_limit_requests_per_minute)
            ),
            rate_limit_burst=int(
                os.getenv("MCP_RATE_LIMIT_BURST", cls.rate_limit_burst)
            ),
            exposed_tools=_parse_list(os.getenv("MCP_EXPOSED_TOOLS", "")),
            sanitize_pids=os.getenv("MCP_SANITIZE_PIDS", "1").lower() not in ("0", "false", "no"),
            sanitize_memory_addresses=os.getenv("MCP_SANITIZE_ADDRESSES", "1").lower() not in ("0", "false", "no"),
        )


@dataclass
class MCPClientConfig:
    """MCP Client 配置（连接外部 Server）。"""
    server_url: str = ""  # 如 https://github-mcp.example.com/mcp
    transport: str = "streamable_http"  # stdio | streamable_http
    api_key: Optional[str] = None
    timeout_seconds: float = 10.0
    # 发现后自动注册的工具前缀
    tool_prefix: str = "mcp_"
    # 白名单：只注册这些外部工具（空 = 全部）
    allowlist: List[str] = field(default_factory=list)
    # 黑名单：明确拒绝这些工具
    blocklist: List[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, prefix: str = "MCP_CLIENT") -> "MCPClientConfig":
        """从环境变量构建，支持前缀区分多个 Client。"""
        return cls(
            server_url=os.getenv(f"{prefix}_URL", cls.server_url),
            transport=os.getenv(f"{prefix}_TRANSPORT", cls.transport),
            api_key=os.getenv(f"{prefix}_API_KEY"),
            timeout_seconds=float(
                os.getenv(f"{prefix}_TIMEOUT", cls.timeout_seconds)
            ),
            tool_prefix=os.getenv(f"{prefix}_TOOL_PREFIX", cls.tool_prefix),
            allowlist=_parse_list(os.getenv(f"{prefix}_ALLOWLIST", "")),
            blocklist=_parse_list(os.getenv(f"{prefix}_BLOCKLIST", "")),
        )


@dataclass
class MCPSecurityConfig:
    """MCP 安全层配置。"""
    # 审计日志
    audit_log_enabled: bool = True
    audit_log_path: Optional[str] = None  # None = stdout
    # 输入路径白名单（文件操作工具）
    allowed_paths: List[str] = field(default_factory=list)
    # 禁止的危险模式（已有 RouterOutputValidator，这里补充）
    dangerous_patterns: List[str] = field(default_factory=list)
    # 最大输出长度（防止 DoS）
    max_output_length: int = 4096

    @classmethod
    def from_env(cls) -> "MCPSecurityConfig":
        return cls(
            audit_log_enabled=os.getenv("MCP_AUDIT_LOG", "1").lower() not in ("0", "false", "no"),
            audit_log_path=os.getenv("MCP_AUDIT_LOG_PATH"),
            allowed_paths=_parse_list(os.getenv("MCP_ALLOWED_PATHS", "")),
            dangerous_patterns=_parse_list(os.getenv("MCP_DANGEROUS_PATTERNS", "")),
            max_output_length=int(os.getenv("MCP_MAX_OUTPUT_LENGTH", 4096)),
        )


def _parse_list(value: str) -> List[str]:
    """解析逗号分隔的列表。"""
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]
