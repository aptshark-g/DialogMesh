"""Tests for MetaCognition + Scheduler + Workspace + Runtime loop."""
import pytest
from core.agent.v4.cognitive.metacognition import MetaCognition, MetaReflection, META_PROMPT
from core.agent.v4.cognitive.scheduler import Observer, CognitiveTask, CognitiveScheduler
from core.agent.v4.cognitive.workspace import (
    CognitiveWorkspace, WorkspaceGraph, WorkspaceNode, ExecutionTrace, TraceStep,
)
from core.agent.v4.cognitive.runtime import run_cognitive_loop


class TestMetaReflection:
    def test_default_fields(self):
        mr = MetaReflection()
        assert mr.confidence_self == 0.5
        assert mr.next_action == "REASON"
        assert isinstance(mr.gaps, list)

    def test_custom_action(self):
        mr = MetaReflection(next_action="COMMIT", confidence_self=0.85)
        assert mr.next_action == "COMMIT"
        assert mr.confidence_self == 0.85


class TestMetaCognition:
    def test_fallback_low_confidence(self):
        mc = MetaCognition()  # no LLM provider
        ws = CognitiveWorkspace(id="test", confidence=0.2, state="REASONING")
        reflection = mc.reflect(ws)
        assert reflection.next_action == "RETRIEVE"
        assert "confidence" in reflection.action_reason.lower()

    def test_fallback_high_confidence(self):
        mc = MetaCognition()
        ws = CognitiveWorkspace(id="test", confidence=0.8,
                                hypotheses=[{"content": "test hypothesis"}],
                                state="REASONING")
        reflection = mc.reflect(ws)
        assert reflection.next_action == "COMMIT"

    def test_fallback_single_hypothesis(self):
        mc = MetaCognition()
        ws = CognitiveWorkspace(id="test", confidence=0.5,
                                hypotheses=[{"content": "only one"}],
                                state="REASONING", reasoning_depth=1)
        reflection = mc.reflect(ws)
        assert reflection.next_action == "EXPAND"

    def test_parse_valid_json(self):
        mc = MetaCognition()
        text = '{"confidence_self": 0.7, "gaps": ["missing data"], "next_action": "RETRIEVE", "action_target": "test", "action_reason": "need more", "need_expand": false, "expand_targets": [], "has_contradiction": false, "contradiction_desc": ""}'
        reflection = mc._parse(text)
        assert reflection.confidence_self == 0.7
        assert reflection.next_action == "RETRIEVE"
        assert reflection.action_target == "test"

    def test_serialize_workspace(self):
        mc = MetaCognition()
        ws = CognitiveWorkspace(
            id="test",
            goal="test goal",
            active_objects=["A", "B"],
            hypotheses=[{"content": "hypothesis 1"}],
            confidence=0.6,
            state="REASONING",
        )
        text = mc._serialize_workspace(ws)
        assert "test goal" in text
        assert "A" in text
        assert "hypothesis 1" in text


class TestScheduler:
    def test_maps_retrieve(self):
        mc = MetaCognition()
        scheduler = CognitiveScheduler(metacognition=mc)
        obs = Observer(id="test")
        ws = CognitiveWorkspace(id="test", confidence=0.2)
        obs.workspace = ws
        task = scheduler.next(obs)
        assert task.type == "RETRIEVE"

    def test_maps_commit(self):
        mc = MetaCognition()
        scheduler = CognitiveScheduler(metacognition=mc)
        obs = Observer(id="test")
        ws = CognitiveWorkspace(id="test", confidence=0.85,
                                hypotheses=[{"content": "h1"}])
        obs.workspace = ws
        task = scheduler.next(obs)
        assert task.type == "COMMIT"

    def test_no_metacognition_defaults_to_reason(self):
        scheduler = CognitiveScheduler()
        obs = Observer(id="test")
        ws = CognitiveWorkspace(id="test")
        obs.workspace = ws
        task = scheduler.next(obs)
        assert task.type == "REASON"

    def test_execute_updates_workspace(self):
        scheduler = CognitiveScheduler()
        obs = Observer(id="test")
        ws = CognitiveWorkspace(id="test", state="INIT")
        obs.workspace = ws
        task = CognitiveTask("EXPAND", target=["TestObject"])
        scheduler.execute(obs, task)
        assert "TestObject" in ws.active_objects
        assert ws.state == "EXPANDING"


class TestWorkspace:
    def test_workspace_creation(self):
        ws = CognitiveWorkspace(id="test", goal="test")
        assert ws.id == "test"
        assert ws.goal == "test"
        assert ws.state == "INIT"

    def test_workspace_graph(self):
        graph = WorkspaceGraph()
        ws1 = CognitiveWorkspace(id="ws1")
        node1 = WorkspaceNode(workspace=ws1, status="running")
        graph.add(node1)
        assert graph.root_id == "ws1"

        ws2 = CognitiveWorkspace(id="ws2", parent_id="ws1")
        node2 = WorkspaceNode(workspace=ws2, status="done")
        graph.add(node2, parent_id="ws1")
        assert "ws2" in graph.nodes["ws1"].children

        # Merge: child done → merge hypotheses into parent
        ws2.hypotheses = [{"content": "from child"}]
        ws2.confidence = 0.9
        graph.merge("ws1")
        assert len(ws1.hypotheses) >= 1

    def test_execution_trace(self):
        trace = ExecutionTrace(session_id="test_session")
        trace.add(TraceStep(step_id="s1", state="PERCEIVE", decision="found objects"))
        trace.add(TraceStep(step_id="s2", state="REASON", decision="reasoning"))
        assert len(trace.steps) == 2
        assert "PERCEIVE" in trace.summary()
        assert "REASON" in trace.summary()

    def test_trace_to_dict(self):
        trace = ExecutionTrace(session_id="test")
        trace.add(TraceStep(step_id="s1", state="REASON", latency_ms=100.0))
        d = trace.to_dict()
        assert d["session_id"] == "test"
        assert len(d["steps"]) == 1


class TestRunLoop:
    def test_run_without_engine(self):
        """Loop should complete even without engine (no LLM calls)."""
        mc = MetaCognition()
        scheduler = CognitiveScheduler(metacognition=mc)
        obs = Observer(id="test", token_budget=1000)
        trace = run_cognitive_loop(
            observer=obs,
            scheduler=scheduler,
            engine=None,
            question="test question",
            max_iterations=3,
        )
        assert len(trace.steps) >= 2  # PERCEIVE + at least 1 cycle
        assert "PERCEIVE" in trace.summary()

    def test_commits_when_confidence_high(self):
        mc = MetaCognition()
        scheduler = CognitiveScheduler(metacognition=mc)
        obs = Observer(id="test")
        ws = CognitiveWorkspace(
            id="ws_test", confidence=0.85,
            hypotheses=[{"content": "h1"}], state="REASONING",
        )
        obs._workspace = ws
        node = WorkspaceNode(workspace=ws, status="running")
        obs._workspace_graph = WorkspaceGraph()
        obs._workspace_graph.add(node)

        task = scheduler.next(obs)
        assert task.type == "COMMIT"
