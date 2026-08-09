# -*- coding: utf-8 -*-
"""权限引擎 — GAP-1（COMPLETENESS_GAP_INVENTORY §C）.

对标 OpenWorker risk.py + permissions.py（已精读源码, 2026-08-06）:
  - RiskClass 4 级: read / write_local / exec / external
    （我们的 P1-2 三层介入是概念等价但粒度粗 — 本引擎补粒度）
  - Mode 5 档: discuss / plan / interactive / auto / custom
  - 写路径根限制（writable roots, 多根 + 可写标志）
  - shell 操作符检测（; | > < $( 等链式命令 → 强制审批, 防白名单逃逸）
  - 会话白名单 + 任务级 standing rules（tool → target 精确授权）

与 InterventionRouter（P1-2）关系: 本引擎 = 工具调用前"安全门"
（决定 allowed / needs_user）; InterventionRouter = 决策变更后
"记录/介入路由"（proposed/approve/reject）。两者互补。
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class RiskClass(str, Enum):
    """工具副作用风险分级（OpenWorker 同构）."""
    READ = "read"            # 无副作用 — 始终允许
    WRITE_LOCAL = "write_local"  # 改动工作区 — 路径限制 + 模式门控
    EXEC = "exec"            # 执行命令 — 模式门控
    EXTERNAL = "external"    # 机器外副作用 — 无人值守收件箱钩子


class Mode(str, Enum):
    DISCUSS = "discuss"       # 只读对话（连规划都不做）
    PLAN = "plan"             # 只读 + 规划契约（explore→propose→execute）
    INTERACTIVE = "interactive"  # 默认: 写/命令需询问
    AUTO = "auto"             # 全权（仍路径限制）
    CUSTOM = "custom"         # interactive + 配置的 auto_allow 工具


# 内置工具固定风险（按名表, 对齐 OpenWorker WRITE_TOOLS/SHELL_TOOL）
WRITE_TOOLS = {"write_file", "file_write", "replace_in_file", "apply_patch", "apply_unified_diff"}
SHELL_TOOL = "run_shell"
EXEC_TOOLS = {"run_shell", "run_python", "shell:exec"}

# shell 操作符: 白名单命令携带这些 → 强制审批（防 "git status && rm -rf ~"）
SHELL_OPERATORS = (";", "&", "|", ">", "<", "`", "$(", "(", "\n", "\r")


def has_shell_operators(command: str) -> bool:
    return any(op in command for op in SHELL_OPERATORS)


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    needs_user: bool = False   # True → 需用户 approve（同步 PlanGate 语义）
    rule: str = ""             # 命中的 standing rule（可审计）


def classify_tool(tool_name: str, metadata: Any = None) -> RiskClass:
    """工具 → 风险级: 名表优先 → metadata（requires_approval）→ read 兜底.

    与 OpenWorker classify() 同构:
      overrides 未接（预留）, 名表 base, metadata, else read.
    """
    if tool_name in WRITE_TOOLS:
        return RiskClass.WRITE_LOCAL
    if tool_name in EXEC_TOOLS or tool_name.startswith("shell:"):
        return RiskClass.EXEC
    if metadata is not None:
        # ToolAdapter.availability / input_schema 可带 risk 声明
        risk = getattr(metadata, "risk", None) or (
            isinstance(metadata, dict) and metadata.get("risk"))
        if risk in ("exec", "write_local", "external"):
            return RiskClass(risk)
        if bool(getattr(metadata, "requires_approval", False)) or (
                isinstance(metadata, dict) and metadata.get("requires_approval")):
            return RiskClass.EXTERNAL
    return RiskClass.READ


@dataclass
class PermissionEngine:
    """工具调用权限判定 — 决定 allow / deny / ask-user.

    用法:
        pe = PermissionEngine(workspace_root=".")
        decision = pe.evaluate("write_file", {"path": "x.txt"})
    """
    workspace_root: str = "."
    mode: Mode = Mode.INTERACTIVE
    allowed_commands: List[str] = field(default_factory=list)
    auto_allow_tools: set = field(default_factory=set)
    session_allow_tools: set = field(default_factory=set)
    session_allow_commands: set = field(default_factory=set)
    # standing rules: {tool: {targets}} — 任务级精确授权
    task_rules: Dict[str, set] = field(default_factory=dict)
    # 多根: [{"path": ..., "writable": bool}]
    roots: Optional[List[dict]] = None

    def __post_init__(self):
        if self.roots is None:
            self.roots = [{"path": self.workspace_root, "writable": True}]

    def _resolved_roots(self) -> List[Tuple[Path, bool]]:
        out = []
        for r in self.roots or []:
            if isinstance(r, dict):
                p, w = r.get("path", "."), bool(r.get("writable", False))
            else:
                p, w = r, True
            out.append((Path(p).expanduser().resolve(), w))
        return out

    def _under_writable_root(self, path: str) -> bool:
        if not path:
            return True
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            candidate = candidate.resolve()
        else:
            candidate = (Path(self.workspace_root).expanduser().resolve() /
                         candidate).resolve()
        for rp, writable in self._resolved_roots():
            if not writable:
                continue
            try:
                candidate.relative_to(rp)
                return True
            except ValueError:
                continue
        return False

    def _command_allowed(self, command: str) -> bool:
        """白名单命令精确前缀匹配（token 级, 防 `git statusfoo`/`git status && rm`）."""
        if has_shell_operators(command):
            return False
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False
        for allowed in self.allowed_commands:
            try:
                prefix = shlex.split(allowed)
            except ValueError:
                continue
            if prefix and argv[:len(prefix)] == prefix:
                return True
        return False

    def evaluate(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None,
                 metadata: Any = None) -> Decision:
        """一次工具调用的权限判定."""
        arguments = arguments or {}
        risk = classify_tool(tool_name, metadata)
        is_write = risk is RiskClass.WRITE_LOCAL
        is_shell = risk is RiskClass.EXEC
        consequential = risk is not RiskClass.READ

        # discuss/plan 模式只读
        if self.mode in (Mode.DISCUSS, Mode.PLAN) and consequential:
            return Decision(False, f"{self.mode.value} mode is read-only")

        # 写路径必须在可写根内
        if is_write:
            path = arguments.get("path")
            if path is not None and not self._under_writable_root(str(path)):
                return Decision(False, f"path not in writable root: {path}")

        # 低风险始终允许
        if not consequential:
            return Decision(True, "low risk")

        # AUTO 全权
        if self.mode is Mode.AUTO:
            return Decision(True, "full access")

        # 白名单/会话允许
        if is_shell:
            command = str(arguments.get("command", ""))
            if self._command_allowed(command):
                return Decision(True, "command on allowlist")
            if command and command in self.session_allow_commands:
                return Decision(True, "command allowed for session")
        if tool_name in self.session_allow_tools:
            return Decision(True, "tool allowed for session")

        # 任务级 standing rules: 精确 target 绑定才自动允许
        if tool_name in self.task_rules:
            target = self._rule_target(tool_name, arguments)
            if target and target in self.task_rules[tool_name]:
                rule = f"{tool_name} → {target}"
                return Decision(True, f"allowed by standing rule: {rule}", rule=rule)

        # CUSTOM 模式自动允许配置的工具
        if self.mode is Mode.CUSTOM and tool_name in self.auto_allow_tools:
            return Decision(True, "auto-allowed by config")

        # 否则询问
        return Decision(False, "requires approval", needs_user=True)

    @staticmethod
    def _rule_target(tool_name: str, arguments: dict) -> Optional[str]:
        """standing rule 的目标参数（连接器类工具声明 target 参数）. """
        for key in ("target", "channel", "recipient", "url", "path"):
            v = arguments.get(key)
            if v:
                return str(v).strip()
        return None

    # ── 会话记忆 ──

    def allow_tool_for_session(self, tool_name: str) -> None:
        self.session_allow_tools.add(tool_name)

    def allow_command_for_session(self, command: str) -> None:
        if command:
            self.session_allow_commands.add(command)

    def add_task_rule(self, tool_name: str, target: str) -> bool:
        """添加任务级 standing rule（tool → target 精确授权）."""
        if not tool_name or not target:
            return False
        self.task_rules.setdefault(tool_name, set()).add(target)
        return True

    def revoke_task_rule(self, tool_name: str, target: str) -> bool:
        targets = self.task_rules.get(tool_name)
        if not targets or target not in targets:
            return False
        targets.discard(target)
        return True
