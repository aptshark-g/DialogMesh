# -*- coding: utf-8 -*-
"""Decider — BlueprintDAG execution entry point (§14.3, §7.2).

The Decider is the conductor: it groups nodes by Tick and delegates to
BlueprintExecutor (single execution implementation). EventBus subscription
table (§14.3) remains the architecture target; P0 uses sync DAG + EventLog
trace (mixed mode), so the Decider itself carries no duplicate loop.

Kept as a thin facade because agent_native.process_dag() and v3_session_api
both construct Decider() — changing internals keeps their contracts stable.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from core.agent.blueprint.models import BlueprintDAG

logger = logging.getLogger(__name__)


class Decider:
    """Executes a BlueprintDAG via the shared BlueprintExecutor."""

    def __init__(self, executor: Any = None):
        if executor is None:
            from core.agent.blueprint.executor import BlueprintExecutor
            executor = BlueprintExecutor(gate_resolver=_permission_resolver())
        self._executor = executor

    def execute(self, dag: BlueprintDAG, user_text: str = "") -> Dict[str, Any]:
        """Delegate to BlueprintExecutor.execute (single implementation)."""
        return self._executor.execute(dag, user_text=user_text)


def _permission_resolver():
    """默认权限 gate_resolver: PermissionEngine → PlanGate resolver 语义。
    F1（2026-08-08）: 生产路径工具权限生效（decider 构造 executor 默认挂载）。
    """
    from core.agent.blueprint.permission_engine import PermissionEngine
    pe = PermissionEngine()

    def resolver(node, outputs):
        if getattr(node, "chain", "") != "tool":
            return {"status": "approved"}
        tool = node.params.get("tool", "")
        args = node.params.get("args", {}) or {}
        decision = pe.evaluate(tool, args)
        if not decision.allowed:
            # 真危险拦截: 出可写根 / 只读模式 / 链式 shell（第一版基本能力）
            if "writable root" in decision.reason or "read-only" in decision.reason:
                return {"status": "rejected",
                        "comment": "permission: " + decision.reason}
            if tool == "run_shell" or tool.startswith("shell:"):
                command = str(args.get("command", ""))
                from core.agent.blueprint.permission_engine import has_shell_operators
                if has_shell_operators(command):
                    return {"status": "rejected",
                            "comment": "permission: shell chaining blocked"}
            # 普通审批（needs_user）→ 开发模式默认放行
        return {"status": "approved"}

    return resolver
