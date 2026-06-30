# core/agent/task_engine/task.py
"""任务数据模型 —— 可序列化、可追踪，支持里程碑与子任务树。

扩展能力（Phase 1）：
- 里程碑进展（Milestone）：0-100% 完成度，自动推断
- 子任务树（Subtask Tree）：支持父任务→子任务嵌套
- 自动任务摘要：每新增关联块时，由小模型或规则生成一句话摘要
- 任务上下文恢复：用户说“回到刚才的…”时自动恢复任务上下文

字段：
- task_id: 唯一标识
- task_type: 任务类型（code/debug/analyze/...）
- status: 任务状态
- progress: 进展百分比（0-100）
- milestones: 里程碑列表（[(label, percent, turn_index)]）
- start_turn: 起始轮次
- end_turn: 结束轮次（最新更新轮次）
- block_ids: 关联的 DiscourseBlock ID 列表
- summary: 任务级摘要（跨轮次进展）
- parent_task_id: 父任务 ID（子任务）
- children_ids: 子任务 ID 列表（新增）
- metadata: 额外元数据（JSON 可扩展）
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TaskStatus(Enum):
    """任务状态枚举。"""
    STARTED = "started"        # 新任务开始
    CONTINUED = "continued"    # 任务继续
    SWITCHED = "switched"      # 切换到新任务（原任务暂停）
    COMPLETED = "completed"    # 任务完成
    PAUSED = "paused"          # 任务暂停（可恢复）
    FAILED = "failed"          # 任务失败/放弃


class TaskProgress(Enum):
    """任务进展里程碑标签（用于快速识别任务阶段）。"""
    JUST_STARTED = (0, 10, "刚开始")
    EXPLORING = (10, 30, "探索中")
    IN_PROGRESS = (30, 60, "进行中")
    NEAR_COMPLETE = (60, 90, "即将完成")
    COMPLETED = (90, 100, "已完成")
    ABANDONED = (0, 0, "已放弃")

    def __init__(self, low: int, high: int, label: str):
        self.low = low
        self.high = high
        self.label = label

    @classmethod
    def from_percent(cls, percent: int) -> TaskProgress:
        for item in cls:
            if item.low <= percent <= item.high:
                return item
        return cls.IN_PROGRESS


@dataclass
class Milestone:
    """单个里程碑节点。"""
    label: str            # 里程碑名称（如 "设计完成"）
    percent: int          # 完成百分比（0-100）
    turn_index: int       # 对应轮次
    block_id: Optional[str] = None  # 关联的话语块
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "percent": self.percent,
            "turn_index": self.turn_index,
            "block_id": self.block_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Milestone:
        return cls(
            label=data.get("label", ""),
            percent=data.get("percent", 0),
            turn_index=data.get("turn_index", 0),
            block_id=data.get("block_id"),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class Task:
    """任务模型 —— 支持里程碑、子任务树、自动摘要。"""
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    task_type: str = "none"           # code/debug/analyze/search/learn/...
    status: TaskStatus = TaskStatus.STARTED
    progress: int = 0                 # 0-100 完成度
    milestones: List[Milestone] = field(default_factory=list)
    start_turn: int = 0
    end_turn: int = 0
    block_ids: List[str] = field(default_factory=list)
    summary: str = ""                 # 任务级一句话摘要
    parent_task_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)  # 子任务 ID
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── 生命周期 ──────────────────────────────────────────────────

    def add_block(self, block_id: str, turn_index: int):
        """添加关联的话语块并更新轮次。"""
        if block_id not in self.block_ids:
            self.block_ids.append(block_id)
        self.end_turn = max(self.end_turn, turn_index)
        self.updated_at = time.time()

    def update_status(self, status: TaskStatus, turn_index: int):
        """更新状态并同步进展。"""
        self.status = status
        if status == TaskStatus.COMPLETED:
            self.progress = 100
            self._add_milestone("任务完成", 100, turn_index)
        elif status == TaskStatus.FAILED:
            self._add_milestone("任务失败", self.progress, turn_index)
        self.end_turn = max(self.end_turn, turn_index)
        self.updated_at = time.time()

    def set_progress(self, percent: int, label: str, turn_index: int, block_id: Optional[str] = None):
        """设置进展百分比并记录里程碑。"""
        percent = max(0, min(100, percent))
        if percent > self.progress:
            self.progress = percent
            self._add_milestone(label, percent, turn_index, block_id)

    def _add_milestone(self, label: str, percent: int, turn_index: int, block_id: Optional[str] = None):
        """内部：添加里程碑（去重检查）。"""
        # 避免同一轮次同一标签重复
        for m in self.milestones:
            if m.turn_index == turn_index and m.label == label:
                return
        self.milestones.append(Milestone(label, percent, turn_index, block_id))

    # ── 子任务树 ──────────────────────────────────────────────────

    def add_child(self, child_task_id: str) -> bool:
        """添加子任务 ID。"""
        if child_task_id not in self.children_ids:
            self.children_ids.append(child_task_id)
            self.updated_at = time.time()
            return True
        return False

    def remove_child(self, child_task_id: str) -> bool:
        """移除子任务 ID。"""
        if child_task_id in self.children_ids:
            self.children_ids.remove(child_task_id)
            self.updated_at = time.time()
            return True
        return False

    @property
    def has_children(self) -> bool:
        return len(self.children_ids) > 0

    @property
    def is_subtask(self) -> bool:
        return self.parent_task_id is not None

    # ── 摘要与上下文 ──────────────────────────────────────────────

    def update_summary(self, summary: str) -> None:
        """更新任务级摘要。"""
        self.summary = summary
        self.updated_at = time.time()

    def get_context_hint(self) -> str:
        """生成任务上下文提示（用于注入对话）。"""
        if self.summary:
            return f"[任务 {self.task_id[:8]}: {self.summary}]"
        return f"[任务 {self.task_id[:8]}: {self.task_type} {self.progress}%]"

    # ── 序列化 ───────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "milestones": [m.to_dict() for m in self.milestones],
            "start_turn": self.start_turn,
            "end_turn": self.end_turn,
            "block_ids": self.block_ids,
            "summary": self.summary,
            "parent_task_id": self.parent_task_id,
            "children_ids": self.children_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Task:
        return cls(
            task_id=data.get("task_id", ""),
            task_type=data.get("task_type", "none"),
            status=TaskStatus(data.get("status", "started")),
            progress=data.get("progress", 0),
            milestones=[Milestone.from_dict(m) for m in data.get("milestones", [])],
            start_turn=data.get("start_turn", 0),
            end_turn=data.get("end_turn", 0),
            block_ids=data.get("block_ids", []),
            summary=data.get("summary", ""),
            parent_task_id=data.get("parent_task_id"),
            children_ids=data.get("children_ids", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=data.get("metadata", {}),
        )
