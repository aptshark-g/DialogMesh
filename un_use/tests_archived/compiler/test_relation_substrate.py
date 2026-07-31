"""Tests for RelationSubstrate: build_from_extractions, typed edges."""
import pytest
from core.agent.compiler.relation_substrate import (
    RelationSubstrate, RelationEdge, Evidence
)
from core.agent.tiered.jieba_parser import JiebaRelationParser


class TestRelationSubstrateExtraction:
    def test_build_from_extractions_dict(self):
        rs = RelationSubstrate()
        extractions = [
            {"subject": "DomainSelector", "predicate": "depends_on",
             "object": "IntentParser", "confidence": 0.7},
        ]
        count = rs.build_from_extractions(extractions)
        assert count == 1
        assert rs.stats["total"] == 1
        assert rs.stats["kinds"]["structural"] == 1
        assert rs.stats["strengths"]["dependency"] == 1

    def test_build_from_jieba_extraction(self):
        rs = RelationSubstrate()
        jrp = JiebaRelationParser()
        extractions = jrp.extract("DomainSelector依赖于IntentParser")
        count = rs.build_from_extractions(extractions)
        assert count >= 1

    def test_multiple_extractions(self):
        rs = RelationSubstrate()
        extractions = [
            {"subject": "A", "predicate": "depends_on", "object": "B", "confidence": 0.7},
            {"subject": "B", "predicate": "calls", "object": "C", "confidence": 0.6},
        ]
        count = rs.build_from_extractions(extractions)
        assert count == 2
        assert rs.stats["total"] == 2

    def test_query_by_source(self):
        rs = RelationSubstrate()
        rs.build_from_extractions([
            {"subject": "DomainSelector", "predicate": "depends_on",
             "object": "IntentParser", "confidence": 0.7},
        ])
        results = rs.query(source="DomainSelector")
        assert len(results) >= 1
        assert results[0].target == "IntentParser"

    def test_relation_has_evidence(self):
        rs = RelationSubstrate()
        extractions = [
            {"subject": "A", "predicate": "depends_on", "object": "B", "confidence": 0.7},
        ]
        rs.build_from_extractions(extractions)
        edges = rs.query(source="A")
        assert len(edges) >= 1
        assert len(edges[0].evidence) >= 1
        assert edges[0].evidence[0].source == "extraction"
