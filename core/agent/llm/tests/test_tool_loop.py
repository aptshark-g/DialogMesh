# -*- coding: utf-8 -*-
"""tool_loop 测试: 工具 schema 构建 + 权限门执行（不依赖真实 LLM）。"""
import json

import pytest

from core.agent.tools import os_tools  # noqa: F401 注册
from core.agent.llm.tool_loop import build_tools_schema, _execute_tool_call


def test_build_tools_schema_contains_os_tools():
    tools = build_tools_schema()
    names = {t["function"]["name"] for t in tools}
    assert "run_shell" in names
    assert "run_python" in names
    assert "write_file" in names
    for t in tools:
        assert t["function"]["parameters"]["type"] == "object"


def test_execute_tool_call_runs_python():
    tc = {"function": {"name": "run_python",
                       "arguments": json.dumps(
                           {"code": "print(40+2)"})}}
    result = _execute_tool_call(tc)
    assert result.get("ok")
    assert "42" in str(result.get("result"))


def test_execute_tool_call_blocks_shell_chain():
    tc = {"function": {"name": "run_shell",
                       "arguments": json.dumps(
                           {"command": "git status && rm -rf ~"})}}
    result = _execute_tool_call(tc)
    assert not result.get("ok")
    assert "blocked" in str(result.get("error", ""))


def test_execute_tool_call_unknown_tool():
    tc = {"function": {"name": "not_a_real_tool",
                       "arguments": "{}"}}
    result = _execute_tool_call(tc)
    assert not result.get("ok")


def test_code_request_detection():
    from core.agent.blueprint.code_request import is_code_request
    assert is_code_request("帮我写一个 python 程序")
    assert is_code_request("build a hello world")
    # v2.1 施工类信号（修改/重构/修复/编辑…）
    assert is_code_request("修改 core/agent/recall 下的召回服务")
    assert is_code_request("重构 statemachine 的执行分支")
    assert is_code_request("修复 task_graph 保存失败的问题")
    assert is_code_request("给 api_viz_edit 加一个恢复端点")
    assert is_code_request("refactor the tool_loop module")
    assert not is_code_request("今天天气怎么样")
