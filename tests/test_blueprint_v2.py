# -*- coding: utf-8 -*-
"""Blueprint P0 contract tests — deterministic (fake components, no models/net).

Alignment: DESIGN_DEEP_AUDIT §四 P0 + §7.2/§7.6. Red-to-green discipline:
each assertion targets a real contract that previously failed in probes
(singleton pollution, fake fallbacks, lost nodes, crash on bad LLM output).
"""

import copy
import json
import os
from types import SimpleNamespace

import pytest

from core.agent.blueprint.engine import BlueprintEngine
from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.skill_registry import BUILTIN_TEMPLATES, SkillRegistry
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge


# ═══ Fakes (injected, no model/network) ═══

class FakePCR:
    @classmethod
    def route(cls, text, history=None, subgraph_prior=None):
        return SimpleNamespace(
            zone="CODING", x_axis=0.4, y_axis=0.6, z_axis=0.1,
            cognitive_level="moderate", execution_mode="auto",
            labels={"temperature": "warm"},
        )


class FakeDualTrack:
    def process(self, text, profile=None, association=None, history=None):
        return SimpleNamespace(segments=["代码分析"], confidence=0.9, source="test")


class FakeSubgraph:
    def compile_dialogue(self, intent="general_query", intent_category=None,
                         zone=None, **kw):
        return SimpleNamespace(compile_strategy="summary_fallback",
                               entries=[], perspective="dialogue")


class FakeUnified:
    def assemble(self, perception, token_budget=None):
        return {"dialogue_context": "ctx", "meta_context": "", "stats": {}}


