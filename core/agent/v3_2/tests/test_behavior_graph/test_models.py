import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.behavior.models import BehaviorStep, BehaviorEdge, ColdStartSeed, GraphStatistics

class TestBehaviorStep:
    def test_creation(self):
        s = BehaviorStep("s1", "run", "TOOL_EXEC")
        assert s.step_id == "s1"
        assert s.action_summary == "run"

    def test_edge_key(self):
        s = BehaviorStep("s1", "run", "TOOL_EXEC")
        assert s.edge_key == "TOOL_EXEC:run"

    def test_default_result(self):
        s = BehaviorStep("s1", "run", "TOOL_EXEC")
        assert s.result == ""

class TestBehaviorEdge:
    def test_creation(self):
        e = BehaviorEdge("e1", "s1", "s2")
        assert e.edge_key == "s1->s2"
        assert e.weight == 0.5

    def test_success_rate_zero(self):
        e = BehaviorEdge("e1", "s1", "s2")
        assert e.success_rate == 0.5

    def test_record_observation(self):
        e = BehaviorEdge("e1", "s1", "s2")
        e.record_observation(True)
        assert e.success_count == 1
        assert e.success_rate == 1.0

    def test_record_failure(self):
        e = BehaviorEdge("e1", "s1", "s2")
        e.record_observation(False)
        assert e.failure_count == 1

    def test_record_correction(self):
        e = BehaviorEdge("e1", "s1", "s2")
        e.record_observation(True, correction=True)
        assert e.correction_count == 1

    def test_instability_ratio(self):
        e = BehaviorEdge("e1", "s1", "s2")
        e.record_observation(True)
        assert e.instability_ratio == 0.0
        e.record_observation(True, correction=True)
        assert e.instability_ratio == 0.5

class TestColdStartSeed:
    def test_usable(self):
        s = ColdStartSeed("run","check","TOOL_EXEC","LOG_CHECK",0.7)
        assert s.is_usable()

    def test_deprecated(self):
        s = ColdStartSeed("run","check","TOOL_EXEC","LOG_CHECK",0.7,is_deprecated=True)
        assert not s.is_usable()

    def test_edge_key(self):
        s = ColdStartSeed("run","check","TOOL_EXEC","LOG_CHECK",0.7)
        assert s.edge_key == "seed:run->check"

class TestGraphStatistics:
    def test_defaults(self):
        gs = GraphStatistics()
        assert gs.node_count == 0.0 or gs.node_count == 0
        assert gs.edge_count == 0
