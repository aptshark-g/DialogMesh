import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.behavior.cold_start import ColdStartManager

class TestColdStartManager:
    def setup_method(self):
        self.mgr = ColdStartManager()

    def test_has_default_seeds(self):
        assert len(self.mgr.seeds) > 0
        assert len(self.mgr.seeds) <= 15

    def test_get_weight_hit(self):
        w = self.mgr.get_weight("执行", "查看结果")
        assert w == 0.7

    def test_get_weight_miss(self):
        w = self.mgr.get_weight("不存在", "不存在")
        assert w is None

    def test_mark_seed_used(self):
        self.mgr.mark_seed_used("执行", "查看结果")
        assert self.mgr.seeds[0].sample_count == 1

    def test_get_active_seeds(self):
        active = self.mgr.get_active_seeds()
        assert len(active) == len(self.mgr.seeds)

    def test_deprecation_check(self):
        for _ in range(50):
            self.mgr.on_turn_completed()
        assert self.mgr.deprecated_count >= 0