def make_executor(**kw):
    defaults = dict(
        pcr_router=FakePCR,
        dual_track=FakeDualTrack(),
        subgraph_compiler=FakeSubgraph(),
    )
    defaults.update(kw)
    ex = BlueprintExecutor(**defaults)
    ex._unified_context = FakeUnified()
    ex._event_log = False  # disable EventLog writes in tests
    return ex


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Mock the switch gateway for ALL tests (deterministic, no local switch).

    Implementation goes through the gateway for uniformity; tests never
    depend on whether the local switch (127.0.0.1:8080) is running.
    """
    monkeypatch.setattr("core.agent.blueprint.executor.call_switch",
                        lambda *a, **k: "测试回复")


# ═══ 1. Template immutability (P0-1) ═══

def test_hybrid_override_does_not_pollute_global_template():
    before = len(BUILTIN_TEMPLATES["task_planning"].nodes)
    eng = BlueprintEngine()
    eng.builder._call_llm = lambda *a, **k: (
        '{"action":"modify","add":[{"node_id":"subgraph_x","chain":"subgraph",'
        '"deps":["ghost"]}],"remove":[],"reorder":{}}'
    )
    dag = eng.build("帮我规划项目", intent="任务规划")
    after = len(BUILTIN_TEMPLATES["task_planning"].nodes)
    assert before == after
    assert dag is not BUILTIN_TEMPLATES["task_planning"]
    assert not any(e.from_node == "ghost"
                   for e in BUILTIN_TEMPLATES["task_planning"].edges)


def test_recovery_strategy_not_overwritten():
    eng = BlueprintEngine()
    eng.builder._call_llm = lambda *a, **k: (
        '{"action":"modify","add":[{"node_id":"subgraph_x","chain":"subgraph",'
        '"deps":["ghost"]}],"remove":[],"reorder":{}}'
    )
    dag = eng.build("帮我规划项目", intent="任务规划")
    assert dag.strategy == "RECOVERY"


def test_cache_return_is_copy_mutation_isolated():
    eng = BlueprintEngine()
    d1 = eng.build("分析任务", intent="代码分析")
    d1.nodes = []  # caller mutation must not poison cache
    d2 = eng.build("分析任务", intent="代码分析")
    # 订阅表语义重构后: Tick0(pcr∥intent) + Tick1(context∥subgraph) +
    # Tick2(llm_reply) + async(meta_audit∥behavior_learn) = 7 节点
    assert d2.node_count == 7
    assert d1 is not d2


# ═══ 2. Converge robustness (P1-9 / P2-19) ═══

def test_converge_bad_confidence_no_crash():
    from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder
    b = LLMDAGBuilder()
    calls = {"n": 0}
    def fake(system, user, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return '[{"path":[{"chain":"pcr","reason":"r"},' \
                   '{"chain":"llm_reply","reason":"r"}],' \
                   '"confidence":0.9,"rationale":"r"}]'
        return '{"nodes":[{"node_id":"pcr_0","chain":"pcr"},' \
               '{"node_id":"llm_1","chain":"llm_reply"}],' \
               '"edges":[{"from_node":"pcr_0","to_node":"llm_1",' \
               '"data_key":"route","required":"false"}],' \
               '"confidence":"high","design_rationale":"x"}'
    b._call_llm = fake
    dag = b.build_llm_driven("t", "通用对话")
    assert dag is not None
    assert dag.confidence == 0.5
    assert dag.edges[0].required is False


def test_empty_intent_guard():
    r = SkillRegistry()
    s, bp = r.match("")
    assert s == "HYBRID"
    assert bp is BUILTIN_TEMPLATES["general_chat"]


# ═══ 3. Executor: real chain outputs, no fake data (P0-3/P0-4) ═══

def test_executor_real_chain_outputs():
    ex = make_executor()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("pcr_0", "pcr"), BlueprintNode("intent_1", "intent"),
               BlueprintNode("llm_2", "llm_reply", priority=1)],
        edges=[BlueprintEdge("pcr_0", "intent_1", "route"),
               BlueprintEdge("pcr_0", "llm_2", "route"),
               BlueprintEdge("intent_1", "llm_2", "intent_context")],
        strategy="TEMPLATE")
    res = ex.execute(dag, user_text="分析代码")
    outs = res["chain_outputs"]
    assert outs["pcr_0"]["route"]["zone"] == "CODING"      # real PCR V2 shape
    assert outs["intent_1"]["intents"]["segments"] == ["代码分析"]
    assert outs["llm_2"]["mode"] == "llm"                  # gateway (mocked)
    assert outs["llm_2"]["response"] == "测试回复"


def test_profile_no_fake_fallback(monkeypatch):
    ex = make_executor()
    # Simulate profile API down → must degrade, never inject fake INFJ data.
    def _down(url, timeout=5):
        raise OSError("profile down")
    monkeypatch.setattr("urllib.request.urlopen", _down)
    out = ex._handle_profile(None, {}, "hi")
    assert out["status"] == "unavailable"
    assert "INFJ" not in out.get("profile_text", "")


def test_same_tick_reversed_order_no_lost_nodes():
    ex = make_executor()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("b", "intent", priority=0),
               BlueprintNode("a", "pcr", priority=0),
               BlueprintNode("c", "llm_reply", priority=1)],
        edges=[BlueprintEdge("a", "b", "route"),
               BlueprintEdge("a", "c", "route"),
               BlueprintEdge("b", "c", "intent_context")],
        strategy="TEMPLATE")
    res = ex.execute(dag, user_text="hi")
    assert "a" in res["chain_outputs"]
    assert "b" in res["chain_outputs"]   # dep on same-tick a, defined after
    assert "c" in res["chain_outputs"]


def test_llm_reply_mode_dispatch(monkeypatch):
    ex = make_executor()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("a", "pcr"), BlueprintNode("l", "llm_reply", priority=1,
                                                        params={"reply_mode": "llm"})],
        edges=[BlueprintEdge("a", "l", "route")],
        strategy="HYBRID")
    monkeypatch.setattr("core.agent.blueprint.executor.call_switch",
                        lambda *a, **k: "真实回复")
    res = ex.execute(dag, user_text="hi")
    assert res["chain_outputs"]["l"]["mode"] == "llm"
    assert res["llm_reply"] == "真实回复"


# ═══ 4. DAG snapshot (T4, §7.5) ═══

def test_dag_snapshot_written(tmp_path, monkeypatch):
    ex = make_executor()
    monkeypatch.chdir(tmp_path)  # snapshot dir is data/ under cwd
    dag = BlueprintDAG(
        nodes=[BlueprintNode("a", "pcr"), BlueprintNode("l", "llm_reply", priority=1)],
        edges=[BlueprintEdge("a", "l", "route")],
        strategy="TEMPLATE")
    ex.execute(dag, user_text="hi", request_id="req_test")
    snap = tmp_path / "data" / "blueprint_dags" / "req_test.json"
    assert snap.exists()
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["request_id"] == "req_test"
    assert {n["node_id"] for n in data["nodes"]} == {"a", "l"}
    assert "a" in data["outputs"]
