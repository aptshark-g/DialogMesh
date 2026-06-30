# -*- coding: utf-8 -*-
"""
core/agent/orchestrator.py
──────────────────────────
Blueprint Executor + Router LLM 输出校验器（v2.4 新增）。

执行引擎负责机械地按 Blueprint 调用工具，处理状态传递、
幂等、回滚和 trace。
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext
from core.agent.blueprints import Blueprint, BLUEPRINT_REGISTRY


@dataclass
class RouterDecision:
    """Router LLM 输出（经校验器确认后）。"""
    blueprint_id: str
    reason_code: str
    custom_tools: List[str] = field(default_factory=list)


@dataclass
class ExecutionStep:
    """单步执行记录。"""
    index: int
    tool: str
    status: str  # "ok" | "error" | "skipped"
    result_preview: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class ExecutionResult:
    """Blueprint 执行结果。"""
    status: str  # "ok" | "clarifying" | "error" | "fallback"
    task_graph: Optional[Any] = None
    clarification: Optional[Dict] = None
    trace: List[ExecutionStep] = field(default_factory=list)
    fallback_to: Optional[str] = None
    message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# RouterOutputValidator — 硬约束校验
# ═══════════════════════════════════════════════════════════════════════════════

class RouterOutputValidator:
    """
    Router LLM 输出必须通过的校验。任何失败 → 强制降级到 BLUEPRINT_ZERO。
    """

    DANGEROUS_PATTERNS = [
        "<script", "javascript:", "eval(", "exec(", "system(",
        "ignore previous", "ignore all", "you are now", "developer mode",
        "delete all", "drop table", "rm -rf",
    ]

    VALID_REASON_CODES = [
        "NOISE_TOO_HIGH", "AMBIGUITY_DETECTED", "UNKNOWN_INTENT",
        "NOVICE_USER", "COMPLEXITY_OVERFLOW", "CUSTOM_REQUEST",
        "TRACK_0_FALLBACK",
    ]

    @classmethod
    def validate(cls, raw: str, available_blueprints: List[str]) -> Optional[RouterDecision]:
        # 1. 必须是合法 JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        # 2. 必填字段
        if not isinstance(data, dict):
            return None
        bp_id = data.get("selected_blueprint")
        reason = data.get("reason_code")
        if bp_id is None or reason is None:
            return None

        # 3. 蓝图 ID 必须在可用列表中
        if bp_id not in available_blueprints:
            return None

        # 4. 自定义工具校验
        custom = data.get("custom_tools", [])
        if not isinstance(custom, list):
            custom = []
        if custom:
            registered = CognitiveTools.list_registered()
            invalid = [t for t in custom if t not in registered]
            if invalid:
                return None

        # 5. 危险模式拦截（即使 JSON 格式正确）
        text = raw.lower()
        if any(d in text for d in cls.DANGEROUS_PATTERNS):
            return None

        # 6. reason_code 校验（可选，允许未知 reason 但建议限定）
        # if reason not in cls.VALID_REASON_CODES:
        #     return None

        return RouterDecision(
            blueprint_id=bp_id,
            reason_code=reason,
            custom_tools=custom,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BlueprintExecutor — 执行引擎
# ═══════════════════════════════════════════════════════════════════════════════

class BlueprintExecutor:
    """
    蓝图执行引擎：按 Blueprint.strategy_steps 顺序调用 CognitiveTools。
    支持：状态快照、步骤回滚、动态追加工具、fallback 切换。
    """

    def __init__(self):
        self.trace: List[ExecutionStep] = []
        self.state: Dict[str, Any] = {}

    def reset(self):
        self.trace.clear()
        self.state.clear()

    def execute(self, blueprint: Blueprint, ctx: ExecutionContext) -> ExecutionResult:
        """
        同步执行 Blueprint。注意：底层工具如果是异步的，需要在外层 await。
        这里假设所有工具是同步的（符合现有规则引擎的实现）。
        """
        sequence = list(blueprint.strategy_steps)

        # 如果 Router 指定了 custom_tools，追加到序列末尾
        if ctx.router_decision and ctx.router_decision.custom_tools:
            sequence.extend(ctx.router_decision.custom_tools)

        # 超时检查（预算时间）
        deadline_ms = ctx.elapsed_ms() + blueprint.latency_budget_ms

        for idx, tool_name in enumerate(sequence):
            # 预算超时检查
            if ctx.elapsed_ms() > deadline_ms:
                self.trace.append(ExecutionStep(
                    index=idx, tool=tool_name, status="skipped",
                    error="Latency budget exceeded", latency_ms=ctx.elapsed_ms()
                ))
                return self._fallback(blueprint, ctx, "LATENCY_BUDGET_EXCEEDED")

            # 1. 执行前快照
            snapshot = self._snapshot()

            # 2. 调用工具
            try:
                result = CognitiveTools.run(tool_name, ctx, self.state)
                self.state[tool_name] = result
                self.trace.append(ExecutionStep(
                    index=idx, tool=tool_name, status="ok",
                    result_preview=_preview(result), latency_ms=ctx.elapsed_ms()
                ))

            except Exception as e:
                self.trace.append(ExecutionStep(
                    index=idx, tool=tool_name, status="error",
                    error=str(e), latency_ms=ctx.elapsed_ms()
                ))

                # 3. 回滚策略
                if blueprint.fallback_id:
                    self._restore(snapshot)
                    return self._fallback(blueprint, ctx, str(e))

                # 4. 动态注入 ask_user（如果当前是歧义检测失败）
                elif tool_name == "detect_ambiguities":
                    return ExecutionResult(
                        status="clarifying",
                        clarification={
                            "type": "clarification",
                            "message": f"执行工具 '{tool_name}' 时出错，请澄清。",
                            "error": str(e),
                        },
                        trace=self.trace,
                    )

                else:
                    return ExecutionResult(
                        status="error",
                        message=f"Tool '{tool_name}' failed: {e}",
                        trace=self.trace,
                    )

        # 5. 提取最终产物
        task_graph = self.state.get("build_task_graph")
        return ExecutionResult(
            status="ok",
            task_graph=task_graph,
            trace=self.trace,
        )

    def _snapshot(self) -> Dict:
        return copy.deepcopy(self.state)

    def _restore(self, snapshot: Dict) -> None:
        self.state = snapshot

    def _fallback(self, current_bp: Blueprint, ctx: ExecutionContext, reason: str) -> ExecutionResult:
        """切换到 fallback blueprint。"""
        if not current_bp.fallback_id:
            return ExecutionResult(
                status="error",
                message=f"No fallback for blueprint '{current_bp.id}': {reason}",
                trace=self.trace,
            )
        fallback_bp = BLUEPRINT_REGISTRY.get(current_bp.fallback_id)
        if fallback_bp is None:
            return ExecutionResult(
                status="error",
                message=f"Fallback blueprint '{current_bp.fallback_id}' not found",
                trace=self.trace,
            )
        # 递归执行 fallback（注意避免无限循环）
        return ExecutionResult(
            status="fallback",
            fallback_to=fallback_bp.id,
            message=f"Blueprint '{current_bp.id}' failed, falling back to '{fallback_bp.id}': {reason}",
            trace=self.trace,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _preview(result: Any) -> Optional[str]:
    """生成执行结果的简短预览，用于 trace_log。"""
    if result is None:
        return None
    if hasattr(result, "__class__") and result.__class__.__name__ == "PCROutput_v1":
        return f"PCROutput(expectation={getattr(result, 'expectation', '?')}, noise={getattr(result, 'noise_level', '?')})"
    if hasattr(result, "__class__") and result.__class__.__name__ == "ParseResult":
        return f"ParseResult(actionable={getattr(result, 'is_actionable', '?')})"
    if hasattr(result, "__class__") and result.__class__.__name__ == "TaskGraph":
        return f"TaskGraph(nodes={len(getattr(result, 'nodes', {}))})"
    if isinstance(result, list):
        return f"List(len={len(result)})"
    if isinstance(result, dict):
        return f"Dict(keys={list(result.keys())})"
    return str(result)[:100]
