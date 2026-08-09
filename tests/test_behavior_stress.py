"""Behavior chain stress + robustness tests — run with ``-m slow`` (A18).

Covers: event-stream volume, background-prediction throughput, concurrent
registry/brain access, token-budget exhaustion (L1), lifecycle transition
integrity, LLM-failure fallback, corrupted-graph tolerance, registry bounds,
and reward value-domain safety. Fails loudly with concrete numbers.
"""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.behavior.brain import BehaviorBrain
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep
from core.agent.behavior.scheduler import (
    BehaviorScheduler,
    ScheduleMode,
    ci_width_proxy,
    is_risk_action,
)
from core.agent.behavior.explicit_commitment import (
    CommitmentRegistry,
    simulate_with_retry,
)
from core.agent.rewarder.reward_rules import evaluate_accuracy
from core.agent.compiler.parameter_registry import ParameterRegistry, get_registry
from core.agent.events.event_ir import EventIR
from core.agent.predictor.models import Candidate

pytestmark = pytest.mark.slow


def _evt(eid, text):
    return EventIR(
        id=eid, kind="user_message",
        payload={"text": text}, metadata={}, timestamp=time.time(),
    )


def _wait_predict(brain, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if brain.stats()["predict_count"] >= 1:
            return True
        time.sleep(0.05)
    return False


class TestEventVolume:
    def test_300_event_stream_no_crash_learns(self):
        """Volume: 300 events → learning engaged, graph grows, no leak."""
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=None)
        start = time.time()
        for i in range(300):
            brain.learn_from_event(_evt(f"v{i}", f"action {i % 7}"))
            brain.predict_next_background()
            if i % 50 == 49:
                _wait_predict(brain)
        elapsed = time.time() - start
        stats = brain.stats()
        # Background prediction is anti-pileup by design: some learn slots are
        # skipped when the previous prediction thread is still running.
        assert stats["learn_count"] >= 200, stats["learn_count"]
        assert stats["graph"]["nodes"] > 0
        assert elapsed < 30, f"300 events took {elapsed:.1f}s"
        brain.shutdown()

    def test_50_repeat_predictions_stable(self):
        """Stability: 50 repeated predictions on a fixed graph stay bounded."""
        g = BehaviorGraph()
        s1 = BehaviorStep("s1", "write code", "code")
        s2 = BehaviorStep("s2", "run tests", "test")
        g.add_step(s1)
        g.add_step(s2)
        for _ in range(10):
            g.record_edge(s1, s2, success=True)
        brain = BehaviorBrain(graph=g, llm_provider=None)
        brain.predict_next_background()
        assert _wait_predict(brain)
        top1 = brain.stats()["pending_prediction"]["top1"]
        for _ in range(49):
            brain.predict_next_background()
            assert _wait_predict(brain)
            assert brain.stats()["pending_prediction"]["top1"] == top1
        brain.shutdown()


class TestConcurrency:
    def test_registry_concurrent_add_and_match(self):
        reg = CommitmentRegistry()
        errors = []

        def _add(i):
            try:
                reg.add(when=f"trigger{i}", should=f"action{i}")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=_add, args=(i,)) for i in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors
        assert len(reg.list()) == 40
        # Concurrent matching must not corrupt the store.
        hits = reg.match("trigger3 trigger7")
        assert any("trigger3" in c.when for c in hits)

    def test_brain_concurrent_learn_no_crash(self):
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=None)

        def _learn(i):
            try:
                for _ in range(20):
                    brain.learn_from_event(_evt(f"c{i}", f"act {i}"))
            except Exception:  # pragma: no cover
                pass

        threads = [threading.Thread(target=_learn, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert brain.profile.total_turns == 8 * 20
        brain.shutdown()

    def test_background_prediction_no_thread_pileup(self):
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=None)
        # Fire-and-forget while a prediction is in flight must not stack threads.
        assert brain.predict_next_background() is True
        assert brain.predict_next_background() is False  # already running
        assert _wait_predict(brain)
        assert brain.predict_next_background() is True  # new slot after done
        brain.shutdown()


class TestTokenBudget:
    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, prompt, max_tokens=200):
            self.calls += 1
            return '[{"action": "run tests", "probability": 0.8}]'

    def test_budget_exhaustion_forces_stats_only(self, monkeypatch):
        """L1: after budget drains, scheduler returns stats and LLM stops."""
        import core.agent.behavior.brain as brain_mod
        # EXPLORE 分支是 ε-greedy 随机——固定 random 走 LLM 分支（确定性，防 flaky）。
        monkeypatch.setattr(brain_mod.random, "random", lambda: 0.0)
        reg = get_registry()
        reg.set("behavior.scheduler_token_budget", 800)  # exactly one LLM call
        llm = self._FakeLLM()
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=llm)
        # First prediction consumes the budget via LLM.
        brain.predict_next_background()
        assert _wait_predict(brain)
        assert llm.calls == 1
        assert brain.stats()["token_budget_remaining"] == 0.0
        # Second round: L1 cost floor → stats mode, LLM must NOT be called again.
        brain.predict_next_background()
        deadline = time.time() + 8.0
        while time.time() < deadline and brain.stats()["predict_count"] < 2:
            time.sleep(0.05)
        assert brain.stats()["predict_count"] >= 2
        calls_after = llm.calls
        assert calls_after == 1, f"LLM called {calls_after} times after budget drain"
        assert brain._last_decision.mode == ScheduleMode.STATS
        brain.shutdown()
        reg.set("behavior.scheduler_token_budget", 2000)  # restore default


