# -*- coding: utf-8 -*-
"""
core/agent/mcp/tests/test_mcp.py
────────────────────────────────
MCP 模块单元测试（无需外部 mcp 包）。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core.agent.mcp.config import MCPServerConfig, MCPClientConfig, MCPSecurityConfig, _parse_list
from core.agent.mcp.security import (
    AuditLogger, AuditEntry, Sanitizer, AuthGuard, RateLimitGuard, PathGuard, SecurityManager,
)


class TestMCPConfig(unittest.TestCase):
    """配置解析测试。"""

    def test_server_config_defaults(self):
        cfg = MCPServerConfig()
        self.assertEqual(cfg.name, "memorygraph-agent")
        self.assertEqual(cfg.transport, "stdio")
        self.assertTrue(cfg.sanitize_pids)

    def test_client_config_defaults(self):
        cfg = MCPClientConfig()
        self.assertEqual(cfg.transport, "streamable_http")
        self.assertEqual(cfg.tool_prefix, "mcp_")

    def test_security_config_defaults(self):
        cfg = MCPSecurityConfig()
        self.assertTrue(cfg.audit_log_enabled)
        self.assertEqual(cfg.max_output_length, 4096)

    def test_parse_list(self):
        self.assertEqual(_parse_list("a,b,c"), ["a", "b", "c"])
        self.assertEqual(_parse_list(""), [])
        self.assertEqual(_parse_list("a, b, c"), ["a", "b", "c"])


class TestSecurityLayer(unittest.TestCase):
    """安全层测试。"""

    def test_sanitizer_pid(self):
        s = Sanitizer(MCPServerConfig(sanitize_pids=True, sanitize_memory_addresses=True))
        text = "Process PID: 1234 and address 0x401000"
        result = s.sanitize(text)
        self.assertIn("<REDACTED>", result)
        self.assertNotIn("1234", result)

    def test_sanitizer_address(self):
        s = Sanitizer(MCPServerConfig(sanitize_pids=True, sanitize_memory_addresses=True))
        text = "Address 0xDEADBEEF found"
        result = s.sanitize(text)
        self.assertIn("<ADDR>", result)
        self.assertNotIn("0xDEADBEEF", result)

    def test_sanitizer_disabled(self):
        s = Sanitizer(MCPServerConfig(sanitize_pids=False, sanitize_memory_addresses=False))
        text = "PID: 1234 and 0x401000"
        self.assertEqual(s.sanitize(text), text)

    def test_sanitizer_truncate(self):
        s = Sanitizer(MCPServerConfig())
        long_text = "A" * 5000
        result = s.truncate(long_text, max_length=100)
        self.assertEqual(len(result), 100 + len("\n...[truncated: 4900 chars]"))

    def test_auth_guard_no_auth(self):
        g = AuthGuard(MCPServerConfig(require_auth=False))
        self.assertTrue(g.check({}, {}))

    def test_auth_guard_success(self):
        g = AuthGuard(MCPServerConfig(require_auth=True, api_key="secret"))
        self.assertTrue(g.check({"x-api-key": "secret"}, {}))

    def test_auth_guard_bearer(self):
        g = AuthGuard(MCPServerConfig(require_auth=True, api_key="token"))
        self.assertTrue(g.check({"authorization": "Bearer token"}, {}))

    def test_auth_guard_fail(self):
        g = AuthGuard(MCPServerConfig(require_auth=True, api_key="secret"))
        self.assertFalse(g.check({"x-api-key": "wrong"}, {}))

    def test_rate_limit_guard(self):
        g = RateLimitGuard(MCPServerConfig(rate_limit_requests_per_minute=60, rate_limit_burst=2))
        self.assertTrue(g.check())
        self.assertTrue(g.check())
        # 第3次应该失败（burst=2）
        self.assertFalse(g.check())

    def test_path_guard_empty(self):
        g = PathGuard([])
        self.assertTrue(g.is_allowed("/any/path"))

    def test_path_guard_allowed(self):
        g = PathGuard(["/allowed"])
        self.assertTrue(g.is_allowed("/allowed/sub"))
        self.assertFalse(g.is_allowed("/other"))

    def test_security_manager_preflight(self):
        cfg = MCPServerConfig(require_auth=False)
        sec = MCPSecurityConfig()
        mgr = SecurityManager(cfg, sec)
        self.assertIsNone(mgr.pre_flight({}, {}, "test", {}))

    def test_security_manager_postflight(self):
        cfg = MCPServerConfig()
        sec = MCPSecurityConfig(audit_log_enabled=False)
        mgr = SecurityManager(cfg, sec)
        result = mgr.post_flight("test", None, "input", "output with 0x401000 and PID: 1234", 10.0)
        self.assertIn("<ADDR>", result)
        self.assertIn("<REDACTED>", result)

    def test_audit_logger(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            path = f.name
        try:
            cfg = MCPSecurityConfig(audit_log_enabled=True, audit_log_path=path)
            logger = AuditLogger(cfg)
            entry = AuditEntry(
                timestamp=0.0, tool_name="test", user_id=None,
                input_preview="in", output_preview="out", latency_ms=1.0, success=True,
            )
            logger.log(entry)
            with open(path, "r", encoding="utf-8") as f:
                line = f.read().strip()
            self.assertIn("test", line)
            self.assertIn("true", line)
        finally:
            os.unlink(path)


class TestMCPClientAdapter(unittest.TestCase):
    """MCP Client 适配器测试（Mock）。"""

    def _run_async(self, coro):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    def test_list_discovered_tools_empty(self):
        from core.agent.mcp.client import MCPClientAdapter
        adapter = MCPClientAdapter(MCPClientConfig())
        self.assertEqual(adapter.list_discovered_tools(), [])

    def test_is_tool_allowed(self):
        from core.agent.mcp.client import MCPClientAdapter
        cfg = MCPClientConfig(blocklist=["dangerous"], allowlist=["safe"])
        adapter = MCPClientAdapter(cfg)
        self.assertFalse(adapter.is_tool_allowed("dangerous"))
        # allowlist 非空时，只允许白名单内
        self.assertTrue(adapter.is_tool_allowed("safe"))
        self.assertFalse(adapter.is_tool_allowed("other"))

    def test_is_tool_allowed_no_restrictions(self):
        from core.agent.mcp.client import MCPClientAdapter
        adapter = MCPClientAdapter(MCPClientConfig())
        self.assertTrue(adapter.is_tool_allowed("anything"))

    def test_connect_without_mcp_package(self):
        """未安装 mcp 包时应返回 False。"""
        from core.agent.mcp.client import MCPClientAdapter, HAS_MCP
        if not HAS_MCP:
            adapter = MCPClientAdapter(MCPClientConfig(server_url="http://test"))
            result = self._run_async(adapter.connect())
            self.assertFalse(result)


class TestMCPClientManager(unittest.TestCase):
    """MCP Client 管理器测试。"""

    def _run_async(self, coro):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    def test_list_registered_tools_empty(self):
        from core.agent.mcp.client import MCPClientManager
        mgr = MCPClientManager()
        self.assertEqual(mgr.list_registered_tools(), [])

    def test_disconnect_all_empty(self):
        from core.agent.mcp.client import MCPClientManager
        mgr = MCPClientManager()
        # 不应抛异常
        self._run_async(mgr.disconnect_all())


class TestMCPServerFactory(unittest.TestCase):
    """MCP Server 工厂测试。"""

    def test_create_without_mcp_package(self):
        """未安装 mcp 包时应返回 None。"""
        from core.agent.mcp.server import create_mcp_server, HAS_MCP
        if not HAS_MCP:
            result = create_mcp_server()
            self.assertIsNone(result)

    def test_get_streamable_http_app_without_mcp(self):
        from core.agent.mcp.server import get_streamable_http_app, HAS_MCP
        if not HAS_MCP:
            result = get_streamable_http_app()
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
