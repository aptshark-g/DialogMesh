# -*- coding: utf-8 -*-
"""TaskRunner 测试 — 蓝图约束注入 / 重规划循环 / 三层介入 / 复盘回流。"""
import pytest

from core.agent.llm.task_runner import TaskConstraint, TaskRunner


def _make_loop(responses):
    """Fake llm_loop: 按顺序消费 responses（可含 steps 喂 on_step）。"""
    calls = []
    pool = list(responses) if isinstance(responses, list) else [responses]

    def loop(msgs, model="", max_rounds=6, allowed_tools=None,
             system_inject=None, on_step=None, timeout_s=0.0,
             symbol_interval=0, symbol_keep_last=2):
        calls.append({
            "system_inject": system_inject, "allowed_tools": allowed_tools,
            "max_rounds": max_rounds,
        })
        resp = pool.pop(0) if len(pool) > 1 else pool[0]
        for step in resp.get("steps", []):
            if on_step:
                on_step(step)
        return {
            "content": resp.get("content", ""),
            "tool_calls": resp.get("tool_calls", []),
            "rounds": resp.get("rounds", 1),
            "trace": [], "error": resp.get("error", ""),
        }
    return loop, calls


def _fail_resp():
    return {"steps": [{"round": 1, "tool": "run_shell", "ok": False,
                       "latency_ms": 10, "error": "boom"} for _ in range(2)],
            "content": ""}


class _FakeExecutionTree:
    """执行轨迹落树（P0）: 记录 create_task/spawn/complete 调用。"""
    def __init__(self):
        self.created = []
        self.spawned = []
        self.completed = []
        self.nodes = []

    def create_task(self, plan, parent_id=None):
        self.created.append(plan)
        return type("N", (), {"node_id": "exec_root"})()

    def spawn_sub_agent(self, parent_id, task, context_size,
                        pointers=None, queries=None):
        self.spawned.append((parent_id, task, context_size))
        # 阶段 0: 返回节点对象（_step_hook 写 outcome/input）
        node = type("N", (), {"content": {}})()
        self.nodes.append(node)
        return node

    def complete_node(self, node_id, result):
        self.completed.append((node_id, result))


def test_execution_trace_lands_in_tree():
    """P0 执行轨迹落树: 任务→create_task, 每步→spawn, 收尾→complete。"""
    tree = _FakeExecutionTree()
    loop, _ = _make_loop({"content": "完成", "steps": [
        {"round": 1, "tool": "write_file", "args": "hello.py",
         "ok": True, "latency_ms": 5,
         "input": '{"path": "hello.py"}'},
        {"round": 2, "tool": "run_python", "args": "python hello.py",
         "ok": True, "latency_ms": 8,
         "input": '{"command": "python hello.py"}'},
    ]})
    runner = TaskRunner(llm_loop=loop, execution_tree=tree)
    res = runner.run("写 hello.py 并运行",
                     constraint=TaskConstraint(goal="写 hello.py 并运行"))
    assert res.status == "ok"
    assert len(tree.created) == 1
    assert tree.created[0]["strategy"] == "TOOL_LOOP"
    assert len(tree.spawned) == 2
    assert tree.spawned[0][1].startswith("write_file")
    # 阶段 0（吸收 A2/O3）: 每步 outcome 词汇化 + 输入摘要落节点
    assert tree.nodes[0].content["outcome"] == "success"
    assert tree.nodes[1].content["outcome"] == "success"
    assert '"path": "hello.py"' in tree.nodes[0].content["input"]
    assert len(tree.completed) == 1
    assert tree.completed[0][1]["tools"] == ["write_file", "run_python"]
    assert tree.completed[0][1]["status"] == "ok"


