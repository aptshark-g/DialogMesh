import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.global_workspace import GlobalWorkspace
from core.agent.association.models import TrackType, TrackResult

class TestGlobalWorkspace:
    def setup_method(self):
        self.gw = GlobalWorkspace()

    def test_select_dominant(self):
        tr = TrackResult(TrackType.TRACK_0, {"d": "x"}, 0.9)
        dom = self.gw.select_dominant([tr])
        assert dom.track == TrackType.TRACK_0

    def test_select_none_if_empty(self):
        dom = self.gw.select_dominant([])
        assert dom is None

    def test_repression_increases(self):
        algo = TrackResult(TrackType.TRACK_0, {"d": "a"}, 0.9)
        causal = TrackResult(TrackType.CAUSAL, {"d": "b"}, 0.9)
        dom1 = self.gw.select_dominant([causal, algo])
        dom2 = self.gw.select_dominant([causal, algo])
        assert self.gw.repression_count[TrackType.TRACK_0] > 0

    def test_get_status(self):
        status = self.gw.get_status()
        assert "algo" in status
        assert "causal" in status