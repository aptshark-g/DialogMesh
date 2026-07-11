"""Tests for TieredContextCompiler."""
import pytest
from core.agent.v4.tiered_context_compiler import TieredContextCompiler


class TestTieredContextCompiler:
    def test_rule_compile_basic(self):
        compiler = TieredContextCompiler(llm_provider=None)
        result = compiler.compile("list all modules")
        assert result is not None

    def test_fallback_no_llm(self):
        compiler = TieredContextCompiler(llm_provider=None)
        result = compiler.compile("analyze the dependencies")
        assert result is not None

    def test_stats_are_collected(self):
        compiler = TieredContextCompiler(llm_provider=None)
        compiler.compile("test query")
        s = compiler.stats()
        assert "tiers" in s
        assert len(s["tiers"]) == 3
