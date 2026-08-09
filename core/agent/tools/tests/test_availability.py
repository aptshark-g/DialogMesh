# -*- coding: utf-8 -*-
"""P1-4 availability signal 测试（FLOW_SELF_GROWTH §5.5 OpenClaw 对齐）.

覆盖:
  - env 条件: 缺 env 变量 → 不可见 + 原因
  - config 条件: 缺配置键 → 不可见（set_config 注入后可见）
  - auth 条件: 未认证 → 不可见（set_auth 后可见）
  - discover 只返回可用工具
  - list_all 过滤 + include_unavailable 全量
  - resolve 不可用工具 → RuntimeError（明确原因）
  - status 含 available 标记
"""
from __future__ import annotations

import os

from core.agent.tools.registry import ToolRegistry, ToolAdapter, ToolResult
from core.agent.tools import builtin  # noqa: F401 — 注册内置工具


def _mk_result(name):
    return lambda **kw: ToolResult(name, True, data={"ok": name})


def test_env_condition():
    ToolRegistry.register(ToolAdapter(
        name="env_tool", description="needs token",
        category="test", availability={"env": ["DM_TEST_TOKEN_XYZ"]},
        handler=_mk_result("env_tool"),
    ))
    os.environ.pop("DM_TEST_TOKEN_XYZ", None)
    ok, reason = ToolRegistry.is_available("env_tool")
    assert ok is False
    assert "DM_TEST_TOKEN_XYZ" in reason
    # env 注入后可见
    os.environ["DM_TEST_TOKEN_XYZ"] = "abc"
    try:
        ok, reason = ToolRegistry.is_available("env_tool")
        assert ok is True
        assert reason == ""
    finally:
        os.environ.pop("DM_TEST_TOKEN_XYZ", None)
    ToolRegistry.unregister("env_tool")


def test_config_condition():
    ToolRegistry.register(ToolAdapter(
        name="cfg_tool", description="needs config",
        category="test", availability={"config": ["gateway.url"]},
        handler=_mk_result("cfg_tool"),
    ))
    ToolRegistry._config = {}
    ok, reason = ToolRegistry.is_available("cfg_tool")
    assert ok is False
    assert "gateway.url" in reason
    # set_config 注入后可见
    ToolRegistry.set_config({"gateway.url": "http://127.0.0.1:8080"})
    ok, reason = ToolRegistry.is_available("cfg_tool")
    assert ok is True
    ToolRegistry.unregister("cfg_tool")
    ToolRegistry.set_config({})


def test_auth_condition():
    ToolRegistry.register(ToolAdapter(
        name="auth_tool", description="needs auth",
        category="test", availability={"auth": True, "note": "需要登录"},
        handler=_mk_result("auth_tool"),
    ))
    ToolRegistry.set_auth(False)
    ok, reason = ToolRegistry.is_available("auth_tool")
    assert ok is False
    assert "auth required" in reason
    ToolRegistry.set_auth(True)
    ok, reason = ToolRegistry.is_available("auth_tool")
    assert ok is True
    ToolRegistry.unregister("auth_tool")
    ToolRegistry.set_auth(False)


def test_discover_filters_unavailable():
    ToolRegistry.register(ToolAdapter(
        name="disc_hidden", description="hidden paper search",
        category="search", keywords_zh=["查论文"],
        availability={"env": ["DM_PAPER_KEY_XYZ"]},
        handler=_mk_result("disc_hidden"),
    ))
    os.environ.pop("DM_PAPER_KEY_XYZ", None)
    names = [t.name for t in ToolRegistry.discover("查论文", limit=5)]
    assert "disc_hidden" not in " ".join(names)
    ToolRegistry.unregister("disc_hidden")


def test_list_all_filter_and_full():
    ToolRegistry.register(ToolAdapter(
        name="list_hidden", description="hidden",
        category="test", availability={"env": ["DM_NOPE_XYZ"]},
        handler=_mk_result("list_hidden"),
    ))
    os.environ.pop("DM_NOPE_XYZ", None)
    visible = ToolRegistry.list_all()
    names = [t["name"] for t in visible]
    assert "list_hidden" not in " ".join(names)
    full = ToolRegistry.list_all(include_unavailable=True)
    item = next((t for t in full if t["name"] == "list_hidden"), None)
    assert item is not None
    assert "unavailable_reason" in item
    ToolRegistry.unregister("list_hidden")


def test_resolve_unavailable_raises():
    ToolRegistry.register(ToolAdapter(
        name="resolve_hidden", description="needs env",
        category="test", availability={"env": ["DM_NOPE2_XYZ"]},
        handler=_mk_result("resolve_hidden"),
    ))
    os.environ.pop("DM_NOPE2_XYZ", None)
    try:
        ToolRegistry.resolve("resolve_hidden", auto_install=False)
        assert False, "should raise"
    except RuntimeError as e:
        assert "unavailable" in str(e)
        assert "DM_NOPE2_XYZ" in str(e)
    ToolRegistry.unregister("resolve_hidden")


def test_status_includes_available():
    ToolRegistry.register(ToolAdapter(
        name="status_hidden", description="s",
        category="test", availability={"env": ["DM_NOPE3_XYZ"]},
        handler=_mk_result("status_hidden"),
    ))
    os.environ.pop("DM_NOPE3_XYZ", None)
    st = ToolRegistry.status()
    assert st["tools"]["status_hidden"]["available"] is False
    assert st["tools"]["echo"]["available"] is True
    ToolRegistry.unregister("status_hidden")


def test_plain_tools_available():
    """无 availability 条件的工具默认可用."""
    ok, reason = ToolRegistry.is_available("echo")
    assert ok is True
    assert reason == ""
