"""Tests for ParameterRegistry: defaults, get/set, parameter count."""
import pytest
from core.agent.compiler.parameter_registry import ParameterRegistry


class TestParameterRegistry:
    def setup_method(self):
        self.reg = ParameterRegistry()

    def test_defaults_loaded(self):
        assert self.reg.get("relation.min_confidence_edge") is not None
        assert self.reg.get("behavior.ttl_seconds") is not None
        assert self.reg.get("slow_path.event_threshold") is not None

    def test_get_float_defaults(self):
        assert self.reg.get("relation.min_confidence_edge") == 0.15
        assert isinstance(self.reg.get("relation.min_confidence_edge"), float)

    def test_get_int_defaults(self):
        assert self.reg.get("behavior.ttl_seconds") == 300
        assert self.reg.get("slow_path.event_threshold") == 5

    def test_get_bool_defaults(self):
        assert self.reg.get("execution.context_threshold_8k") is True

    def test_set_and_get(self):
        self.reg.set("relation.min_confidence_edge", 0.3)
        assert self.reg.get("relation.min_confidence_edge") == 0.3

    def test_get_nonexistent(self):
        assert self.reg.get("nonexistent.key") is None

    def test_slow_path_threshold(self):
        assert self.reg.get("slow_path.event_threshold") == 5
        assert self.reg.get("conversation.max_history_entries") == 10

    def test_all_returns_dict(self):
        params = self.reg.all()
        assert isinstance(params, dict)
        assert len(params) >= 20
        assert "relation.min_confidence_edge" in params

    def test_set_value_persists(self):
        self.reg.set("behavior.ttl_seconds", 600)
        assert self.reg.get("behavior.ttl_seconds") == 600
