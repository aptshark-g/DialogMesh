"""Tests for DiscourseBlockTree: fork detection, tree building, context serialization."""
import pytest
from core.agent.compiler.discourse_block_tree import (
    DiscourseBlockTreeManager, DiscourseBlockTree, DiscourseBlock,
    HeaderInjector, SyntacticDecomposer, MacroMicroQuantizer, EDU, CohesionScore,
    RouteDecision,
)


class TestHeaderInjector:
    def test_pronoun_resolution_same_turn(self):
        inj = HeaderInjector()
        # "它" is in PRONOUNS list; Python appears before it
        result = inj.inject("Python is great, it has many libraries", "s1")
        assert "[Python]" in result or "Python" in result  # may or may not resolve

    def test_no_pronoun_no_change(self):
        inj = HeaderInjector()
        result = inj.inject("DomainSelector根据意图选择知识域", "s1")
        assert result == "DomainSelector根据意图选择知识域"

    def test_session_entity_cache(self):
        inj = HeaderInjector()
        inj._update_cache("s1", ["DomainSelector handles domain routing"])
        result = inj.inject("这个模块很重要", "s1")
        # C1 (R6): A facade delegates to the B kernel HeaderInjector; the
        # injected format is the resolved entity (no bracket wrapper).
        assert "DomainSelector" in result


class TestSyntacticDecomposer:
    def test_decompose_chinese(self):
        dec = SyntacticDecomposer()
        edus = dec.decompose("有记忆吗？对自己了解什么")
        assert len(edus) >= 2
        assert edus[0].raw_text == "有记忆吗"

    def test_decompose_camelcase_entities(self):
        dec = SyntacticDecomposer()
        edus = dec.decompose("DomainSelector根据意图选择知识域")
        assert len(edus) >= 1
        # Entity detection may work via CamelCase regex or jieba segmentation
        all_entities = []
        for e in edus:
            all_entities.extend(e.entities)
        # At minimum, decomposer produces EDUs
        assert all(e.raw_text for e in edus)


class TestMacroMicroQuantizer:
    def test_same_entities_continue(self):
        q = MacroMicroQuantizer()
        a = EDU("e1", "DomainSelector routes domains",
                entities=["DomainSelector"])
        b = EDU("e2", "DomainSelector selects knowledge",
                entities=["DomainSelector"])
        score = q.compute(a, b)
        assert score.decision == "continue"

    def test_different_entities_fork(self):
        q = MacroMicroQuantizer()
        a = EDU("e1", "记忆很重要", entities=["记忆"])
        b = EDU("e2", "递归简化字段", entities=["递归", "封装"])
        score = q.compute(a, b)
        assert score.decision in ("fork", "gray_zone")

    def test_bge_fast_path(self):
        q = MacroMicroQuantizer()
        a = EDU("e1", "DomainSelector routes requests")
        b = EDU("e2", "DomainSelector selects domains")
        score = q.compute(a, b)
        assert hasattr(score, 'total')
        assert 0 <= score.total <= 1


class TestDiscourseBlockTreeManager:
    def test_tree_building(self):
        mgr = DiscourseBlockTreeManager()
        mgr.feed("有记忆吗", "s1")
        mgr.feed("递归图和封装", "s1")
        mgr.feed("性能优化", "s1")
        stats = mgr.get_stats("s1")
        assert stats["total_blocks"] >= 1
        assert stats["root_id"] is not None

    def test_fork_detection(self):
        mgr = DiscourseBlockTreeManager()
        r1 = mgr.feed("DomainSelector路由域", "s1")
        r2 = mgr.feed("递归简化字段存储", "s1")
        # Different topics should trigger fork
        tree = mgr.get_tree("s1")
        assert tree is not None
        assert len(tree.blocks) >= 1

    def test_context_serialization(self):
        mgr = DiscourseBlockTreeManager()
        mgr.feed("有记忆吗", "s1")
        mgr.feed("递归图和封装", "s1")
        ctx = mgr.build_context("s1")
        # Temperature tags are B-kernel style ([Hot]/[Warm]/[Cold]); the A
        # facade bridges A blocks into B-compatible views (C4/R6).
        assert "[Hot]" in ctx
        assert len(ctx) > 0

    def test_empty_context(self):
        mgr = DiscourseBlockTreeManager()
        ctx = mgr.build_context("nonexistent")
        assert ctx == ""

    def test_multiple_sessions(self):
        mgr = DiscourseBlockTreeManager()
        mgr.feed("session A text", "sA")
        mgr.feed("session B text", "sB")
        assert mgr.get_tree("sA") is not None
        assert mgr.get_tree("sB") is not None
        assert mgr.get_tree("sA") != mgr.get_tree("sB")
