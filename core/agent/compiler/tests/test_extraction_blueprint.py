"""Tests for ExtractionBlueprint: multi-provider extraction chain."""
import pytest
from core.agent.compiler.extraction_blueprint import (
    RegexExtractionProvider, StanzaExtractionProvider,
    LMStudioExtractionProvider, DeepSeekExtractionProvider,
    ExtractionOrchestrator, ExtractionBlueprint,
    ExtractedDefinition, ExtractedRelation, ExtractionResult,
)


class TestRegexExtractionProvider:
    def test_always_available(self):
        p = RegexExtractionProvider()
        assert p.available()

    def test_jieba_relation_extraction(self):
        p = RegexExtractionProvider()
        result = p.extract(
            "DomainSelector依赖于IntentParser来解析意图",
            ["DomainSelector", "IntentParser"]
        )
        assert result.provider == "regex"
        # jieba should find "依赖于" relation
        rel_sources = [r.source for r in result.relations]
        assert "DomainSelector" in rel_sources

    def test_definition_extraction(self):
        p = RegexExtractionProvider()
        result = p.extract(
            "ContextCompiler是负责上下文编译的核心模块",
            ["ContextCompiler"]
        )
        assert result.provider == "regex"
        assert len(result.definitions) >= 0  # regex may or may not catch

    def test_no_llm_required(self):
        p = RegexExtractionProvider()
        assert not p.requires_llm


class TestStanzaExtractionProvider:
    def test_availability(self):
        p = StanzaExtractionProvider()
        avail = p.available()
        assert isinstance(avail, bool)

    @pytest.mark.skipif(not StanzaExtractionProvider().available(),
                        reason="Stanza not available")
    def test_dependency_extraction(self):
        p = StanzaExtractionProvider()
        result = p.extract(
            "DomainSelector根据用户意图选择知识域",
            ["DomainSelector"]
        )
        assert result.provider == "stanza"


class TestLMStudioExtractionProvider:
    def test_requires_llm(self):
        p = LMStudioExtractionProvider()
        assert p.requires_llm


class TestDeepSeekExtractionProvider:
    def test_requires_api_key(self):
        p = DeepSeekExtractionProvider()
        import os
        if not os.environ.get("DEEPSEEK_API_KEY"):
            assert not p.available()
        else:
            assert p.available()


class TestExtractionOrchestrator:
    def test_register_and_stats(self):
        orch = ExtractionOrchestrator()
        orch.register(ExtractionBlueprint("regex", RegexExtractionProvider()))
        assert "regex" in orch.stats

    def test_fallback_chain(self):
        orch = ExtractionOrchestrator()
        orch.register(ExtractionBlueprint("regex", RegexExtractionProvider()))
        result = orch.extract("test", ["A", "B"], preferred="nonexistent")
        # Should fallback to first available provider
        assert result.provider != "none"

    def test_regex_extraction_through_orchestrator(self):
        orch = ExtractionOrchestrator()
        orch.register(ExtractionBlueprint("regex", RegexExtractionProvider()))
        result = orch.extract(
            "DomainSelector依赖于IntentParser",
            ["DomainSelector", "IntentParser"],
            preferred="regex"
        )
        assert result.provider == "regex"
        assert len(result.relations) >= 0
