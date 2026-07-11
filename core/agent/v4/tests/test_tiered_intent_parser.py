"""Tests for TieredIntentParser."""
import pytest
from core.agent.v4.tiered_intent_parser import TieredIntentParser
from core.agent.models import IntentCategory, IntentContext

class MockLLMProvider:
    def complete(self, prompt):
        return """{"intent": "question", "confidence": 0.92}"""


class TestTieredIntentParser:
    def test_rule_classify_simple_text(self):
        parser = TieredIntentParser(llm_provider=MockLLMProvider())
        ctx = IntentContext()
        ctx.expectation = None
        ctx.noise_level = 0.0
        ctx.complexity_level = 0.0
        cat, conf = parser.classify("help me scan memory", ctx)
        assert isinstance(cat, (str, type(None))) or hasattr(cat, "value")
        assert 0.0 <= conf <= 1.0

    def test_llm_fallback_when_rule_returns_unknown(self):
        parser = TieredIntentParser(llm_provider=MockLLMProvider())
        ctx = IntentContext()
        ctx.expectation = None
        ctx.noise_level = 0.0
        ctx.complexity_level = 0.0
        cat, conf = parser.classify("what is the meaning of life", ctx)
        assert conf >= 0.0

    def test_stats_are_collected(self):
        parser = TieredIntentParser(llm_provider=MockLLMProvider())
        ctx = IntentContext()
        ctx.expectation = None
        ctx.noise_level = 0.0
        ctx.complexity_level = 0.0
        parser.classify("test", ctx)
        s = parser.stats()
        assert "tiers" in s
        assert len(s["tiers"]) == 2

    def test_no_llm_falls_back_to_rule(self):
        parser = TieredIntentParser(llm_provider=None)
        ctx = IntentContext()
        ctx.expectation = None
        ctx.noise_level = 0.0
        ctx.complexity_level = 0.0
        cat, conf = parser.classify("disassemble at 0x4000", ctx)
        assert isinstance(cat, (str, type(None))) or hasattr(cat, "value")
        assert conf >= 0.0
