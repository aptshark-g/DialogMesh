"""Tests for JiebaRelationParser: Chinese entity and relation extraction."""
import pytest
from core.agent.tiered.jieba_parser import JiebaRelationParser


class TestJiebaRelationParser:
    def setup_method(self):
        self.parser = JiebaRelationParser()

    def test_chinese_relation_extraction(self):
        tuples = self.parser.extract("DomainSelector依赖于IntentParser来解析意图")
        assert len(tuples) >= 1
        rel = tuples[0]
        assert rel["subject"] == "DomainSelector"
        assert rel["predicate"] == "depends_on"
        assert "IntentParser" in rel["object"]

    def test_calls_relation(self):
        tuples = self.parser.extract("ContextCompiler调用DomainSelector获取域")
        rels = [t for t in tuples if t["predicate"] == "calls"]
        assert len(rels) >= 1

    def test_definition_detection(self):
        tuples = self.parser.extract("ContextCompiler是负责上下文编译的核心模块")
        defs = [t for t in tuples if t["type"] == "definition"]
        assert len(defs) >= 1

    def test_noise_rejection(self):
        """虚词不应被提取为实体"""
        tuples = self.parser.extract("你觉得怎么样这个好像还可以")
        entities = set()
        for t in tuples:
            entities.add(t["subject"])
            entities.add(t["object"])
        # 不应包含虚词
        assert "你觉得" not in entities
        assert "怎么样" not in entities

    def test_no_entities_no_tuples(self):
        tuples = self.parser.extract("嗯好的知道了")
        assert len(tuples) == 0

    def test_mixed_cn_en(self):
        tuples = self.parser.extract("BudgetAllocator调用DomainSelector获取资源")
        # Jieba may or may not extract in mixed CN-EN; at minimum, no crash
        assert isinstance(tuples, list)
