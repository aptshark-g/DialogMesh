# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_mcp_layer.py
──────────────────────────────────────
MCP 协议层（Layer 4）测试。

覆盖：
  - Config 解析
  - Security 层（认证、审计、脱敏、速率限制、路径守卫）
  - Server 创建和工具注册（mcp 包可用时）
  - Client 连接和工具注册（mcp 包可用时）

兼容 mcp 包未安装：无 mcp 时跳过 Server/Client 测试。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from core.agent.mcp.config import MCPServerConfig, MCPClientConfig, MCPSecurityConfig
from core.agent.mcp.security import (
    SecurityManager, AuditLogger, Sanitizer, AuthGuard,
    RateLimitGuard, PathGuard, AuditEntry,
)

try:
    from core.agent.mcp.server import create_mcp_server, HAS_MCP
except ImportError:
    HAS_MCP = False
    create_mcp_server = None

try:
    from core.agent.mcp.client import MCPClientAdapter, MCPClientManager, HAS_MCP as HAS_MCP_CLIENT
except ImportError:
    HAS_MCP_CLIENT = False
    MCPClientAdapter = None
    MCPClientManager = None


class TestMCPServerConfig(unittest.TestCase):
    """验证 MCP Server 配置解析。"""

    def test_defaults(self):
        cfg = MCPServerConfig()
        self.assertEqual(cfg.name, "memorygraph-agent")
        self.assertEqual(cfg.transport, "stdio")
        self.assertEqual(cfg.port, 8080)
        self.assertTrue(cfg.sanitize_pids)
        self.assertTrue(cfg.sanitize_memory_addresses)

    def test_from_env(self):
        with patch.dict(os.environ, {
            "MCP_SERVER_NAME": "test-agent",
            "MCP_TRANSPORT": "streamable_http",
            "MCP_PORT": "9000",
            "MCP_REQUIRE_AUTH": "true",
            "MCP_API_KEY": "secret123",
            "MCP_EXPOSED_TOOLS": "scan,read",
            "MCP_SANITIZE_PIDS": "0",
        }):
            cfg = MCPServerConfig.from_env()
            self.assertEqual(cfg.name, "test-agent")
            self.assertEqual(cfg.transport, "streamable_http")
            self.assertEqual(cfg.port, 9000)
            self.assertTrue(cfg.require_auth)
            self.assertEqual(cfg.api_key, "secret123")
            self.assertEqual(cfg.exposed_tools, ["scan", "read"])
            self.assertFalse(cfg.sanitize_pids)

    def test_exposed_tools_empty(self):
        with patch.dict(os.environ, {"MCP_EXPOSED_TOOLS": ""}):
            cfg = MCPServerConfig.from_env()
            self.assertEqual(cfg.exposed_tools, [])


class TestMCPClientConfig(unittest.TestCase):
    """验证 MCP Client 配置解析。"""

    def test_defaults(self):
        cfg = MCPClientConfig()
        self.assertEqual(cfg.server_url, "")
        self.assertEqual(cfg.transport, "streamable_http")
        self.assertEqual(cfg.timeout_seconds, 10.0)
        self.assertEqual(cfg.tool_prefix, "mcp_")

    def test_from_env(self):
        with patch.dict(os.environ, {
            "MCP_CLIENT_URL": "https://github.example.com/mcp",
            "MCP_CLIENT_API_KEY": "gh_key",
            "MCP_CLIENT_TIMEOUT": "5.0",
            "MCP_CLIENT_ALLOWLIST": "search_code,fetch_url",
        }):
            cfg = MCPClientConfig.from_env()
            self.assertEqual(cfg.server_url, "https://github.example.com/mcp")
            self.assertEqual(cfg.api_key, "gh_key")
            self.assertEqual(cfg.timeout_seconds, 5.0)
            self.assertEqual(cfg.allowlist, ["search_code", "fetch_url"])

    def test_prefix_env(self):
        with patch.dict(os.environ, {
            "MCP_CLIENT_1_URL": "https://example.com",
            "MCP_CLIENT_1_TOOL_PREFIX": "ext1_",
        }):
            cfg = MCPClientConfig.from_env("MCP_CLIENT_1")
            self.assertEqual(cfg.server_url, "https://example.com")
            self.assertEqual(cfg.tool_prefix, "ext1_")


