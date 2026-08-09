# -*- coding: utf-8 -*-
"""G2 模板进化测试（FLOW_SELF_GROWTH）.

覆盖:
  - learn_blueprint 沉淀（含 tool 节点才沉淀）
  - match 时 LEARNED_TEMPLATES 优先
  - executor learn_hook 执行成功触发
  - 无 tool 节点不沉淀
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.skill_registry import (
    SkillRegistry, LEARNED_TEMPLATES,
)
from core.agent.blueprint.executor import BlueprintExecutor


def _tool_dag():
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "echo", "args": {"message": "x"}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        edges=[BlueprintEdge("pcr_0", "tool_1", "route", required=False)],
        strategy="TEMPLATE",
    )


def _plain_dag():
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("llm_reply_1", "llm_reply", priority=2),
        ],
        strategy="TEMPLATE",
    )


def test_learn_blueprint_registers():
    """含 tool 节点 → 沉淀到 LEARNED_TEMPLATES."""
    reg = SkillRegistry()
    assert reg.learn_blueprint("查论文", _tool_dag(), source_dag_id="d1")
    assert "查论文" in LEARNED_TEMPLATES
    assert "LEARNED" in LEARNED_TEMPLATES["查论文"].design_rationale


def test_learn_skips_plain_dag():
    """无 tool 节点 → 不沉淀."""
    reg = SkillRegistry()
    assert not reg.learn_blueprint("通用对话", _plain_dag())
    assert "通用对话" not in LEARNED_TEMPLATES


def test_match_prefers_learned():
    """match 时 LEARNED_TEMPLATES 优先（成功经验 > 通用种子）."""
    reg = SkillRegistry()
    reg.learn_blueprint("查论文", _tool_dag())
    strategy, dag = reg.match("查论文")
    assert strategy == "TEMPLATE"
    assert any(n.chain == "tool" for n in dag.nodes)


def test_executor_learn_hook_called():
    """executor 执行成功 → learn_hook 触发（含 tool 节点）."""
    learned = []

    def hook(dag, outputs, request_id):
        learned.append((dag, outputs, request_id))

    class _Ex(BlueprintExecutor):
        def __init__(self, **kw):
            super().__init__(**kw)
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "M"}, "status": "ok"}
        def _handle_llm_reply(self, node, outputs, text):
            return {"response": "final", "status": "ok"}

    ex = _Ex(learn_hook=hook)
    r = ex.execute(_tool_dag(), user_text="查论文", request_id="req1")
    assert len(learned) == 1
    assert learned[0][2] == "req1"
