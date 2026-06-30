# core/agent/task_engine/task_manager.py
"""任务管理器 —— 任务状态管理、任务-话语块关联、任务级摘要与里程碑。

Phase 1 扩展：
- 里程碑推断：从话语块内容推断进展百分比（0-100%）
- 子任务树：支持父任务→子任务嵌套
- 自动任务摘要：每新增关联块时触发摘要更新（规则/小模型）
- 任务上下文恢复：用户说“回到刚才的…”时自动恢复任务上下文

职责：
- 维护活跃任务列表与任务索引
- 检测任务切换（新任务开始、旧任务恢复）
- 每个 DiscourseBlock 关联到任务
- 任务级进展追踪与里程碑记录
- 任务树结构管理

使用方式：
    manager = TaskManager(small_model_client=sm_client)
    task = manager.detect_and_update(query="帮我写代码", block_id="block:T0:0", turn_index=0)
    # 创建子任务
    subtask = manager.create_subtask(task.task_id, "test", block_id="block:T1:0", turn_index=1)
    # 更新进展
    manager.infer_progress(task, "代码写完了，帮我测试一下", turn_index=2)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.task_engine.task import Task, TaskStatus, Milestone

logger = logging.getLogger(__name__)


# ── 任务进展推断规则 ────────────────────────────────────────────

PROGRESS_SIGNALS = {
    # 早期阶段 (0-30%)
    ("刚开始", "开始", "起步", "第一步", "先", "先试试", "planning", "designing"): (10, "设计阶段"),
    ("设计", "构思", "规划", "方案", "outline", "draft"): (20, "设计完成"),
    ("搭建", "框架", "骨架", "结构", "setup", "scaffold"): (25, "框架搭建"),
    # 中期阶段 (30-70%)
    ("实现", "编写", "写代码", "coding", "implementing"): (40, "实现中"),
    ("写完", "完成代码", "实现功能", "done coding", "implemented"): (60, "功能实现"),
    ("测试", "调试", "检查", "运行", "testing", "debugging"): (70, "测试调试"),
    ("修改", "优化", "重构", "refining", "optimizing"): (65, "优化改进"),
    # 后期阶段 (70-90%)
    ("差不多", "快好了", " nearing", "almost done"): (80, "即将完成"),
    ("review", "reviewing", "检查", "审查"): (85, "审查阶段"),
    ("完善", "收尾", "finalize", "polishing"): (90, "收尾完善"),
    # 完成阶段 (90-100%)
    ("完成", "搞定", "好了", "done", "finished", "completed", "that's it"): (100, "任务完成"),
    ("可以了", "没问题", "works", "ok now"): (95, "基本可用"),
    ("放弃", "不做了", "算了", "abandoned", "give up"): (-1, "任务放弃"),  # 特殊标记
}

# 合并为单一查找表
FLAT_PROGRESS_SIGNALS: Dict[str, Tuple[int, str]] = {}
for keywords, (percent, label) in PROGRESS_SIGNALS.items():
    for kw in keywords:
        FLAT_PROGRESS_SIGNALS[kw] = (percent, label)


# 任务类型默认里程碑模板
MILESTONE_TEMPLATES: Dict[str, List[Tuple[int, str]]] = {
    "code": [
        (10, "需求明确"), (25, "设计完成"), (40, "编码实现"),
        (60, "功能完成"), (80, "测试通过"), (100, "交付完成"),
    ],
    "debug": [
        (10, "问题复现"), (30, "定位原因"), (50, "修复方案"),
        (70, "修复实施"), (90, "验证通过"), (100, "问题关闭"),
    ],
    "analyze": [
        (10, "问题明确"), (30, "数据收集"), (50, "初步分析"),
        (70, "深度分析"), (90, "结论形成"), (100, "分析完成"),
    ],
    "compare": [
        (10, "对象确定"), (30, "维度梳理"), (50, "逐项对比"),
        (70, "差异总结"), (90, "结论形成"), (100, "对比完成"),
    ],
    "implement": [
        (10, "需求明确"), (25, "方案设计"), (40, "基础实现"),
        (60, "核心功能"), (80, "集成测试"), (100, "上线交付"),
    ],
    "learn": [
        (10, "目标确定"), (25, "资料收集"), (50, "知识学习"),
        (70, "实践练习"), (90, "掌握验证"), (100, "学习完成"),
    ],
    "plan": [
        (10, "目标明确"), (30, "现状分析"), (50, "方案制定"),
        (70, "资源评估"), (90, "计划确认"), (100, "计划完成"),
    ],
    "review": [
        (10, "范围确定"), (30, "初览检查"), (50, "问题标记"),
        (70, "详细审查"), (90, "修改建议"), (100, "审查完成"),
    ],
    "search": [
        (10, "关键词确定"), (30, "初步搜索"), (60, "结果筛选"),
        (80, "信息整理"), (100, "搜索完成"),
    ],
    "discuss": [
        (10, "话题引入"), (40, "观点交换"), (70, "深入探讨"),
        (90, "共识形成"), (100, "讨论结束"),
    ],
}


# 任务恢复关键词（用户想回到之前任务）
RESUME_KEYWORDS = {
    "回到", "返回", "继续", "接着", "刚才", "之前的", "之前",
    "back to", "continue", "resume", "go back", "previous",
    "刚才的", "刚才那个", "之前那个", "回到刚才",
}


try:
    from core.agent.task_engine.task_detector import TaskDetector
except ImportError:
    TaskDetector = None  # type: ignore

try:
    from core.agent.prompts import v3_summarize_prompt, parse_v3_summary
except ImportError:
    v3_summarize_prompt = None  # type: ignore
    parse_v3_summary = None  # type: ignore


class TaskManager:
    """任务管理器 —— 支持里程碑、子任务树、自动摘要、任务恢复。"""

    def __init__(self, small_model_client: Optional[Any] = None):
        self.detector = TaskDetector(small_model_client) if TaskDetector else None
        self._sm_client = small_model_client

        # 任务存储
        self._tasks: List[Task] = []              # 所有任务
        self._active_task: Optional[Task] = None  # 当前活跃任务
        self._task_index: Dict[str, Task] = {}    # task_id → Task

    # ── 核心入口：检测与更新 ──────────────────────────────────────

    def detect_and_update(
        self,
        query: str,
        block_id: str,
        turn_index: int,
        intent_label: Optional[str] = None,
    ) -> Optional[Task]:
        """检测任务并更新状态。

        Args:
            query: 用户输入
            block_id: 当前话语块 ID
            turn_index: 当前轮次
            intent_label: 意图标签（可选）

        Returns:
            当前活跃任务（或 None）
        """
        # 1. 任务恢复检测（用户说“回到刚才的…”）
        resume_task = self._detect_resume_request(query, turn_index)
        if resume_task:
            return resume_task

        # 2. 检测任务类型
        if self.detector:
            task_type, status, confidence = self.detector.detect(query, intent_label)
        else:
            task_type, status, confidence = "none", "continued", 0.3

        logger.debug(f"Task detected: type={task_type}, status={status}, conf={confidence:.2f}")

        # 3. 智能状态推断
        status = self._infer_status(task_type, status, turn_index)

        # 4. 根据状态处理
        task = self._handle_status(status, task_type, block_id, turn_index, query)

        # 5. 推断进展里程碑
        if task and query:
            self._infer_progress(task, query, turn_index, block_id)

        # 6. 更新任务摘要（每 2 个新增块触发一次）
        if task and len(task.block_ids) % 2 == 0 and query:
            self._update_task_summary(task, query)

        return task

    # ── 子任务管理 ────────────────────────────────────────────────

    def create_subtask(
        self,
        parent_task_id: str,
        task_type: str,
        block_id: str,
        turn_index: int,
        summary: str = "",
    ) -> Optional[Task]:
        """在父任务下创建子任务。

        Returns:
            新创建的子任务（或 None 如果父任务不存在）
        """
        parent = self._task_index.get(parent_task_id)
        if not parent:
            logger.warning(f"Parent task {parent_task_id} not found for subtask")
            return None

        subtask = Task(
            task_type=task_type,
            status=TaskStatus.STARTED,
            parent_task_id=parent_task_id,
            start_turn=turn_index,
            end_turn=turn_index,
            summary=summary,
        )
        subtask.add_block(block_id, turn_index)
        self._tasks.append(subtask)
        self._task_index[subtask.task_id] = subtask

        # 双向关联
        parent.add_child(subtask.task_id)

        logger.info(f"Subtask created: {subtask.task_id} ({task_type}) under {parent_task_id}")
        return subtask

    def get_subtasks(self, task_id: str) -> List[Task]:
        """获取指定任务的所有子任务。"""
        task = self._task_index.get(task_id)
        if not task or not task.children_ids:
            return []
        return [self._task_index.get(cid) for cid in task.children_ids if cid in self._task_index]

    def get_parent_task(self, task_id: str) -> Optional[Task]:
        """获取指定任务的父任务。"""
        task = self._task_index.get(task_id)
        if task and task.parent_task_id:
            return self._task_index.get(task.parent_task_id)
        return None

    def get_task_tree(self, task_id: str, depth: int = 0) -> List[Tuple[int, Task]]:
        """获取任务树（深度优先）。

        Returns:
            [(depth, Task), ...]
        """
        result = []
        task = self._task_index.get(task_id)
        if not task:
            return result
        result.append((depth, task))
        for child_id in task.children_ids:
            result.extend(self.get_task_tree(child_id, depth + 1))
        return result

    # ── 进展与里程碑 ──────────────────────────────────────────────

    def infer_progress(self, task: Task, query: str, turn_index: int, block_id: Optional[str] = None) -> int:
        """从用户话语推断任务进展并更新。

        Returns:
            推断的进展百分比（0-100），-1 表示放弃
        """
        return self._infer_progress(task, query, turn_index, block_id)

    def add_milestone(self, task_id: str, label: str, percent: int, turn_index: int, block_id: Optional[str] = None) -> bool:
        """手动添加里程碑。

        Returns:
            是否成功添加
        """
        task = self._task_index.get(task_id)
        if not task:
            return False
        task.set_progress(percent, label, turn_index, block_id)
        return True

    def get_progress_summary(self, task_id: str) -> str:
        """获取任务进展摘要（含里程碑）。"""
        task = self._task_index.get(task_id)
        if not task:
            return ""

        parts = [f"[{task.task_type}] {task.progress}%"]
        if task.milestones:
            latest = task.milestones[-1]
            parts.append(f"最新: {latest.label} ({latest.percent}%, T{latest.turn_index})")
        if task.summary:
            parts.append(f"摘要: {task.summary}")
        return " | ".join(parts)

    # ── 任务恢复 ──────────────────────────────────────────────────

    def resume_task(self, task_id: str, turn_index: int) -> Optional[Task]:
        """手动恢复指定任务。

        Returns:
            恢复后的任务（或 None）
        """
        task = self._task_index.get(task_id)
        if not task:
            return None

        # 暂停当前活跃任务
        if self._active_task and self._active_task.task_id != task_id:
            self._active_task.update_status(TaskStatus.PAUSED, turn_index)

        # 恢复目标任务
        task.update_status(TaskStatus.CONTINUED, turn_index)
        self._active_task = task
        logger.info(f"Task manually resumed: {task_id} ({task.task_type})")
        return task

    def resume_task_by_type(self, task_type: str, turn_index: int) -> Optional[Task]:
        """按类型恢复最近暂停的同类任务。"""
        candidates = [t for t in self._tasks if t.task_type == task_type and t.status == TaskStatus.PAUSED]
        if not candidates:
            return None
        latest = max(candidates, key=lambda t: t.updated_at)
        return self.resume_task(latest.task_id, turn_index)

    def get_task_context(self, task_id: str, max_blocks: int = 5) -> Dict[str, Any]:
        """获取任务上下文（用于注入对话）。

        Returns:
            {
                "task_id": str,
                "task_type": str,
                "progress": int,
                "summary": str,
                "latest_milestone": str,
                "block_ids": List[str],
                "hint": str,
            }
        """
        task = self._task_index.get(task_id)
        if not task:
            return {}

        latest_milestone = ""
        if task.milestones:
            m = task.milestones[-1]
            latest_milestone = f"{m.label} ({m.percent}%)"

        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "progress": task.progress,
            "summary": task.summary,
            "latest_milestone": latest_milestone,
            "block_ids": task.block_ids[-max_blocks:] if max_blocks else task.block_ids,
            "hint": task.get_context_hint(),
        }

    # ── 查询接口 ──────────────────────────────────────────────────

    def get_active_task(self) -> Optional[Task]:
        """获取当前活跃任务。"""
        return self._active_task

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务。"""
        return list(self._tasks)

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """通过 ID 获取任务。"""
        return self._task_index.get(task_id)

    def get_tasks_by_type(self, task_type: str) -> List[Task]:
        """按类型获取任务。"""
        return [t for t in self._tasks if t.task_type == task_type]

    def get_completed_tasks(self) -> List[Task]:
        """获取已完成的任务。"""
        return [t for t in self._tasks if t.status == TaskStatus.COMPLETED]

    def get_paused_tasks(self) -> List[Task]:
        """获取暂停的任务。"""
        return [t for t in self._tasks if t.status == TaskStatus.PAUSED]

    def get_task_summary(self, task_id: str) -> str:
        """获取任务级摘要。"""
        task = self._task_index.get(task_id)
        if not task:
            return ""
        if task.summary:
            return task.summary
        return f"[{task.task_type}] {task.progress}% {len(task.block_ids)} blocks, T{task.start_turn}-{task.end_turn}"

    def reset(self):
        """重置所有任务。"""
        self._tasks.clear()
        self._active_task = None
        self._task_index.clear()

    # ── 状态处理路由 ──────────────────────────────────────────────

    def _handle_status(
        self,
        status: str,
        task_type: str,
        block_id: str,
        turn_index: int,
        query: str,
    ) -> Optional[Task]:
        """根据推断状态处理任务。"""
        if status == "started" and task_type != "none":
            return self._handle_start(task_type, block_id, turn_index)

        elif status == "switched":
            return self._handle_switch(task_type, block_id, turn_index)

        elif status == "completed":
            return self._handle_complete(block_id, turn_index)

        elif status == "continued":
            return self._handle_continue(task_type, block_id, turn_index)

        return None

    def _handle_start(self, task_type: str, block_id: str, turn_index: int) -> Task:
        """新任务开始。"""
        if self._active_task and self._active_task.status == TaskStatus.CONTINUED:
            self._active_task.update_status(TaskStatus.PAUSED, turn_index)
        task = self._create_task(task_type, block_id, turn_index)
        self._active_task = task
        return task

    def _handle_switch(self, task_type: str, block_id: str, turn_index: int) -> Task:
        """任务切换。"""
        existing = self._find_task_by_type(task_type)
        if existing and existing.status == TaskStatus.PAUSED:
            # 恢复旧任务
            existing.update_status(TaskStatus.CONTINUED, turn_index)
            existing.add_block(block_id, turn_index)
            if self._active_task and self._active_task.task_id != existing.task_id:
                self._active_task.update_status(TaskStatus.PAUSED, turn_index)
            self._active_task = existing
            return existing
        else:
            # 创建新任务
            if self._active_task:
                self._active_task.update_status(TaskStatus.PAUSED, turn_index)
            task = self._create_task(task_type, block_id, turn_index)
            self._active_task = task
            return task

    def _handle_complete(self, block_id: str, turn_index: int) -> Optional[Task]:
        """当前任务完成。

        返回被完成的任务本身（而非尝试恢复后的结果）。
        如果没有活跃任务，返回 None。
        """
        if self._active_task:
            completed_task = self._active_task
            completed_task.update_status(TaskStatus.COMPLETED, turn_index)
            completed_task.add_block(block_id, turn_index)
            # 尝试恢复最近暂停的任务（如果存在）
            resumed = self._resume_latest_paused(turn_index)
            self._active_task = resumed
            return completed_task
        return None

    def _handle_continue(self, task_type: str, block_id: str, turn_index: int) -> Optional[Task]:
        """任务继续。"""
        if self._active_task and (self._active_task.task_type == task_type or task_type == "none"):
            self._active_task.add_block(block_id, turn_index)
            return self._active_task
        elif task_type != "none":
            # 没有活跃任务但有类型，创建新任务
            task = self._create_task(task_type, block_id, turn_index)
            self._active_task = task
            return task
        return None

    # ── 智能状态推断 ──────────────────────────────────────────────

    def _infer_status(self, task_type: str, detected_status: str, turn_index: int) -> str:
        """根据历史上下文推断任务状态。"""
        if not self._active_task:
            if task_type != "none":
                return "started"
            return "continued"

        if detected_status == "completed":
            return "completed"
        if detected_status == "switched":
            return "switched"

        if task_type == "none":
            return "continued"

        if task_type == self._active_task.task_type:
            return "continued"

        return "switched"

    # ── 进展推断 ──────────────────────────────────────────────────

    def _infer_progress(self, task: Task, query: str, turn_index: int, block_id: Optional[str] = None) -> int:
        """从用户话语推断任务进展。

        策略：
        1. 信号词匹配（优先级最高）
        2. 任务类型默认模板（渐进式填充）
        3. 块数比例（保底）
        """
        query_lower = query.lower()
        best_match = None
        best_percent = 0

        # 1. 信号词匹配
        for signal, (percent, label) in FLAT_PROGRESS_SIGNALS.items():
            if signal in query_lower:
                if percent > best_percent or (percent == -1 and best_percent == 0):
                    best_match = (percent, label)
                    best_percent = percent

        if best_match:
            percent, label = best_match
            if percent == -1:
                # 放弃信号
                task.update_status(TaskStatus.FAILED, turn_index)
                return -1
            task.set_progress(percent, label, turn_index, block_id)
            logger.debug(f"Progress inferred for {task.task_id}: {percent}% ({label})")
            return percent

        # 2. 任务类型默认模板（渐进式）
        if task.task_type in MILESTONE_TEMPLATES:
            templates = MILESTONE_TEMPLATES[task.task_type]
            # 找到当前进展对应的下一个里程碑
            for pct, label in templates:
                if pct > task.progress:
                    # 如果块数足够，推进到下一个里程碑
                    block_threshold = len(templates) * 2  # 粗略：每阶段约 2 块
                    if len(task.block_ids) >= block_threshold:
                        task.set_progress(pct, label, turn_index, block_id)
                    break

        # 3. 块数保底（最多 80%，避免过早 100%）
        if task.progress == 0 and len(task.block_ids) > 1:
            baseline = min(80, len(task.block_ids) * 15)
            if baseline > task.progress:
                task.progress = baseline

        return task.progress

    # ── 任务摘要 ──────────────────────────────────────────────────

    def _update_task_summary(self, task: Task, query: str) -> None:
        """更新任务级摘要（规则提取，小模型辅助）。"""
        # 规则：从最近的 query 中提取主题 + 行为 + 结论
        # 简化版：提取前 30 字作为主题线索
        if not query:
            return

        # 使用已有的 v3 summarizer prompt（如果可用）
        if self._sm_client and v3_summarize_prompt and parse_v3_summary:
            try:
                # 构建最近 3 轮的对话文本
                blocks_text = f"用户: {query}"
                prompt = v3_summarize_prompt(blocks_text, max_lines=1)
                result = self._sm_client.invoke(prompt, max_tokens=100, temperature=0.1)
                if result:
                    parsed = parse_v3_summary(result)
                    if parsed:
                        task.update_summary(parsed)
                        logger.debug(f"Task summary updated via LLM: {parsed}")
                        return
            except Exception as e:
                logger.debug(f"LLM summary failed: {e}")

        # 回退：规则摘要
        # 提取 query 的核心动作（前 20 字）
        summary = query[:20] + "..." if len(query) > 20 else query
        if task.summary:
            # 增量更新：追加新动作
            task.update_summary(f"{task.summary} → {summary}")
        else:
            task.update_summary(summary)

    # ── 任务恢复检测 ──────────────────────────────────────────────

    def _detect_resume_request(self, query: str, turn_index: int) -> Optional[Task]:
        """检测用户是否请求恢复之前任务。

        匹配：
        - "回到刚才的排序任务"
        - "继续刚才那个"
        - "返回之前的讨论"
        """
        query_lower = query.lower()

        # 检查恢复关键词
        has_resume_signal = any(kw in query_lower for kw in RESUME_KEYWORDS)
        if not has_resume_signal:
            return None

        # 尝试提取任务类型
        target_type = None
        for t_type in MILESTONE_TEMPLATES.keys():
            if t_type in query_lower:
                target_type = t_type
                break

        # 如果没指定类型，恢复最近暂停的任务
        if target_type:
            task = self._find_task_by_type(target_type)
            if task and task.status == TaskStatus.PAUSED:
                return self.resume_task(task.task_id, turn_index)
        else:
            # 恢复最近暂停的任务
            return self._resume_latest_paused(turn_index)

        return None

    # ── 内部工具 ──────────────────────────────────────────────────

    def _create_task(self, task_type: str, block_id: str, turn_index: int) -> Task:
        """创建新任务。"""
        task = Task(
            task_type=task_type,
            status=TaskStatus.CONTINUED,
            start_turn=turn_index,
            end_turn=turn_index,
        )
        task.add_block(block_id, turn_index)
        self._tasks.append(task)
        self._task_index[task.task_id] = task
        logger.info(f"Task created: {task.task_id} ({task_type}) at T{turn_index}")
        return task

    def _find_task_by_type(self, task_type: str) -> Optional[Task]:
        """查找最近暂停的同类任务。"""
        candidates = [
            t for t in self._tasks
            if t.task_type == task_type and t.status == TaskStatus.PAUSED
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t.updated_at)

    def _resume_latest_paused(self, turn_index: int) -> Optional[Task]:
        """恢复最近暂停的任务。"""
        paused = [t for t in self._tasks if t.status == TaskStatus.PAUSED]
        if not paused:
            return None
        # 暂停当前活跃任务（如果存在且不是目标）
        if self._active_task and self._active_task not in paused:
            self._active_task.update_status(TaskStatus.PAUSED, turn_index)
        latest = max(paused, key=lambda t: t.updated_at)
        latest.update_status(TaskStatus.CONTINUED, turn_index)
        self._active_task = latest  # 更新活跃任务引用
        logger.info(f"Task resumed: {latest.task_id} ({latest.task_type})")
        return latest
