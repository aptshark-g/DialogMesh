# -*- coding: utf-8 -*-
"""编码/实现类请求检测（tool_loop 触发条件, 2026-08-09）。"""
from __future__ import annotations

CODE_SIGNALS = [
    "写", "实现", "开发", "创建", "编码", "代码", "程序", "脚本",
    "hello world", "build", "implement", "develop", "write code",
    "写一个", "帮我写", "做一个", "make a", "create a", "运行",
    "compile", "run the code", "跑一下", "跑起来",
]


def is_code_request(text: str) -> bool:
    """检测是否为编码/实现/运行代码类请求。"""
    t = (text or "").lower()
    for s in CODE_SIGNALS:
        if s in t:
            return True
    return False
