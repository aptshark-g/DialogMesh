# -*- coding: utf-8 -*-
"""
core/agent/mcp/security.py
──────────────────────────
MCP 安全层：认证、审计日志、输入脱敏、输出截断。

复用现有基础设施：
  - RateLimiter（令牌桶）
  - RouterOutputValidator（危险模式拦截）
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.mcp.config import MCPSecurityConfig, MCPServerConfig

try:
    from core.agent.service.rate_limiter import RateLimiter
    HAS_RATE_LIMITER = True
except ImportError:
    HAS_RATE_LIMITER = False
    RateLimiter = None

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Logger
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditEntry:
    """单次工具调用审计记录。"""
    timestamp: float
    tool_name: str
    user_id: Optional[str]
    input_preview: str
    output_preview: str
    latency_ms: float
    success: bool
    error: Optional[str] = None


class AuditLogger:
    """审计日志：记录每次 MCP 工具调用。"""

    def __init__(self, config: MCPSecurityConfig):
        self.enabled = config.audit_log_enabled
        self.path = config.audit_log_path

    def log(self, entry: AuditEntry) -> None:
        if not self.enabled:
            return
        line = json.dumps(
            {
                "timestamp": entry.timestamp,
                "tool": entry.tool_name,
                "user": entry.user_id,
                "input_preview": entry.input_preview,
                "output_preview": entry.output_preview,
                "latency_ms": entry.latency_ms,
                "success": entry.success,
                "error": entry.error,
            },
            ensure_ascii=False,
            default=str,
        )
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as exc:
                logger.warning("Audit log write failed: %s", exc)
        else:
            logger.info("[AUDIT] %s", line)


# ═══════════════════════════════════════════════════════════════════════════════
# Sanitizer
# ═══════════════════════════════════════════════════════════════════════════════

class Sanitizer:
    """输出脱敏：PID、内存地址、路径。"""

    PID_PATTERN = re.compile(r"\b(pid[:\s=]*)\d+", re.IGNORECASE)
    ADDR_PATTERN = re.compile(r"\b(0x[0-9a-fA-F]+)\b")
    PATH_PATTERN = re.compile(
        r"([A-Za-z]:\\[^\s]+|/[^\s]+)"
    )

    def __init__(self, server_config: MCPServerConfig):
        self.sanitize_pids = server_config.sanitize_pids
        self.sanitize_addrs = server_config.sanitize_memory_addresses

    def sanitize(self, text: str) -> str:
        if self.sanitize_pids:
            text = self.PID_PATTERN.sub(r"\1<REDACTED>", text)
        if self.sanitize_addrs:
            text = self.ADDR_PATTERN.sub("<ADDR>", text)
        return text

    def truncate(self, text: str, max_length: int = 4096) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length] + f"\n...[truncated: {len(text) - max_length} chars]"


# ═══════════════════════════════════════════════════════════════════════════════
# Auth Guard
# ═══════════════════════════════════════════════════════════════════════════════

class AuthGuard:
    """API Key 认证。支持 header 和 query param 两种传递方式。"""

    def __init__(self, server_config: MCPServerConfig):
        self.require_auth = server_config.require_auth
        self.api_key = server_config.api_key

    def check(self, headers: Dict[str, str], query_params: Dict[str, str]) -> bool:
        if not self.require_auth:
            return True
        if self.api_key is None:
            logger.warning("Auth required but no API_KEY configured")
            return False
        # Header: X-API-Key 或 Authorization: Bearer <key>
        auth_header = headers.get("x-api-key", "")
        if not auth_header:
            auth = headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                auth_header = auth[7:]
        # Query param
        if not auth_header:
            auth_header = query_params.get("api_key", "")
        return auth_header == self.api_key


# ═══════════════════════════════════════════════════════════════════════════════
# RateLimitGuard
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimitGuard:
    """速率限制：简单令牌桶实现。每个 MCP Server 实例独立限流。"""

    def __init__(self, server_config: MCPServerConfig):
        self.rpm = server_config.rate_limit_requests_per_minute
        self.burst = server_config.rate_limit_burst
        self._tokens = float(self.burst)
        self._last_refill = time.time()

    def check(self, tenant_id: str = "default", session_id: str = "mcp") -> bool:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self.burst),
            self._tokens + elapsed * (self.rpm / 60.0)
        )
        self._last_refill = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Path Guard
# ═══════════════════════════════════════════════════════════════════════════════

class PathGuard:
    """文件路径白名单。防止路径遍历。"""

    def __init__(self, allowed_paths: List[str]):
        self._allowed = [os.path.abspath(p) for p in allowed_paths if p]

    def is_allowed(self, path: str) -> bool:
        if not self._allowed:
            return True  # 未配置 = 允许全部（生产环境应配置）
        abs_path = os.path.abspath(path)
        return any(
            abs_path == allowed or abs_path.startswith(allowed + os.sep)
            for allowed in self._allowed
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SecurityManager — 统一入口
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityManager:
    """MCP 安全层统一入口。顺序：认证 → 速率限制 → 路径检查 → 执行 → 审计 → 脱敏。"""

    def __init__(
        self,
        server_config: MCPServerConfig,
        security_config: Optional[MCPSecurityConfig] = None,
    ):
        self.server_config = server_config
        self.security_config = security_config or MCPSecurityConfig.from_env()
        self.auth = AuthGuard(server_config)
        self.rate_limit = RateLimitGuard(server_config)
        self.path_guard = PathGuard(self.security_config.allowed_paths)
        self.sanitizer = Sanitizer(server_config)
        self.audit = AuditLogger(self.security_config)

    def pre_flight(
        self,
        headers: Dict[str, str],
        query_params: Dict[str, str],
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Optional[str]:
        """
        执行前检查。返回 None = 通过，返回 str = 错误信息（拒绝）。
        """
        # 1. 认证
        if not self.auth.check(headers, query_params):
            return "Authentication failed"
        # 2. 速率限制
        if not self.rate_limit.check():
            return "Rate limit exceeded"
        # 3. 路径检查（文件操作工具）
        if "path" in arguments or "file" in arguments:
            path = arguments.get("path") or arguments.get("file", "")
            if path and not self.path_guard.is_allowed(str(path)):
                return f"Path not allowed: {path}"
        return None

    def post_flight(
        self,
        tool_name: str,
        user_id: Optional[str],
        input_preview: str,
        output: str,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> str:
        """
        执行后处理：脱敏 + 截断 + 审计日志。
        返回处理后的输出。
        """
        # 1. 脱敏
        sanitized = self.sanitizer.sanitize(output)
        # 2. 截断
        truncated = self.sanitizer.truncate(sanitized, self.security_config.max_output_length)
        # 3. 审计
        self.audit.log(
            AuditEntry(
                timestamp=time.time(),
                tool_name=tool_name,
                user_id=user_id,
                input_preview=input_preview,
                output_preview=truncated[:256],
                latency_ms=latency_ms,
                success=error is None,
                error=error,
            )
        )
        return truncated