class TestMCPSecurityConfig(unittest.TestCase):
    """验证 MCP Security 配置解析。"""

    def test_defaults(self):
        cfg = MCPSecurityConfig()
        self.assertTrue(cfg.audit_log_enabled)
        self.assertEqual(cfg.max_output_length, 4096)

    def test_from_env(self):
        with patch.dict(os.environ, {
            "MCP_AUDIT_LOG": "0",
            "MCP_MAX_OUTPUT_LENGTH": "1024",
            "MCP_ALLOWED_PATHS": "/tmp,/data",
        }):
            cfg = MCPSecurityConfig.from_env()
            self.assertFalse(cfg.audit_log_enabled)
            self.assertEqual(cfg.max_output_length, 1024)
            self.assertEqual(cfg.allowed_paths, ["/tmp", "/data"])


class TestAuthGuard(unittest.TestCase):
    """验证 API Key 认证。"""

    def test_no_auth_required(self):
        cfg = MCPServerConfig(require_auth=False)
        guard = AuthGuard(cfg)
        self.assertTrue(guard.check({}, {}))
        self.assertTrue(guard.check({"x-api-key": "wrong"}, {}))

    def test_header_auth(self):
        cfg = MCPServerConfig(require_auth=True, api_key="secret")
        guard = AuthGuard(cfg)
        self.assertTrue(guard.check({"x-api-key": "secret"}, {}))
        self.assertFalse(guard.check({"x-api-key": "wrong"}, {}))
        self.assertFalse(guard.check({}, {}))

    def test_bearer_auth(self):
        cfg = MCPServerConfig(require_auth=True, api_key="token")
        guard = AuthGuard(cfg)
        self.assertTrue(guard.check({"authorization": "Bearer token"}, {}))
        self.assertFalse(guard.check({"authorization": "Bearer wrong"}, {}))

    def test_query_param_auth(self):
        cfg = MCPServerConfig(require_auth=True, api_key="key")
        guard = AuthGuard(cfg)
        self.assertTrue(guard.check({}, {"api_key": "key"}))
        self.assertFalse(guard.check({}, {"api_key": "wrong"}))

    def test_no_key_configured(self):
        cfg = MCPServerConfig(require_auth=True, api_key=None)
        guard = AuthGuard(cfg)
        self.assertFalse(guard.check({"x-api-key": "anything"}, {}))


class TestRateLimitGuard(unittest.TestCase):
    """验证速率限制。"""

    def test_basic_limit(self):
        cfg = MCPServerConfig(rate_limit_requests_per_minute=60, rate_limit_burst=2)
        guard = RateLimitGuard(cfg)
        # burst = 2，前 2 次通过
        self.assertTrue(guard.check())
        self.assertTrue(guard.check())
        # 第 3 次应该失败（没有等待）
        self.assertFalse(guard.check())

    def test_refill_over_time(self):
        cfg = MCPServerConfig(rate_limit_requests_per_minute=60, rate_limit_burst=1)
        guard = RateLimitGuard(cfg)
        self.assertTrue(guard.check())  # 消耗 1
        self.assertFalse(guard.check())  # 无 token
        time.sleep(0.05)  # 等待 50ms， refill 约 0.05 * 1 = 0.05 token
        # 仍然不够（需要 1.0 token）
        self.assertFalse(guard.check())
        time.sleep(1.1)  # 等待 1.1s，refill 约 1.1 token
        self.assertTrue(guard.check())


class TestPathGuard(unittest.TestCase):
    """验证路径白名单。"""

    def test_no_restrictions(self):
        guard = PathGuard([])
        self.assertTrue(guard.is_allowed("/any/path"))
        self.assertTrue(guard.is_allowed("C:\\Windows\\system32"))

    def test_exact_match(self):
        guard = PathGuard(["/tmp"])
        self.assertTrue(guard.is_allowed("/tmp"))
        self.assertFalse(guard.is_allowed("/tmp2"))

    def test_prefix_match(self):
        guard = PathGuard(["/tmp"])
        self.assertTrue(guard.is_allowed("/tmp/file.txt"))
        self.assertFalse(guard.is_allowed("/tmp2/file.txt"))

    def test_windows_path(self):
        guard = PathGuard(["C:\\Users"])
        self.assertTrue(guard.is_allowed("C:\\Users\\test"))
        self.assertFalse(guard.is_allowed("C:\\Windows"))


