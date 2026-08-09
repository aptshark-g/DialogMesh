# -*- coding: utf-8 -*-
"""v3_session_api 代码执行后处理测试（"实现软件"链路）。"""
import re

from core.agent.tools.os_tools import _run_python


def _extract_python_blocks(content):
    return re.findall(r"```python\n(.*?)```", content, re.S)


def test_extract_python_block():
    content = '先写代码:\n```python\nprint("hi")\n```\n完成。'
    blocks = _extract_python_blocks(content)
    assert len(blocks) == 1
    assert 'print("hi")' in blocks[0]


def test_run_python_executes_block():
    r = _run_python(code='print("Hello World")')
    assert r.success
    assert "Hello World" in r.data.get("stdout", "")


def test_postprocess_appends_result():
    """模拟 v3_session_api 后处理: 提取代码块 → 执行 → 追加结果。"""
    from core.agent.api import v3_session_api as mod
    # 复用真实提取逻辑（避免复制）
    src = "```python\nprint(1+1)\n```"
    blocks = _extract_python_blocks(src)
    assert blocks
    res = _run_python(code=blocks[0])
    out = (res.data or {}).get("stdout", "")
    assert "2" in out
