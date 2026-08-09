"""Behavior chain P1: BehaviorBrain kernel + engine/handlers wiring (ADR-013)."""
import time

import pytest

from core.agent.behavior.brain import BehaviorBrain, extract_action
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep
from core.agent.events.event_ir import EventIR


def _evt(eid, text, kind="user_message"):
    return EventIR(
        id=eid, kind=kind, payload={"text": text}, metadata={}, timestamp=time.time(),
    )


def _wait_predict(brain, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if brain.stats()["predict_count"] >= 1:
            return brain._pending_prediction
        time.sleep(0.1)
    return None


class TestBrainKernel:
    def test_empty_graph_fallback(self):
        brain = BehaviorBrain(graph=None, llm_provider=None)
        brain.learn_from_event(_evt("e1", "帮我写个排序"))
        assert brain._learn_count == 0  # no pending prediction to learn from
        assert brain.predict_next_background() is True
        pred = _wait_predict(brain)
        assert pred is not None
        assert pred.query_mode == "fallback"
        assert brain.stats()["predict_count"] == 1

    def test_graph_no_llm_hints(self):
        g = BehaviorGraph()
        g.add_step(BehaviorStep("s1", "写代码", "code"))
        g.add_step(BehaviorStep("s2", "测试", "test"))
        g.record_edge(g.nodes["s1"], g.nodes["s2"], success=True)
        brain = BehaviorBrain(graph=g, llm_provider=None)
        brain.learn_from_event(_evt("e1", "继续测试"))
        assert brain.predict_next_background() is True
        pred = _wait_predict(brain)
        assert pred is not None
        assert pred.query_mode in ("no_llm", "no_graph", "fallback", "full")

    def test_learning_chain(self):
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=None)
        brain.learn_from_event(_evt("e1", "部署服务"))
        brain.predict_next_background()
        _wait_predict(brain)
        # Second event consumes the pending prediction → learning happens.
        brain.learn_from_event(_evt("e2", "部署完成，继续监控"))
        stats = brain.stats()
        assert stats["learn_count"] == 1
        assert stats["training"]["total_updates"] >= 1
        # Profile updated from observed action.
        assert brain.profile.total_turns == 2

    def test_shutdown_stops_new_predictions(self):
        brain = BehaviorBrain(graph=None, llm_provider=None)
        brain.shutdown()
        assert brain.predict_next_background() is False

    def test_extract_action_mapping(self):
        e = EventIR(
            id="x", kind="config.change",
            payload={"text": "改配置"}, metadata={}, timestamp=time.time(),
        )
        summary, atype = extract_action(e)
        assert atype == "config"
        assert summary == "改配置"

    def test_value_ranker_injected_dimensions(self):
        """P1-2: load_est + prof_matcher injected → both dimensions live."""
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=None)
        assert brain._value_ranker.load_est is not None
        assert brain._value_ranker.prof_matcher is not None
        assert brain.training_loop.graph is brain.graph


class TestEngineWiring:
    def _make_engine(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        from core.agent.behavior.adapter import BehaviorGraphAdapter
        engine = CognitiveRuntimeEngine()
        engine._behavior_graph_adapter = BehaviorGraphAdapter(
            graph_path=None, auto_save=False,
        )
        return engine

    def test_engine_behavior_phase_runs_brain(self):
        engine = self._make_engine()
        from core.agent.event.statemachine import DeciderStateMachine, PipelinePhase
        sm = DeciderStateMachine()

        def handle_behavior(ctx):
            bg = engine._behavior_graph_adapter
            text = ctx.get("text", "")
            evt = _evt("iso1", text)
            bg.record_event(evt, success=True)
            engine._run_behavior_brain(evt)
            return {"recorded": True}

        sm.register_handler(PipelinePhase.BEHAVIOR, handle_behavior)
        sm.register_handler(PipelinePhase.DONE, lambda ctx: {})
        from core.agent.event.statemachine import STATE_TRANSITIONS
        STATE_TRANSITIONS[PipelinePhase.BEHAVIOR] = {"normal": PipelinePhase.DONE}
        engine._state_machine = sm

        resp = engine.on_event_sm(_evt("iso2", "帮我看下日志"), start_phase="behavior")
        assert resp is None
        assert engine._behavior_brain is not None
        stats = engine._behavior_brain_stats()
        assert stats["ready"] is True
        pred = _wait_predict(engine._behavior_brain)
        assert pred is not None
        engine.stop()

    def test_engine_stop_shuts_down_brain(self):
        engine = self._make_engine()
        engine._run_behavior_brain(_evt("s1", "hello"))
        assert engine._behavior_brain is not None
        engine.stop()
        assert engine._behavior_brain._stopped is True

    def test_register_with_engine_attaches_brain(self):
        from core.agent.behavior.runtime_hook import register_with_engine
        engine = self._make_engine()
        hook = register_with_engine(engine, graph_path=None, enable_causal=False)
        assert hook._brain is not None
        assert engine._behavior_brain is hook._brain
        hook.on_event(_evt("r1", "hello"))
        stats = hook.stats()
        assert "brain" in stats
        engine.stop()
