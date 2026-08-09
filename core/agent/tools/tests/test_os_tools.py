# -*- coding: utf-8 -*-
"""OS 控制工具测试（run_shell / run_python + 权限门集成）。"""
import pytest

from core.agent.tools import os_tools  # noqa: F401 注册
from core.agent.tools.os_tools import _run_shell, _run_python, _run_session, _dir_list
from core.agent.tools.registry import ToolRegistry


def test_run_shell_echo():
    r = _run_shell(command="echo hello dm")
    assert r.success
    assert "hello dm" in r.data.get("stdout", "")
    assert r.data.get("exit_code") == 0


def test_run_shell_structured_failure():
    r = _run_shell(command="definitely_not_a_command_xyz")
    assert not r.success
    assert r.error  # 非异常, 结构化返回


def test_run_python_compute():
    r = _run_python(code="print(sum(range(10)))")
    assert r.success
    assert r.data.get("stdout", "").strip() == "45"


def test_run_python_failure_structured():
    r = _run_python(code="raise ValueError('boom')")
    assert not r.success
    assert "boom" in r.data.get("stderr", "") or "boom" in (r.error or "")


def test_registered_in_registry():
    assert ToolRegistry.resolve("run_shell", auto_install=False).name == "run_shell"
    assert ToolRegistry.resolve("run_python", auto_install=False).name == "run_python"


def test_permission_gate_blocks_chained_shell():
    """权限门集成: 蓝图工具节点 run_shell 链式命令被拒。"""
    from core.agent.blueprint.decider import Decider
    from core.agent.blueprint.models import BlueprintNode
    d = Decider()
    resolver = d._executor._gate_resolver
    node = BlueprintNode("t1", "tool", priority=1, params={
        "tool": "run_shell", "args": {"command": "git status && rm -rf ~"}})
    assert resolver(node, {})["status"] == "rejected"


def test_permission_gate_allows_normal_shell():
    from core.agent.blueprint.decider import Decider
    from core.agent.blueprint.models import BlueprintNode
    d = Decider()
    resolver = d._executor._gate_resolver
    node = BlueprintNode("t2", "tool", priority=1, params={
        "tool": "run_shell", "args": {"command": "git status"}})
    assert resolver(node, {})["status"] == "approved"


def test_permission_gate_classifies_exec_risk():
    from core.agent.blueprint.permission_engine import classify_tool, RiskClass
    assert classify_tool("run_shell") is RiskClass.EXEC
    assert classify_tool("run_python") is RiskClass.EXEC


def test_dir_list_returns_entries():
    r = _dir_list(".")
    assert r.success
    assert r.data.get("count", 0) > 0
    assert any(e["name"] == "core" for e in r.data.get("entries", []))


def test_session_new_poll_list():
    r1 = _run_session(command="echo session_ok", action="new")
    assert r1.success
    sid = r1.data.get("session_id")
    assert sid
    r2 = _run_session(action="poll", session_id=sid)
    assert r2.success
    assert r2.data.get("done") is True  # 快速命令已结束
    assert "session_ok" in r2.data.get("stdout_tail", "")
    r3 = _run_session(action="list")
    assert r3.success
    assert r3.data.get("count", 0) >= 1


def test_session_kill_missing_fails():
    r = _run_session(action="kill", session_id="definitely_missing")
    assert not r.success
    assert "not found" in r.error
