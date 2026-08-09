# -*- coding: utf-8 -*-
"""GAP-1 权限引擎测试（COMPLETENESS_GAP_INVENTORY §C, OpenWorker 对标）.

覆盖:
  - classify_tool: 名表（write/exec）+ metadata（risk/requires_approval）+ read 兜底
  - RiskClass/Mode 枚举
  - evaluate: 低风险始终允许 / write 路径根限制 / exec 命令白名单 token 前缀
  - shell 操作符检测（链式命令强制审批）
  - discuss/plan 只读模式拒绝 consequential
  - 会话白名单 + 任务级 standing rules（精确 target）
  - AUTO 全权 / CUSTOM auto_allow
"""
from __future__ import annotations

from core.agent.blueprint.permission_engine import (
    PermissionEngine, RiskClass, Mode, Decision,
    classify_tool, has_shell_operators,
)


# ═══════════════════════════════════════════════════════════════
# classify_tool
# ═══════════════════════════════════════════════════════════════

def test_classify_tool_by_name():
    assert classify_tool("write_file") == RiskClass.WRITE_LOCAL
    assert classify_tool("apply_patch") == RiskClass.WRITE_LOCAL
    assert classify_tool("run_shell") == RiskClass.EXEC
    assert classify_tool("echo") == RiskClass.READ


def test_classify_tool_by_metadata():
    assert classify_tool("gh_send", {"risk": "external"}) == RiskClass.EXTERNAL
    assert classify_tool("x", {"requires_approval": True}) == RiskClass.EXTERNAL
    assert classify_tool("x", {}) == RiskClass.READ


def test_has_shell_operators():
    assert has_shell_operators("git status && rm -rf ~")
    assert has_shell_operators("ls | grep x")
    assert not has_shell_operators("git status")


# ═══════════════════════════════════════════════════════════════
# evaluate
# ═══════════════════════════════════════════════════════════════

def test_low_risk_always_allowed():
    pe = PermissionEngine()
    d = pe.evaluate("echo", {"message": "hi"})
    assert d.allowed is True
    assert d.needs_user is False


def test_write_path_root_restriction():
    pe = PermissionEngine(workspace_root="C:/proj")
    # 根内路径 → 询问（interactive 默认）
    d = pe.evaluate("write_file", {"path": "C:/proj/a.txt"})
    assert d.needs_user is True
    # 根外路径 → 拒绝
    d2 = pe.evaluate("write_file", {"path": "C:/Windows/system32/x"})
    assert d2.allowed is False
    assert "writable root" in d2.reason


def test_exec_command_allowlist_token_prefix():
    pe = PermissionEngine(allowed_commands=["git status"])
    # 精确前缀 → 允许
    assert pe.evaluate("run_shell", {"command": "git status -s"}).allowed is True
    # 链式命令 → 强制审批（即使前缀匹配）
    d = pe.evaluate("run_shell", {"command": "git status && rm -rf ~"})
    assert d.needs_user is True
    # 非白名单 → 询问
    assert pe.evaluate("run_shell", {"command": "rm -rf x"}).needs_user is True


def test_readonly_modes_reject_consequential():
    for mode in (Mode.DISCUSS, Mode.PLAN):
        pe = PermissionEngine(mode=mode)
        d = pe.evaluate("write_file", {"path": "a.txt"})
        assert d.allowed is False
        assert "read-only" in d.reason
        # 低风险仍允许
        assert pe.evaluate("echo", {}).allowed is True


def test_auto_mode_full_access():
    pe = PermissionEngine(mode=Mode.AUTO)
    d = pe.evaluate("run_shell", {"command": "anything"})
    assert d.allowed is True


def test_session_allowlist():
    pe = PermissionEngine()
    pe.allow_tool_for_session("gh_send")
    assert pe.evaluate("gh_send", {}).allowed is True


def test_standing_rule_exact_target():
    pe = PermissionEngine()
    pe.add_task_rule("gh_comment", "repo#issue-1")
    meta = {"risk": "external"}  # 连接器工具需标 external 才走 standing rule
    # 精确 target → 自动允许 + 可审计 rule
    d = pe.evaluate("gh_comment", {"target": "repo#issue-1"}, metadata=meta)
    assert d.allowed is True
    assert d.rule == "gh_comment → repo#issue-1"
    # 其他 target → 询问
    d2 = pe.evaluate("gh_comment", {"target": "other#issue-2"}, metadata=meta)
    assert d2.needs_user is True
    # revoke 后不再允许
    pe.revoke_task_rule("gh_comment", "repo#issue-1")
    assert pe.evaluate("gh_comment", {"target": "repo#issue-1"},
                       metadata=meta).needs_user is True


def test_custom_mode_auto_allow():
    pe = PermissionEngine(mode=Mode.CUSTOM, auto_allow_tools={"read_file"})
    d = pe.evaluate("write_file", {"path": "a.txt"})
    assert d.needs_user is True  # 不在 auto_allow


def test_executor_uses_permission_engine_via_resolver():
    """集成: PermissionEngine 作为 PlanGate resolver — 高风险工具调用需审批."""
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.executor import BlueprintExecutor

    pe = PermissionEngine()
    calls = []

    def resolver(node, outputs):
        # tool 节点 → 权限引擎判定; write 类需 approve
        tool = node.params.get("tool", "")
        args = node.params.get("args", {}) or {}
        decision = pe.evaluate(tool, args)
        calls.append(decision)
        if decision.needs_user:
            return {"status": "rejected", "comment": decision.reason}
        return {"status": "approved"}

    class _Ex(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    ex = _Ex(gate_resolver=resolver)
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            # write_file 高风险 → resolver reject → 节点 error
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "write_file",
                                  "args": {"path": "x.txt", "content": "x"}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        strategy="TEMPLATE",
    )
    r = ex.execute(dag, user_text="写文件")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "error"
    assert "plan_gate rejected" in out["error"]
    assert calls and calls[0].needs_user is True
