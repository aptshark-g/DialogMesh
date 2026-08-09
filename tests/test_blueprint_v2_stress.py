# -*- coding: utf-8 -*-
"""Blueprint P0 deep/stress tests — concurrency, repeat, big graphs, extremes.

Not smoke tests: each case stresses a real failure mode that surfaced during
audit (shared-cache pollution, EventLog write failures, unordered LLM DAGs,
extremes of text/params). Monitoring assertions verify execution is not a
black box — per-node latency is returned with every result.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.agent.blueprint.engine import BlueprintEngine
from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
from core.agent.blueprint.skill_registry import BUILTIN_TEMPLATES


# Stress suite is slow (~100s) — excluded from the default `-m "not slow"` run.
pytestmark = pytest.mark.slow


class FakePCR:
    @classmethod
    def route(cls, text, history=None, subgraph_prior=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            zone="CODING", x_axis=0.4, y_axis=0.6, z_axis=0.1,
            cognitive_level="moderate", execution_mode="auto",
            labels={"temperature": "warm"},
        )


class FakeDualTrack:
    def __init__(self):
        self._calls = 0
    def process(self, text, profile=None, association=None, history=None):
        from types import SimpleNamespace
        self._calls += 1
        return SimpleNamespace(segments=[text[:8] or "空"], confidence=0.9,
                               source="test")


class FakeSubgraph:
    def compile_dialogue(self, intent="general_query", intent_category=None,
                         zone=None, **kw):
        from types import SimpleNamespace
        return SimpleNamespace(compile_strategy="summary_fallback",
                               entries=[], perspective="dialogue")


class FakeUnified:
    def assemble(self, perception, token_budget=None):
        return {"dialogue_context": "ctx", "meta_context": "", "stats": {}}


def make_executor(**kw):
    defaults = dict(pcr_router=FakePCR, dual_track=FakeDualTrack(),
                    subgraph_compiler=FakeSubgraph())
    defaults.update(kw)
    ex = BlueprintExecutor(**defaults)
    ex._unified_context = FakeUnified()
    ex._event_log = False
    return ex


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("core.agent.blueprint.executor.call_switch",
                        lambda *a, **k: "测试回复")


def std_dag(n_chain_nodes=3):
    nodes = [BlueprintNode("pcr_0", "pcr"), BlueprintNode("intent_1", "intent")]
    for i in range(n_chain_nodes):
        nodes.append(BlueprintNode(f"ctx_{i+2}", "context", priority=1))
    nodes.append(BlueprintNode("llm_N", "llm_reply", priority=2,
                               params={"reply_mode": "template"}))
    edges = [BlueprintEdge("pcr_0", "intent_1", "route")]
    for i in range(n_chain_nodes):
        edges.append(BlueprintEdge("intent_1", f"ctx_{i+2}", "intent_context"))
        edges.append(BlueprintEdge(f"ctx_{i+2}", "llm_N", "assembled_context"))
    return BlueprintDAG(nodes=nodes, edges=edges, strategy="TEMPLATE")


# ═══ A. Concurrency stress: shared executor across threads ═══

def test_concurrent_execute_shared_executor():
    ex = make_executor()
    dag = std_dag()
    errs = []
    def run(i):
        try:
            res = ex.execute(dag, user_text=f"并发任务{i}")
            assert "llm_N" in res["chain_outputs"]
            assert res["ticks"]
            # monitoring: every tick exposes per-node latency
            for t in res["ticks"]:
                assert t["node_latency"], f"missing node_latency in tick {t['tick']}"
        except Exception as e:  # pragma: no cover
            errs.append(e)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, range(32)))
    assert not errs


def test_concurrent_same_request_id_snapshot_no_crash(tmp_path, monkeypatch):
    ex = make_executor()
    monkeypatch.chdir(tmp_path)
    dag = std_dag(1)
    # Same request_id written concurrently — must not raise (last-writer wins)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: ex.execute(dag, user_text="x",
                                           request_id="same_id"), range(8)))
    snap = tmp_path / "data" / "blueprint_dags" / "same_id.json"
    assert snap.exists()


# ═══ B. Repeat stress: state stability, no leaks/pollution ═══

def test_repeat_execute_100x_stable():
    ex = make_executor()
    dag = std_dag()
    first = ex.execute(dag, user_text="repeat")
    for i in range(100):
        res = ex.execute(dag, user_text=f"repeat{i}")
        assert len(res["chain_outputs"]) == len(first["chain_outputs"])
    assert len(BUILTIN_TEMPLATES["task_planning"].nodes) == 6  # global intact


def test_repeat_build_cache_stable():
    eng = BlueprintEngine()
    dags = [eng.build(f"任务 {i}", intent="任务规划") for i in range(50)]
    counts = {d.node_count for d in dags}
    assert counts == {6}  # no drift/pollution across builds


# ═══ C. Big / adversarial DAGs ═══

def test_big_dag_20_nodes_multitick():
    ex = make_executor()
    nodes = [BlueprintNode("pcr_0", "pcr", priority=0)]
    edges = []
    for i in range(5):
        nodes.append(BlueprintNode(f"int_{i}", "intent", priority=0))
        edges.append(BlueprintEdge("pcr_0", f"int_{i}", "route"))
    for i in range(10):
        nodes.append(BlueprintNode(f"ctx_{i}", "context", priority=1))
        edges.append(BlueprintEdge(f"int_{i % 5}", f"ctx_{i}", "intent_context"))
    for i in range(4):
        nodes.append(BlueprintNode(f"sub_{i}", "subgraph", priority=1))
        edges.append(BlueprintEdge(f"ctx_{i+5}", f"sub_{i}", "assembled_context"))
    nodes.append(BlueprintNode("llm", "llm_reply", priority=2,
                               params={"reply_mode": "template"}))
    for i in range(4):
        edges.append(BlueprintEdge(f"sub_{i}", "llm", "compiled_subgraph"))
    dag = BlueprintDAG(nodes=nodes, edges=edges, strategy="TEMPLATE")
    res = ex.execute(dag, user_text="big")
    assert len(res["chain_outputs"]) == len(nodes)  # no node lost
    assert len(res["ticks"]) == 3


def test_unordered_llm_dag_fan_in():
    """LLM_DRIVEN-style unordered nodes with fan-in to llm_reply."""
    ex = make_executor()
    # deliberately unordered: llm first, pcr last in list, same tick deps
    nodes = [BlueprintNode("llm", "llm_reply", priority=1,
                           params={"reply_mode": "template"}),
             BlueprintNode("b", "intent", priority=0),
             BlueprintNode("a", "pcr", priority=0),
             BlueprintNode("c", "context", priority=1)]
    edges = [BlueprintEdge("a", "b", "route"),
             BlueprintEdge("b", "c", "intent_context"),
             BlueprintEdge("a", "c", "route"),
             BlueprintEdge("b", "llm", "intent_context"),
             BlueprintEdge("c", "llm", "assembled_context")]
    dag = BlueprintDAG(nodes=nodes, edges=edges, strategy="LLM_DRIVEN")
    res = ex.execute(dag, user_text="unordered")
    assert {"a", "b", "c", "llm"} <= set(res["chain_outputs"])


def test_cycle_detection_still_blocks():
    ex = make_executor()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("a", "pcr"), BlueprintNode("b", "intent"),
               BlueprintNode("l", "llm_reply")],
        edges=[BlueprintEdge("a", "b", "route"), BlueprintEdge("b", "l", "x"),
               BlueprintEdge("l", "b", "y")],
        strategy="TEMPLATE")
    # cycle: a→b→l→b. Multi-pass loop must terminate, not hang.
    res = ex.execute(dag, user_text="cyc")
    # l deps never satisfied (b requires l) → b/l marked skipped, a done
    assert res["chain_outputs"]["a"]["status"] == "ok"
    assert res["chain_outputs"]["b"]["status"] == "skipped"
    assert res["chain_outputs"]["l"]["status"] == "skipped"


# ═══ D. Extreme inputs ═══

@pytest.mark.parametrize("text", [
    "",
    " " * 100,
    "a" * 5000,
    "!" * 1000,
    "中文" * 1000,
    "mixed EN 中文 123 !@#$%^&*()",
])
def test_extreme_inputs_no_crash(text):
    ex = make_executor()
    dag = std_dag(1)
    res = ex.execute(dag, user_text=text)
    assert res["chain_outputs"]


def test_failing_event_log_degrades_not_crashes(tmp_path, monkeypatch):
    """EventLog write failures must not break execution (monitoring degrades)."""
    ex = make_executor()
    monkeypatch.chdir(tmp_path)
    ex._event_log = None  # force lazy init path
    def _boom(event_id, kind, payload):
        raise RuntimeError("eventlog disk full")
    class _FakeEventLog:
        def open(self):
            return None
        def put_event(self, event_id, kind, payload):
            _boom(event_id, kind, payload)
    ex._event_log = _FakeEventLog()
    res = ex.execute(std_dag(), user_text="x")
    assert "pcr_0" in res["chain_outputs"]


def test_snapshot_write_failure_degrades(tmp_path, monkeypatch):
    ex = make_executor()
    monkeypatch.chdir(tmp_path)
    # make data/ a file so mkdir fails → snapshot must degrade, not crash
    (tmp_path / "data").write_text("occupied", encoding="utf-8")
    res = ex.execute(std_dag(1), user_text="x", request_id="snap_fail")
    assert "pcr_0" in res["chain_outputs"]


# ═══ E. Monitoring visibility ═══

def test_monitoring_node_latency_present():
    ex = make_executor()
    res = ex.execute(std_dag(2), user_text="monitor")
    total_nodes = 0
    for t in res["ticks"]:
        total_nodes += len(t["node_latency"])
        assert all(v >= 0 for v in t["node_latency"].values())
    assert total_nodes >= 5
    assert res["latency_ms"] >= 0
