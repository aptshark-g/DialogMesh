"""Business Chain Pipeline Tests — Decider-gated, per-chain, end-to-end.

Tests each chain's trigger conditions independently, then full pipeline.
Generates report to tests/test_performance/chain_pipeline_report.jsonl
"""

import sys, json, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.v4.state.global_decider import GlobalDecider, Command, EventType, StateSnapshot
from core.agent.v4.state.trigger_conditions import TRIGGER_CONDITIONS


class TestTriggerConditions(unittest.TestCase):
    """Each chain's should_trigger predicate."""

    def setUp(self):
        self.d = GlobalDecider()

    def _tick(self, cmd_type):
        self.d.evolve(self.d.decide(Command(type=cmd_type)))

    def test_pcr_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["pcr"](self.d.state, self.d.event_log))

    def test_router_always_triggers(self):
        self._tick("pcr")
        self.assertTrue(TRIGGER_CONDITIONS["routing"](self.d.state, self.d.event_log))

    def test_intent_skipped_for_atomic(self):
        self._tick("pcr")
        self.d.evolve(self.d.decide(Command(type="routing", payload={"zone": "ATOMIC"})))
        self.assertFalse(TRIGGER_CONDITIONS["intent"](self.d.state, self.d.event_log))

    def test_intent_triggers_for_precision(self):
        self._tick("pcr")
        self.d.evolve(self.d.decide(Command(type="routing", payload={"zone": "PRECISION"})))
        self.assertTrue(TRIGGER_CONDITIONS["intent"](self.d.state, self.d.event_log))

    def test_planner_triggers_precision_abyss(self):
        for zone in ("PRECISION", "ABYSS"):
            d = GlobalDecider()
            d.evolve(d.decide(Command(type="routing", payload={"zone": zone})))
            self.assertTrue(TRIGGER_CONDITIONS["planning"](d.state, d.event_log), f"Should trigger for {zone}")

    def test_planner_skips_atomic_explore(self):
        for zone in ("ATOMIC", "EXPLORE", "PSYCHE", "MIXED"):
            d = GlobalDecider()
            d.evolve(d.decide(Command(type="routing", payload={"zone": zone})))
            self.assertFalse(TRIGGER_CONDITIONS["planning"](d.state, d.event_log), f"Should skip for {zone}")

    def test_context_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["context"](self.d.state, self.d.event_log))

    def test_llm_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["llm"](self.d.state, self.d.event_log))

    def test_profile_triggers_with_pcr(self):
        self._tick("pcr")
        self.assertTrue(TRIGGER_CONDITIONS["profile"](self.d.state, self.d.event_log))

    def test_profile_triggers_with_behavior_burst(self):
        for _ in range(3):
            self._tick("behavior")
        self.assertTrue(TRIGGER_CONDITIONS["profile"](self.d.state, self.d.event_log))

    def test_behavior_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["behavior"](self.d.state, self.d.event_log))

    def test_abc_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["abc"](self.d.state, self.d.event_log))

    def test_mind_always_triggers(self):
        self.assertTrue(TRIGGER_CONDITIONS["mind"](self.d.state, self.d.event_log))

    def test_meta_triggers_every_5_ticks(self):
        for i in range(5):
            self.assertFalse(TRIGGER_CONDITIONS["meta"](self.d.state, self.d.event_log), f"Tick {i+1}")
            self._tick("pcr")
        self.assertTrue(TRIGGER_CONDITIONS["meta"](self.d.state, self.d.event_log), "Tick 5 should trigger")

    def test_meta_triggers_on_behavior_surge(self):
        for _ in range(3):
            self._tick("behavior")
        self.assertTrue(TRIGGER_CONDITIONS["meta"](self.d.state, self.d.event_log))


class TestFullPipeline(unittest.TestCase):
    """Full pipeline: simulate on_event with all chains."""

    def setUp(self):
        self.d = GlobalDecider()

    def _run_pipeline(self, zone="MIXED") -> dict:
        """Simulate one full on_event tick."""
        chains_triggered = []
        chains_skipped = []

        cmd = Command(type="user_message")
        self.d.evolve(self.d.decide(cmd))
        chains_triggered.append("user_message")

        for chain in ["pcr", "routing", "intent", "planning", "context", "llm",
                       "profile", "behavior", "abc", "mind", "meta"]:
            should = TRIGGER_CONDITIONS[chain](self.d.state, self.d.event_log)
            if should:
                payload = {}
                if chain == "routing":
                    payload = {"zone": zone}
                elif chain == "intent":
                    payload = {"category": "ANALYZE"}
                elif chain == "pcr":
                    payload = {"expectation": "ADVISOR"}
                self.d.evolve(self.d.decide(Command(type=chain, payload=payload)))
                chains_triggered.append(chain)
            else:
                chains_skipped.append(chain)

        return {
            "tick": self.d.state.tick,
            "triggered": chains_triggered,
            "skipped": chains_skipped,
            "total_events": len(self.d.event_log),
            "state": self.d.state.__dict__,
        }

    def test_pipeline_atomic_zone(self):
        """ATOMIC zone: skip IntentParser and Planner."""
        result = self._run_pipeline("ATOMIC")
        self.assertIn("intent", result["skipped"], "ATOMIC should skip intent")
        self.assertIn("planning", result["skipped"], "ATOMIC should skip planner")

    def test_pipeline_precision_zone(self):
        """PRECISION zone: all chains active."""
        result = self._run_pipeline("PRECISION")
        self.assertIn("intent", result["triggered"])
        self.assertIn("planning", result["triggered"])

    def test_pipeline_explore_zone(self):
        """EXPLORE zone: skip planner."""
        result = self._run_pipeline("EXPLORE")
        self.assertIn("planning", result["skipped"])

    def test_pipeline_10_ticks(self):
        """10 consecutive pipeline runs — verify varying trigger patterns."""
        meta_triggered = 0
        for i in range(10):
            result = self._run_pipeline()
            if "meta" in result["triggered"]:
                meta_triggered += 1
            triggered_count = len(result["triggered"])
            self.assertGreater(triggered_count, 3, f"Run {i+1}: at least core chains should trigger")
        self.assertGreater(meta_triggered, 0, "Meta should trigger at least once in 10 runs")

    def test_pipeline_cost_control(self):
        """ATOMIC zone triggers only 6 chains (vs ~10 for PRECISION)."""
        atomic = self._run_pipeline("ATOMIC")
        d2 = GlobalDecider()
        self.d = d2  # fresh decider
        precision = self._run_pipeline("PRECISION")
        self.assertLess(len(atomic["triggered"]), len(precision["triggered"]),
                       "ATOMIC should trigger fewer chains than PRECISION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
