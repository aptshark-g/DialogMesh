"""Tests for Executor Mapping."""
import pytest
from core.agent.v4.skill_layer.executor_map import resolve_executor

class TestExecutorMap:
    def test_default(self):
        result = resolve_executor("create_module", params={"name": "myapp"})
        assert "myapp" in result

    def test_shell(self):
        result = resolve_executor("create_module", executor="shell", params={"name": "src"})
        assert "mkdir" in result

    def test_unknown(self):
        assert resolve_executor("unknown_action") is None