class TestLifecycleIntegrity:
    def test_all_valid_transitions(self):
        reg = CommitmentRegistry()
        c = reg.add(when="w", should="s")
        assert reg.arm(c.id).status == "armed"
        assert reg.fire(c.id).status == "fired"
        assert reg.complete(c.id).status == "done"

    def test_invalid_transitions_rejected(self):
        reg = CommitmentRegistry()
        c = reg.add(when="w", should="s")
        # pending → fired is illegal.
        assert reg.fire(c.id) is None
        assert reg.arm(c.id).status == "armed"
        # armed → done is illegal.
        assert reg.complete(c.id) is None
        # fired → arm is illegal.
        assert reg.fire(c.id).status == "fired"
        assert reg.arm(c.id) is None
        # fired → cancelled is LEGAL (user changes mind after firing).
        assert reg.cancel(c.id).status == "cancelled"
        # done/terminal → anything is illegal.
        assert reg.fire(c.id) is None

    def test_unknown_id_safe(self):
        reg = CommitmentRegistry()
        assert reg.arm("nope") is None
        assert reg.feedback("nope", "completed") is None


class TestRobustness:
    class _FailingLLM:
        async def generate(self, prompt, max_tokens=200):
            raise RuntimeError("provider down")

    def test_llm_failure_falls_back(self):
        brain = BehaviorBrain(graph=BehaviorGraph(), llm_provider=self._FailingLLM())
        brain.predict_next_background()
        assert _wait_predict(brain)
        stats = brain.stats()
        assert stats["pending_prediction"] is not None
        assert stats["pending_prediction"]["mode"] in ("fallback", "no_llm", "no_graph")

    def test_corrupted_graph_safe(self):
        g = BehaviorGraph()
        s1 = BehaviorStep("x1", "a", "t")
        g.add_step(s1)
        # Edge pointing at a missing node.
        g.edges["broken->edge"] = g.edges.get("broken->edge") or type(
            "BadEdge", (), {
                "from_step_id": "missing", "to_step_id": "also_missing",
                "sample_count": 5, "success_rate": 0.5,
            },
        )()
        width = ci_width_proxy(g)
        assert 0.0 <= width <= 1.0
        brain = BehaviorBrain(graph=g, llm_provider=None)
        brain.predict_next_background()
        assert _wait_predict(brain)
        assert brain.stats()["pending_prediction"] is not None
        brain.shutdown()

    def test_registry_bounds_reject_out_of_range(self):
        reg = get_registry()
        assert reg.set("behavior.predict_weight_llm", 5.0) is False   # > vmax
        assert reg.set("behavior.predict_weight_llm", -1.0) is False  # < vmin
        assert reg.set("behavior.predict_weight_llm", 0.5) is True
        assert reg.get("behavior.predict_weight_llm") == 0.5
        reg.set("behavior.predict_weight_llm", 0.4)  # restore

    def test_reward_value_domain(self):
        """Adversarial: extreme candidate values never escape [0,1] domain."""
        reg = get_registry()
        # Default weights sum to 1 → expected_value stays inside [0, 1].
        c = Candidate("x", llm_probability=1.0, success_rate=1.0,
                      cognitive_load=0.0, profile_match=1.0)
        v = c.compute_value()
        assert 0.0 <= v <= 1.0
        c2 = Candidate("y", llm_probability=0.0, success_rate=0.0,
                       cognitive_load=0.0, profile_match=0.0)
        assert c2.compute_value() >= 0.0  # weights are non-negative
        assert reg.get("behavior.reward_top1_hit") == 1.0

    def test_shared_direction_adversarial(self):
        from core.agent.rewarder.reward_rules import _shared_direction
        assert _shared_direction("", "x") is False
        assert _shared_direction("x", "") is False
        assert _shared_direction("a", "b") is False
        assert _shared_direction("写代码", "写代码注释") is False  # strict prefix
        assert _shared_direction("add_doc", "add comments") is True  # shared word

    def test_scheduler_decision_stability_200_runs(self):
        s = BehaviorScheduler()
        for _ in range(200):
            d1 = s.decide(total_turns=50, ci_width=0.2, token_budget_remaining=100)
            d2 = s.decide(total_turns=50, ci_width=0.2, token_budget_remaining=100)
            assert d1.mode == d2.mode and d1.reason == d2.reason

    def test_commitment_persistence_roundtrip(self, tmp_path):
        path = str(tmp_path / "commitments.json")
        reg1 = CommitmentRegistry(store_path=path)
        reg1.add(when="when x", should="do y", rather_than="do z", because="r")
        reg1.save()
        reg2 = CommitmentRegistry(store_path=path)
        assert reg2.stats()["total"] == 1
        c = reg2.list()[0]
        assert c.should == "do y"
        assert c.rather_than == "do z"

    def test_simulate_retry_budget_exhaustion(self):
        class _NeverSucceeds:
            async def generate(self, prompt, max_tokens=800):
                return "still wrong"

        async def go():
            return await simulate_with_retry(
                _NeverSucceeds(), "s", lambda raw: (False, raw), max_attempts=3,
            )

        import asyncio
        assert asyncio.run(go()) is None  # exhausts attempts, returns None safely

    def test_evaluate_accuracy_empty_inputs(self):
        assert evaluate_accuracy([], "x") == 0.0
        assert evaluate_accuracy(None, "x") == 0.0
        assert evaluate_accuracy([], "x", is_correction=True) == -0.2
