# core/agent/task_engine/__init__.py
"""任务引擎 —— 从对话中检测任务、管理任务状态、关联话语块。

核心能力（Phase 1）：
- 任务检测（从意图标签 + 小模型推断）
- 任务状态管理（started/continued/switched/completed/paused/failed）
- 任务进展里程碑（0-100% 自动推断）
- 子任务树（父任务→子任务嵌套）
- 任务-话语块关联（每个块归属一个或多个任务）
- 任务级自动摘要（每 2 块触发更新，规则 + 小模型）
- 任务上下文恢复（"回到刚才的…"自动检测并恢复）
- 任务切换检测（"回到刚才的"、"换个话题"）
"""

from __future__ import annotations

from core.agent.task_engine.task import Task, TaskStatus, TaskProgress, Milestone
from core.agent.task_engine.task_manager import TaskManager
from core.agent.task_engine.task_detector import TaskDetector

__all__ = [
    "Task",
    "TaskStatus",
    "TaskProgress",
    "Milestone",
    "TaskManager",
    "TaskDetector",
]