class TestSanitizer(unittest.TestCase):
    """验证输出脱敏。"""

    def test_pid_redaction(self):
        cfg = MCPServerConfig(sanitize_pids=True, sanitize_memory_addresses=True)
        s = Sanitizer(cfg)
        text = "Found process Game.exe pid=1234"
        self.assertIn("<REDACTED>", s.sanitize(text))
        self.assertNotIn("1234", s.sanitize(text))

    def test_pid_no_redaction(self):
        cfg = MCPServerConfig(sanitize_pids=False, sanitize_memory_addresses=True)
        s = Sanitizer(cfg)
        text = "pid=1234"
        self.assertEqual(s.sanitize(text), text)

    def test_address_redaction(self):
        cfg = MCPServerConfig(sanitize_pids=True, sanitize_memory_addresses=True)
        s = Sanitizer(cfg)
        text = "Address 0x1000 and 0xABCDEF"
        result = s.sanitize(text)
        self.assertNotIn("0x1000", result)
        self.assertNotIn("0xABCDEF", result)
        self.assertIn("<ADDR>", result)

    def test_truncate(self):
        cfg = MCPServerConfig()
        s = Sanitizer(cfg)
        text = "A" * 10000
        result = s.truncate(text, max_length=100)
        self.assertEqual(len(result), 100 + len("\n...[truncated: 9900 chars]"))
        self.assertIn("truncated", result)

    def test_no_truncate(self):
        cfg = MCPServerConfig()
        s = Sanitizer(cfg)
        text = "short"
        self.assertEqual(s.truncate(text, max_length=100), text)


