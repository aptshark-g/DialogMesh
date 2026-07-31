"""Tests for tree-sitter Python code extractor."""
import pytest
from core.agent.adapter.code.tree_sitter_extractor import PythonCodeExtractor


class TestPythonCodeExtractor:
    def setup_method(self):
        self.extractor = PythonCodeExtractor()

    def test_class_extraction(self):
        info = self.extractor.extract("""
class DomainSelector:
    def select(self, intent):
        return intent
""")
        assert len(info["classes"]) == 1
        assert info["classes"][0]["name"] == "DomainSelector"
        assert "select" in info["classes"][0]["methods"]

    def test_function_extraction(self):
        info = self.extractor.extract("""
def allocate_budget(tokens: int) -> int:
    return tokens // 2
""")
        assert len(info["functions"]) >= 1
        assert info["functions"][0]["name"] == "allocate_budget"

    def test_import_extraction(self):
        info = self.extractor.extract("""
from os import path
import json
""")
        assert "os" in info["imports"] or "json" in info["imports"]

    def test_call_extraction(self):
        info = self.extractor.extract("""
result = domain_selector.select(intent)
budget = BudgetAllocator().allocate(100)
""")
        assert len(info["calls"]) >= 1

    def test_empty_code(self):
        info = self.extractor.extract("")
        assert info["classes"] == []
        assert info["functions"] == []
        assert info["calls"] == []

    def test_extract_for_concept(self):
        result = self.extractor.extract_for_concept(
            "DomainSelector",
            ["class DomainSelector:\n    def route(self): pass"]
        )
        assert "DomainSelector" in result
        assert "route" in result
