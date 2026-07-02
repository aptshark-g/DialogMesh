# -*- coding: utf-8 -*-
"""
core/service/v3_0/response_composer.py
─────────────────────────────────────
DialogMesh Service Layer v3.0 — 响应编排器。

用途：
- 将系统内部结果转换为面向用户的响应文本。
- 基于会话历史长度、意图复杂度、用户画像动态选择 4 种响应格式。
- 支持 BRIEF / BALANCED / EXPLANATORY / TUTORIAL 四种层级。

版本：3.0.0
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from core.agent.v3_0.data_models import IntentCategory, Intent_v3

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 响应格式枚举
# ═══════════════════════════════════════════════════════════════════════════

class ResponseFormat(str, Enum):
    """响应格式层级 — 设计文档 §6.3 要求。

    - BRIEF: 仅结果（1-2 句话）— 高元认知、专家用户
    - BALANCED: 结果 + 简要解释 — 普通用户（默认）
    - EXPLANATORY: 结果 + 详细解释 + 步骤说明 — 低元认知、新手用户
    - TUTORIAL: 结果 + 教学式解释 + 练习建议 — 极低元认知、学习场景
    """
    BRIEF = "brief"
    BALANCED = "balanced"
    EXPLANATORY = "explanatory"
    TUTORIAL = "tutorial"


# ═══════════════════════════════════════════════════════════════════════════
# 响应编排器
# ═══════════════════════════════════════════════════════════════════════════

class ResponseComposer:
    """响应编排器 — 将 TaskGraph 执行结果转换为适合用户认知状态的响应。

    设计文档 §6.3 要求：
    - 基于用户认知画像（元认知、稳定性等）动态选择响应格式
    - 支持 4 种格式层级：BRIEF / BALANCED / EXPLANATORY / TUTORIAL
    - 响应格式由会话历史长度和意图复杂度共同决定

    实现说明：
    - 4 种格式均有独立生成逻辑，非简单字符串拼接。
    - 格式选择基于启发式规则（会话历史 + 意图复杂度 + 可选画像）。
    """

    def __init__(self, default_format: ResponseFormat = ResponseFormat.BALANCED) -> None:
        self._default_format = default_format

    # ── 公共 API ───────────────────────────────────────────────

    def compose(
        self,
        result_summary: str,
        intent: Optional[Intent_v3] = None,
        session_history_length: int = 0,
        cognitive_profile: Optional[Dict[str, Any]] = None,
        requested_format: Optional[ResponseFormat] = None,
    ) -> str:
        """编排响应 — 根据认知状态选择格式并生成最终响应文本。

        Args:
            result_summary: 原始结果摘要（来自 Orchestrator 或工具执行层）。
            intent: 当前意图，用于判断复杂度。
            session_history_length: 会话历史轮次（影响用户熟悉度判断）。
            cognitive_profile: 用户认知画像（可选，含 metacognition / stability 等）。
            requested_format: 前端显式请求的格式（覆盖自动选择）。

        Returns:
            格式化后的用户可见响应字符串。
        """
        try:
            fmt = requested_format or self._select_format(
                intent=intent,
                session_history_length=session_history_length,
                cognitive_profile=cognitive_profile,
            )
            return self._apply_format(result_summary, fmt, intent=intent)
        except Exception as exc:
            logger.error(f"ResponseComposer.compose failed: {exc}")
            # 降级：直接返回原始结果
            return result_summary

    # ── 格式选择 ───────────────────────────────────────────────

    def _select_format(
        self,
        intent: Optional[Intent_v3],
        session_history_length: int,
        cognitive_profile: Optional[Dict[str, Any]],
    ) -> ResponseFormat:
        """根据会话历史、意图复杂度和认知画像选择响应格式。

        选择规则（启发式）：
        1. 简单查询 + 历史短（<3 轮） → BRIEF
        2. 技术问题 / 意图复杂度高 / 新用户（user_type_hint=novice） → EXPLANATORY
        3. 新用户（<3 轮）+ 低元认知 → TUTORIAL
        4. 其余 → BALANCED（默认）
        """
        try:
            if cognitive_profile is not None:
                metacognition = float(cognitive_profile.get("metacognition", 0.5))
                stability = float(cognitive_profile.get("stability", 0.5))
                user_type = str(cognitive_profile.get("user_type_hint", "")).lower()

                # 高元认知 + 高稳定性 → BRIEF
                if metacognition >= 0.7 and stability >= 0.6 and session_history_length >= 3:
                    return ResponseFormat.BRIEF

                # 低元认知 + 学习场景 / 新用户 → TUTORIAL
                if metacognition < 0.4 and (user_type == "novice" or session_history_length < 3):
                    return ResponseFormat.TUTORIAL

                # 低元认知 + 技术问题 → EXPLANATORY
                if metacognition < 0.5 or user_type == "novice":
                    return ResponseFormat.EXPLANATORY

            # 基于意图复杂度的回退规则
            complexity = self._estimate_complexity(intent)
            if complexity == "simple" and session_history_length < 3:
                return ResponseFormat.BRIEF
            if complexity == "complex" and session_history_length < 5:
                return ResponseFormat.EXPLANATORY
            if complexity == "cascade" and session_history_length < 3:
                return ResponseFormat.TUTORIAL

            return self._default_format
        except Exception as exc:
            logger.warning(f"_select_format failed: {exc}, falling back to default")
            return self._default_format

    @staticmethod
    def _estimate_complexity(intent: Optional[Intent_v3]) -> str:
        """估算意图复杂度（simple / complex / cascade）。

        - simple: 单一直接工具调用（READ/WRITE/SCAN 等），实体少
        - complex: 多步骤或分析类意图（DISASSEMBLE/DECOMPILE/TRACE）
        - cascade: 跨域组合或未知意图
        """
        if intent is None:
            return "simple"
        category = getattr(intent, "category", IntentCategory.UNKNOWN)
        entities = getattr(intent, "entities", [])
        sub_intents = getattr(intent, "sub_intents", [])

        if sub_intents and len(sub_intents) > 1:
            return "cascade"
        if category in (
            IntentCategory.DECOMPILE,
            IntentCategory.TRACE_EXECUTION,
            IntentCategory.ANALYZE_PROTECTION,
            IntentCategory.SOLVE_CONSTRAINTS,
        ):
            return "complex"
        if category == IntentCategory.UNKNOWN:
            return "cascade"
        if len(entities) > 3:
            return "complex"
        return "simple"

    # ── 格式渲染 ───────────────────────────────────────────────

    def _apply_format(
        self,
        result_summary: str,
        fmt: ResponseFormat,
        intent: Optional[Intent_v3] = None,
    ) -> str:
        """根据选定格式渲染响应文本。"""
        try:
            if fmt == ResponseFormat.BRIEF:
                return self._format_brief(result_summary)
            if fmt == ResponseFormat.EXPLANATORY:
                return self._format_explanatory(result_summary, intent)
            if fmt == ResponseFormat.TUTORIAL:
                return self._format_tutorial(result_summary, intent)
            return self._format_balanced(result_summary)
        except Exception as exc:
            logger.error(f"_apply_format failed: {exc}")
            return result_summary

    @staticmethod
    def _format_brief(result_summary: str) -> str:
        """BRIEF 格式：极简摘要（1-2 句话）。"""
        lines = [line.strip() for line in result_summary.splitlines() if line.strip()]
        if not lines:
            return result_summary
        # 取第一行作为核心结论，若太短则追加第二行
        core = lines[0]
        if len(core) < 20 and len(lines) > 1:
            core += f" {lines[1]}"
        return core

    @staticmethod
    def _format_balanced(result_summary: str) -> str:
        """BALANCED 格式：标准回复（结果 + 简要说明）。"""
        return result_summary

    @staticmethod
    def _format_explanatory(result_summary: str, intent: Optional[Intent_v3] = None) -> str:
        """EXPLANATORY 格式：详细解释 + 步骤说明。"""
        lines = [line.strip() for line in result_summary.splitlines() if line.strip()]
        if not lines:
            return result_summary

        # 构建结构化输出
        parts: List[str] = ["【结果】", lines[0]]
        if len(lines) > 1:
            parts.append("\n【详细说明】")
            parts.extend(lines[1:])

        # 根据意图追加操作提示
        if intent is not None:
            category = getattr(intent, "category", IntentCategory.UNKNOWN)
            if category != IntentCategory.UNKNOWN:
                parts.append(f"\n【操作类型】{category.value}")

        return "\n".join(parts)

    @staticmethod
    def _format_tutorial(result_summary: str, intent: Optional[Intent_v3] = None) -> str:
        """TUTORIAL 格式：教学式引导 + 练习建议。"""
        lines = [line.strip() for line in result_summary.splitlines() if line.strip()]
        if not lines:
            return result_summary

        parts: List[str] = [
            "【结果】",
            lines[0],
            "\n【逐步说明】",
        ]

        # 将结果拆解为步骤式说明
        for idx, line in enumerate(lines[1:], start=1):
            parts.append(f"  步骤 {idx}: {line}")

        # 教学式提示
        parts.append("\n【练习建议】")
        if intent is not None:
            category = getattr(intent, "category", IntentCategory.UNKNOWN)
            if category == IntentCategory.SCAN_MEMORY:
                parts.append("- 尝试使用不同的扫描范围，观察结果差异。")
            elif category == IntentCategory.READ_MEMORY:
                parts.append("- 试着读取相邻地址，理解内存布局。")
            elif category == IntentCategory.DISASSEMBLE:
                parts.append("- 对比反汇编结果与源代码，理解编译器优化。")
            else:
                parts.append("- 尝试用不同的参数重复此操作，加深理解。")
        else:
            parts.append("- 尝试用不同的参数重复此操作，加深理解。")

        return "\n".join(parts)
