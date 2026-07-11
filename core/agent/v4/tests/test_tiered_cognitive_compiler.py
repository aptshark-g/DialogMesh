"""Tests for TieredCognitiveCompiler."""
import pytest
from core.agent.v4.tiered_cognitive_compiler import TieredCognitiveCompiler


class TestTieredCognitiveCompiler:
    def test_rule_only_without_llm(self):
        compiler = TieredCognitiveCompiler(llm_provider=None)
        result = compiler.process("check the status")
        assert result is not None
        assert hasattr(result, "slots")

    def test_rule_only_returns_parse_result(self):
        compiler = TieredCognitiveCompiler(llm_provider=None)
        result = compiler.process("restart service")
        assert result is not None
        assert result is not None

    def test_stats_are_collected(self):
        compiler = TieredCognitiveCompiler(llm_provider=None)
        compiler.process("test input")
        s = compiler.stats()
        assert "tiers" in s
        assert len(s["tiers"]) == 2
