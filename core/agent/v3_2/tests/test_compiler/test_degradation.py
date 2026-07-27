"""Tests for degradation manager"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.compiler.degradation_manager import DegradationManager


class TestDegradationManager:
    def setup_method(self):
        self.mgr = DegradationManager()

    def test_initial_mode(self):
        assert self.mgr.should_use_llm()

    def test_reset_after_success(self):
        self.mgr.on_failure()
        self.mgr.on_failure()
        self.mgr.on_failure()
        assert not self.mgr.should_use_llm()
        self.mgr.on_success()
        assert self.mgr.should_use_llm()

    def test_three_failures(self):
        self.mgr.on_failure()
        self.mgr.on_failure()
        self.mgr.on_failure()
        self.mgr.on_failure()
        assert not self.mgr.should_use_llm()
        assert self.mgr.mode == DegradationManager.MODE_RULE

    def test_force_rule_mode(self):
        self.mgr.force_rule_mode()
        assert not self.mgr.should_use_llm()

    def test_get_status(self):
        status = self.mgr.get_status()
        assert "mode" in status

    def test_rule_parse_empty(self):
        slots = DegradationManager.rule_parse("test", None)
        assert isinstance(slots, dict)

    def test_custom_threshold(self):
        mgr = DegradationManager(threshold=5)
        for _ in range(4):
            mgr.on_failure()
        assert mgr.should_use_llm()
        mgr.on_failure()
        assert not mgr.should_use_llm()
