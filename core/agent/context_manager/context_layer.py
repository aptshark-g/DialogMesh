# core/agent/context_manager/context_layer.py
"""上下文层 —— 管理所有系统注入的上下文。

核心职责：
1. 将用户画像、任务状态、检索结果等注入 Turn 的 context_blocks
2. 不修改 Turn.raw_query（原始查询不可污染）
3. 提供不同场景的渲染：
   - inject_for_router: 轻量上下文（给路由决策）
   - inject_for_llm: 完整上下文（给 LLM 生成）
   - inject_for_search: 干净文本（给语义搜索/NER）
   - inject_for_task: 任务相关上下文（给任务检测）

vs 旧架构：
    旧: inject_context() 返回字符串 = "[技术水平:expert]" + query
    新: context_layer.inject() 返回 ContextBlock[]，不修改 query
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.context_manager.turn import ContextBlock, Turn

logger = logging.getLogger(__name__)


class ContextLayer:
    """上下文注入层 —— 所有系统上下文通过此层进入 Turn。"""

    # 默认优先级
    PRIORITY_USER_PROFILE = 100  # 最高：用户画像
    PRIORITY_TASK_PROGRESS = 80  # 任务进展
    PRIORITY_RETRIEVAL = 60      # 检索结果
    PRIORITY_SYSTEM = 40         # 系统提示
    PRIORITY_ROUTER = 20         # 路由器专用

    def __init__(self):
        self._router_context_cache: Dict[str, Any] = {}

    # ── 按场景注入 ─────────────────────────────────────────────────

    def inject_for_router(self, turn: Turn, user_profile: Any, task_manager: Any) -> Turn:
        """为路由决策注入轻量上下文。

        路由器只需要：
        - 用户画像摘要（技术水平、耐心、成本预算）
        - 活跃任务状态（如果有）
        - 轮次计数（历史长度）
        """
        router_ctx = {}

        if user_profile is not None:
            router_ctx["user_profile"] = {
                "tech_level": getattr(user_profile, "tech_level", "unknown"),
                "patience_level": getattr(user_profile, "patience_level", "neutral"),
                "attention_span": getattr(user_profile, "attention_span", "medium"),
                "cost_budget": getattr(user_profile, "cost_budget", "standard"),
            }

        if task_manager is not None:
            active = task_manager.get_active_task()
            if active:
                router_ctx["active_task"] = {
                    "task_type": active.task_type,
                    "status": active.status.value if hasattr(active.status, "value") else str(active.status),
                    "progress": active.progress,
                }

        turn.router_context = router_ctx

        # 添加一个标记块（供调试，不进入 raw_query）
        turn.add_context(ContextBlock(
            type="router_context",
            content=router_ctx,
            priority=self.PRIORITY_ROUTER,
            source="context_layer",
        ))

        return turn

    def inject_for_llm(self, turn: Turn, user_profile: Any, task_manager: Any) -> List[ContextBlock]:
        """为 LLM 生成注入完整上下文。

        包含：
        - 用户画像（完整，用于个性化回复）
        - 活跃任务进展（如果用户在任务中）
        - 最近对话历史（语义搜索 top-k）
        """
        blocks: List[ContextBlock] = []

        # 用户画像（完整版）
        if user_profile is not None:
            blocks.append(ContextBlock(
                type="user_profile",
                content=user_profile.get_system_context(),
                priority=self.PRIORITY_USER_PROFILE,
                source="context_layer",
            ))

        # 任务进展
        if task_manager is not None:
            active = task_manager.get_active_task()
            if active:
                blocks.append(ContextBlock(
                    type="task_progress",
                    content={
                        "task_type": active.task_type,
                        "status": active.status.value if hasattr(active.status, "value") else str(active.status),
                        "progress": active.progress,
                        "milestones": [
                            {"label": m.label, "percent": m.percent, "turn": m.turn_index}
                            for m in active.milestones
                        ] if active.milestones else [],
                    },
                    priority=self.PRIORITY_TASK_PROGRESS,
                    source="context_layer",
                ))

        return blocks

    def inject_for_search(self, turn: Turn) -> str:
        """为语义搜索准备干净文本（过滤所有上下文块 + 注入过滤）。

        返回过滤后的文本（不含系统注入，且过滤用户伪造前缀）。
        """
        try:
            from core.agent.user_engine.user_extractor import UserExtractor
            extractor = UserExtractor()
            return extractor._filter_injection(turn.raw_query)
        except Exception:
            return turn.raw_query

    def inject_for_ner(self, turn: Turn) -> str:
        """为 NER 准备干净文本（同语义搜索 + 注入过滤）。"""
        return self.inject_for_search(turn)

    def inject_for_task(self, turn: Turn, user_profile: Any) -> Dict[str, Any]:
        """为任务检测准备上下文。

        包含：
        - 用户技术水平（影响任务推断）
        - 历史任务状态（用于恢复/切换检测）
        """
        return {
            "raw_query": turn.raw_query,
            "user_tech_level": getattr(user_profile, "tech_level", "unknown") if user_profile else "unknown",
        }

    # ── 组装输出 ───────────────────────────────────────────────────

    def assemble(self, turn: Turn, for_target: str = "llm") -> str:
        """组装最终输出文本。

        Args:
            turn: 当前 Turn
            for_target: "llm" | "router" | "search" | "task" | "debug"
        """
        if for_target == "search":
            return self.inject_for_search(turn)
        elif for_target == "task":
            return turn.raw_query  # 任务检测在原始文本上
        elif for_target == "ner":
            return self.inject_for_ner(turn)
        elif for_target == "debug":
            return turn.rendered_text
        else:  # "llm" 或其他
            return turn.rendered_text

    # ── 辅助方法 ───────────────────────────────────────────────────

    def create_user_profile_block(self, user_profile: Any) -> ContextBlock:
        """创建用户画像上下文块。"""
        return ContextBlock(
            type="user_profile",
            content=user_profile.get_system_context() if user_profile else {},
            priority=self.PRIORITY_USER_PROFILE,
        )

    def create_system_block(self, content: str, priority: int = 0) -> ContextBlock:
        """创建系统提示上下文块。"""
        return ContextBlock(
            type="system_prompt",
            content=content,
            priority=priority or self.PRIORITY_SYSTEM,
        )

    def clear_cache(self) -> None:
        """清除路由器上下文缓存。"""
        self._router_context_cache.clear()