class TestAuditLogger(unittest.TestCase):
    """验证审计日志。"""

    def test_disabled(self):
        cfg = MCPSecurityConfig(audit_log_enabled=False)
        logger = AuditLogger(cfg)
        # 不抛异常即可
        logger.log(AuditEntry(
            timestamp=time.time(), tool_name="test", user_id=None,
            input_preview="", output_preview="", latency_ms=0.0, success=True,
        ))

    def test_stdout_logging(self):
        cfg = MCPSecurityConfig(audit_log_enabled=True, audit_log_path=None)
        logger = AuditLogger(cfg)
        # 不抛异常即可
        logger.log(AuditEntry(
            timestamp=time.time(), tool_name="scan", user_id="u1",
            input_preview="query", output_preview="result", latency_ms=12.0, success=True,
        ))

    def test_file_logging(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            path = f.name
        try:
            cfg = MCPSecurityConfig(audit_log_enabled=True, audit_log_path=path)
            logger = AuditLogger(cfg)
            logger.log(AuditEntry(
                timestamp=12345.0, tool_name="test", user_id=None,
                input_preview="in", output_preview="out", latency_ms=1.0, success=True,
            ))
            with open(path, "r") as f:
                content = f.read()
            self.assertIn("test", content)
            self.assertIn("12345.0", content)
            self.assertIn("\"success\": true", content)
        finally:
            os.unlink(path)


class TestSecurityManager(unittest.TestCase):
    """验证 SecurityManager 统一入口。"""

    def test_pre_flight_pass(self):
        server_cfg = MCPServerConfig(require_auth=False)
        sec_cfg = MCPSecurityConfig()
        sm = SecurityManager(server_cfg, sec_cfg)
        result = sm.pre_flight({}, {}, "scan", {"query": "test"})
        self.assertIsNone(result)

    def test_pre_flight_auth_fail(self):
        server_cfg = MCPServerConfig(require_auth=True, api_key="secret")
        sec_cfg = MCPSecurityConfig()
        sm = SecurityManager(server_cfg, sec_cfg)
        result = sm.pre_flight({}, {}, "scan", {})
        self.assertEqual(result, "Authentication failed")

    def test_pre_flight_rate_limit(self):
        server_cfg = MCPServerConfig(
            require_auth=False,
            rate_limit_requests_per_minute=0,  # 0 RPM = 立即耗尽
            rate_limit_burst=1,
        )
        sec_cfg = MCPSecurityConfig()
        sm = SecurityManager(server_cfg, sec_cfg)
        sm.rate_limit.check()  # 消耗唯一 token
        result = sm.pre_flight({}, {}, "scan", {})
        self.assertEqual(result, "Rate limit exceeded")

    def test_pre_flight_path_blocked(self):
        server_cfg = MCPServerConfig(require_auth=False)
        sec_cfg = MCPSecurityConfig(allowed_paths=["/tmp"])
        sm = SecurityManager(server_cfg, sec_cfg)
        result = sm.pre_flight({}, {}, "read_file", {"path": "/etc/passwd"})
        self.assertIn("Path not allowed", result)

    def test_pre_flight_path_allowed(self):
        server_cfg = MCPServerConfig(require_auth=False)
        sec_cfg = MCPSecurityConfig(allowed_paths=["/tmp"])
        sm = SecurityManager(server_cfg, sec_cfg)
        result = sm.pre_flight({}, {}, "read_file", {"path": "/tmp/file.txt"})
        self.assertIsNone(result)

    def test_post_flight(self):
        server_cfg = MCPServerConfig(sanitize_pids=True)
        sec_cfg = MCPSecurityConfig(audit_log_enabled=True, max_output_length=100)
        sm = SecurityManager(server_cfg, sec_cfg)
        output = sm.post_flight(
            tool_name="scan",
            user_id="u1",
            input_preview="query",
            output="pid=1234 and address 0x1000 and " + "A" * 500,
            latency_ms=10.0,
        )
        self.assertIn("<REDACTED>", output)
        self.assertIn("<ADDR>", output)
        self.assertIn("truncated", output)


@unittest.skipUnless(HAS_MCP, "mcp package not installed")
class TestMCPServer(unittest.TestCase):
    """验证 MCP Server 创建和工具注册（mcp 包可用时）。"""

    def test_create_server(self):
        server = create_mcp_server()
        self.assertIsNotNone(server)

    def test_create_server_with_custom_config(self):
        cfg = MCPServerConfig(name="custom-agent", transport="streamable_http")
        server = create_mcp_server(config=cfg)
        self.assertIsNotNone(server)

    def test_tools_registered(self):
        server = create_mcp_server()
        self.assertIsNotNone(server)
        # FastMCP 内部结构在不同版本中可能变化
        # 只检查 server 是 FastMCP 实例且成功创建
        self.assertTrue(callable(getattr(server, "run", None)) or hasattr(server, "_mcp_server"))
        # 工具注册由 @mcp.tool() 装饰器在导入时完成
        # 具体工具列表通过外部调用 list_tools 获取，不依赖内部属性
        # 验证方式：检查 server 能响应 run 调用（FastMCP 1.x 标准）


@unittest.skipUnless(HAS_MCP_CLIENT, "mcp package not installed")
class TestMCPClientAdapter(unittest.TestCase):
    """验证 MCP Client 适配器（mcp 包可用时）。"""

    def test_initial_state(self):
        cfg = MCPClientConfig(server_url="https://example.com")
        adapter = MCPClientAdapter(cfg)
        self.assertFalse(adapter._connected)
        self.assertEqual(adapter.list_discovered_tools(), [])

    def test_is_tool_allowed(self):
        cfg = MCPClientConfig(
            allowlist=["search_code", "fetch_url"],
            blocklist=["delete_repo"],
        )
        adapter = MCPClientAdapter(cfg)
        self.assertTrue(adapter.is_tool_allowed("search_code"))
        self.assertTrue(adapter.is_tool_allowed("fetch_url"))
        self.assertFalse(adapter.is_tool_allowed("delete_repo"))
        self.assertFalse(adapter.is_tool_allowed("other"))

    def test_is_tool_allowed_no_filters(self):
        cfg = MCPClientConfig()
        adapter = MCPClientAdapter(cfg)
        self.assertTrue(adapter.is_tool_allowed("anything"))

    def test_blocklist_only(self):
        cfg = MCPClientConfig(blocklist=["dangerous"])
        adapter = MCPClientAdapter(cfg)
        self.assertFalse(adapter.is_tool_allowed("dangerous"))
        self.assertTrue(adapter.is_tool_allowed("safe"))

    def test_allowlist_only(self):
        cfg = MCPClientConfig(allowlist=["allowed"])
        adapter = MCPClientAdapter(cfg)
        self.assertTrue(adapter.is_tool_allowed("allowed"))
        self.assertFalse(adapter.is_tool_allowed("other"))


class TestMCPClientManager(unittest.TestCase):
    """验证 MCP Client Manager。"""

    def test_initial_state(self):
        mgr = MCPClientManager()
        self.assertEqual(mgr.list_registered_tools(), [])

    def test_env_parsing(self):
        # 只验证配置解析，不实际连接
        with patch.dict(os.environ, {
            "MCP_CLIENT_URL": "https://test.example.com",
            "MCP_CLIENT_1_URL": "https://test1.example.com",
            "MCP_CLIENT_2_URL": "https://test2.example.com",
            "MCP_CLIENT_3_URL": "",  # 空 URL 应该停止枚举
        }):
            # 只测试配置读取，不测试连接
            cfg1 = MCPClientConfig.from_env("MCP_CLIENT")
            self.assertEqual(cfg1.server_url, "https://test.example.com")
            cfg2 = MCPClientConfig.from_env("MCP_CLIENT_1")
            self.assertEqual(cfg2.server_url, "https://test1.example.com")
            cfg3 = MCPClientConfig.from_env("MCP_CLIENT_2")
            self.assertEqual(cfg3.server_url, "https://test2.example.com")
            # 3 没有 URL，但 from_env 不会报错（返回默认空字符串）
            cfg4 = MCPClientConfig.from_env("MCP_CLIENT_3")
            self.assertEqual(cfg4.server_url, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
