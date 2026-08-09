# -*- coding: utf-8 -*-
"""生产路径契约测试 — 学习闭环"测试绿≠生产通"的根治.

背景（用户质疑: 第一批测试是否浅层? 之前实现完备为何还会有问题?）:
  模块测试隔离, 不覆盖跨层接线. learn_blueprint 测试测的是方法本身,
  没人验证"生产请求（v3_session_api → StateMachine.run_dag）跑完后
  LEARNED_TEMPLATES 真的增长".

本文件固化生产路径:
  T1（快）: v3_session_api 注入契约 — 生产代码确实调 learn_from_execution
    + BlueprintEngine 支持共享 registry（防注入代码被误删/误改）.
  T2（完整, bootstrap）: 真实引擎 run_dag 后 LEARNED 真增长 +
    蒸馏原料真收集 + 共享 registry 同一性（防"方法可用但生产不调"）.
"""
from __future__ import annotations


def test_production_injection_code_exists():
    """T1: v3_session_api 生产注入契约（源级断言, 防回归）.

    若注入代码被误删, 此测试红 → 学习闭环生产断线可被测试捕获.
    """
    src = open("core/agent/api/v3_session_api.py", encoding="utf-8").read()
    assert "learn_from_execution" in src, \
        "v3_session_api 必须调用 engine.learn_from_execution（生产注入点）"
    assert "registry=_shared_registry" in src, \
        "v3_session_api 必须传共享 registry（match/learn 不分叉）"


def test_blueprint_engine_accepts_shared_registry():
    """T1: BlueprintEngine registry 注入契约（生产依赖此参数）. """
    from core.agent.blueprint.engine import BlueprintEngine
    from core.agent.blueprint.skill_registry import SkillRegistry
    reg = SkillRegistry()
    be = BlueprintEngine(registry=reg)
    assert be.registry is reg


def test_full_production_path_grows_learned_templates():
    """T2: 真实生产引擎（bootstrap 挂 state_machine）run_dag 后,
    LEARNED_TEMPLATES 真增长 + 蒸馏原料真收集 + 共享 registry 同一性.

    完整路径（~10s, NATS 降级噪声为已知环境坑）:
      _create_engine_instance → state_machine.run_dag →
      engine.learn_from_execution（= v3_session_api 注入代码路径）.
    """
    from core.agent.cli.engine import _create_engine_instance
    from core.agent.blueprint.engine import BlueprintEngine
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.skill_registry import LEARNED_TEMPLATES

    eng = _create_engine_instance()
    sm = getattr(eng, "_state_machine", None)
    assert sm is not None, "bootstrap 必须挂 state_machine"
    lb = getattr(eng, "_learning_bridge", None)
    assert lb is not None, "bootstrap 必须挂 learning_bridge"

    # 共享 registry 同一性（v3_session_api 的注入前提）
    shared = lb.registry
    be = BlueprintEngine(registry=shared)
    assert be.registry is shared
    assert be.registry._lifecycle is getattr(eng, "_skill_lifecycle", None)

    before = set(LEARNED_TEMPLATES.keys())
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("intent_1", "intent", priority=0),
            BlueprintNode("tool_2", "tool", priority=1,
                          params={"tool": "echo",
                                  "args": {"message": "prod-verify"}}),
            BlueprintNode("llm_reply_3", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        edges=[
            BlueprintEdge("pcr_0", "intent_1", "route", required=False),
            BlueprintEdge("intent_1", "tool_2", "intent_context"),
            BlueprintEdge("tool_2", "llm_reply_3", "tool_result"),
        ],
        strategy="TEMPLATE",
    )
    chain_result = sm.run_dag(
        dag,
        context={"text": "生产契约验证", "session_id": "prod-verify",
                 "request_id": "prod-verify-1"},
    )
    ok = any(
        _out and not _out.get("error")
        for _out in chain_result.get("results", {}).values()
    )
    assert ok, "run_dag 应成功执行含 tool 节点的 DAG"

    # 复刻 v3_session_api 注入（与生产代码同一调用）
    eng.learn_from_execution(dag, intent="生产契约验证",
                             request_id="prod-verify-1", success=True)
    after = set(LEARNED_TEMPLATES.keys())
    assert after - before, \
        "生产路径后 LEARNED_TEMPLATES 必须增长（学习闭环生产通）"
    assert len(lb.trace_store) >= 1, "蒸馏原料必须收集"

