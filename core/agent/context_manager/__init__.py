# core/agent/context_manager/__init__.py
"""上下文管理模块 —— 统一入口，整合三级协同、用户识别、任务引擎。

核心类：DiscourseManager
- 用户识别（UserEngine）
- 任务引擎（TaskEngine）
- 话语块管理（DiscoursePipeline）
- 模式路由（ModeRouter）

使用方式：
    from core.agent.context_manager import DiscourseManager

    manager = DiscourseManager(user_id="user_123")
    context = manager.process_turn("帮我写 Python 代码", turn_index=0)
"""

from __future__ import annotations

from core.agent.context_manager.discourse_manager import DiscourseManager

__all__ = ["DiscourseManager"]