def test_constraint_injection_into_system_prompt():
    loop, calls = _make_loop({"content": "完成", "steps": [
        {"round": 1, "tool": "run_python", "ok": True, "latency_ms": 5}]})
    runner = TaskRunner(llm_loop=loop)
    constraint = TaskConstraint(
        goal="写一个 hello world", scope="只允许在项目根目录",
        allowed_tools=["write_file", "run_python"], max_rounds=3)
    result = runner.run("写一个 hello world", constraint=constraint)
    assert result.status == "ok"
    assert "写一个 hello world" in calls[0]["system_inject"]
    assert "只允许在项目根目录" in calls[0]["system_inject"]
    assert calls[0]["allowed_tools"] == ["write_file", "run_python"]
    assert calls[0]["max_rounds"] == 3


def test_ok_continue_no_events():
    loop, _ = _make_loop({"content": "任务完成", "steps": [
        {"round": 1, "tool": "run_python", "ok": True, "latency_ms": 5}]})
    runner = TaskRunner(llm_loop=loop)
    result = runner.run("goal", constraint=TaskConstraint(goal="goal"))
    assert result.verdict == "continue"
    assert result.status == "ok"
    assert result.content == "任务完成"
    assert result.replans == 0
    assert result.events == []


def test_replan_loop_with_replanner():
    loop, calls = _make_loop([_fail_resp(), {"content": "改造完成", "steps": [
        {"round": 1, "tool": "run_python", "ok": True, "latency_ms": 5}]}])

    def replanner(goal, verdict):
        return TaskConstraint(goal="下载开源成品并改造",
                              allowed_tools=["run_shell"])

    runner = TaskRunner(llm_loop=loop, replanner=replanner)
    result = runner.run("手搓 MC 游戏", constraint=TaskConstraint(
        goal="手搓 MC 游戏", max_replans=1))
    assert result.status == "ok"
    assert result.verdict == "continue"
    assert result.replans == 1
    assert result.content == "改造完成"
    # 第二次注入携带新目标
    assert "下载开源成品并改造" in calls[1]["system_inject"]
    # 决策事件已写（meta_advice 路由, 可回看）
    assert len(result.events) >= 1
    assert result.events[0]["event"]["kind"] == "meta_advice"


def test_no_replanner_ask_user():
    loop, _ = _make_loop([_fail_resp()])
    runner = TaskRunner(llm_loop=loop)
    result = runner.run("goal", constraint=TaskConstraint(
        goal="goal", max_replans=1))
    assert result.status == "ask_user"
    assert result.verdict == "ask_user"
    assert "无可自动替换方案" in result.reason


def test_high_risk_sync_required_aborts(monkeypatch):
    loop, _ = _make_loop([_fail_resp()])
    runner = TaskRunner(llm_loop=loop, replanner=lambda g, v: TaskConstraint(
        goal="alternative"))
    monkeypatch.setattr(
        runner._intervention, "route",
        lambda **kw: {"level": "high", "status": "proposed",
                      "sync_required": True, "event": {}})
    result = runner.run("goal", constraint=TaskConstraint(
        goal="goal", max_replans=1))
    assert result.status == "aborted"
    assert result.verdict == "abort"
    assert "等待用户确认" in result.reason


def test_writeback_to_meta_feedback():
    audits = []
    loop, _ = _make_loop({"content": "done", "steps": [
        {"round": 1, "tool": "run_python", "ok": True, "latency_ms": 5}]})

    class FakeFeedback:
        def consume(self, audit):
            audits.append(audit)

    runner = TaskRunner(llm_loop=loop, meta_feedback=FakeFeedback())
    runner.run("goal", constraint=TaskConstraint(goal="goal"),
               request_id="req1")
    assert len(audits) == 1
    assert audits[0].dag_quality_score == 1.0


def test_build_inject_contains_discipline():
    inject = TaskRunner.build_inject(TaskConstraint(
        goal="g", scope="s", allowed_tools=["dir_list"]))
    assert "## 当前任务节点目标" in inject
    assert "## 允许范围" in inject
    assert "dir_list" in inject
    assert "不越界" in inject
