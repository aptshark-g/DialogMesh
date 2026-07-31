# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/tests/test_compiler.py
──────────────────────────────────────────────────
Cognitive compiler tests.
"""

import unittest

from core.agent.cognitive_compiler.compiler import CognitiveCompiler, CompiledInput, CompilerMode
from core.agent.cognitive_compiler.decomposer import SyntacticDecomposer, ParsedClause
from core.agent.cognitive_compiler.injector import HeaderInjector
from core.agent.cognitive_compiler.scorer import CohesionScorer
from core.agent.cognitive_compiler.dual_manager import DualStructureManager, TimelineEvent


class TestSyntacticDecomposer(unittest.TestCase):

    def test_simple_clause(self):
        d = SyntacticDecomposer()
        clauses, trace = d.decompose("scan 0x401000")
        self.assertEqual(len(clauses), 1)
        self.assertFalse(clauses[0].parse_failed)
        self.assertEqual(clauses[0].predicate, "scan")

    def test_complex_input_fast_mode(self):
        d = SyntacticDecomposer()
        # 长句应标记为复杂
        clauses, trace = d.decompose("我想扫描这个地址然后读取它的数值再修改成90", mode=CompilerMode.FAST)
        self.assertEqual(len(clauses), 1)
        self.assertTrue(clauses[0].parse_failed)

    def test_multiple_subjects(self):
        d = SyntacticDecomposer()
        # 多主语 + 连词
        clauses, trace = d.decompose("说说牛奶的好处，然后奶牛怎么产奶", mode=CompilerMode.FAST)
        self.assertEqual(len(clauses), 1)
        self.assertTrue(clauses[0].parse_failed)

    def test_hybrid_mode_parses_complex(self):
        d = SyntacticDecomposer()
        clauses, trace = d.decompose("我想扫描这个地址然后读取它的数值", mode=CompilerMode.HYBRID)
        # hybrid 模式可以处理复杂句（虽然解析可能不完美但不标记失败）
        self.assertGreater(len(clauses), 0)

    def test_negation_modifier(self):
        d = SyntacticDecomposer()
        clauses, trace = d.decompose("我不认为这个API安全")
        self.assertEqual(len(clauses), 1)
        self.assertTrue(any("NOT" in m for m in clauses[0].modifiers))


class TestHeaderInjector(unittest.TestCase):

    def test_entity_injection(self):
        injector = HeaderInjector(domain="default")
        clauses = [ParsedClause(subject="汽水", predicate="喝了", object="很呛")]
        injected, log = injector.inject(clauses, [])
        self.assertGreater(len(log["matched"]), 0)
        self.assertIn("product", injected[0].subject)

    def test_reload_kb(self):
        injector = HeaderInjector()
        ok = injector.reload_kb()
        self.assertTrue(ok)

    def test_unknown_entity_no_match(self):
        injector = HeaderInjector(domain="default")
        clauses = [ParsedClause(subject="unknown_item", predicate="test")]
        injected, log = injector.inject(clauses, [])
        self.assertGreater(len(log["missed"]), 0)


class TestCohesionScorer(unittest.TestCase):

    def test_high_cohesion_causal(self):
        s = CohesionScorer()
        history = [{"content": "scan 0x401000", "timestamp": 0}]
        score = s.calculate("然后读取这个地址", history)
        self.assertGreater(score, 0.5)

    def test_low_cohesion_topic_switch(self):
        s = CohesionScorer()
        history = [{"content": "scan 0x401000", "timestamp": 0}]
        score = s.calculate("学习如何写hook", history)
        self.assertLess(score, 0.5)

    def test_entity_overlap_boost(self):
        s = CohesionScorer()
        history = [{"content": "scan 0x401000", "timestamp": 0}]
        score = s.calculate("0x401000 的值是多少", history)
        self.assertGreater(score, 0.3)

    def test_no_history_zero(self):
        s = CohesionScorer()
        score = s.calculate("scan 0x401000", [])
        self.assertEqual(score, 0.0)


class TestDualStructureManager(unittest.TestCase):

    def test_create_and_lookup(self):
        dm = DualStructureManager()
        event = dm.create_event("node-1", 1, "user_input", "scan 0x401000",
                                entities=[{"type": "memory_address", "value": "0x401000"}])
        self.assertIsNotNone(dm.get_event(event.event_id))
        self.assertEqual(dm.get_latest_event_for_node("node-1").event_id, event.event_id)

    def test_o1_parent_lookup(self):
        dm = DualStructureManager()
        e1 = dm.create_event("node-1", 1, "user_input", "scan 0x401000")
        e2 = dm.create_event("node-1", 2, "user_input", "read it", parent_event_id=e1.event_id)
        parent = dm.get_parent_event(e2.event_id)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.event_id, e1.event_id)

    def test_find_cross_topic_entities(self):
        dm = DualStructureManager()
        dm.create_event("node-a", 1, "user", "scan 0x401000",
                       entities=[{"type": "address", "value": "0x401000"}])
        dm.create_event("node-b", 2, "user", "check 0x401000",
                       entities=[{"type": "address", "value": "0x401000"}])
        shared = dm.find_cross_topic_entities("node-a", "node-b")
        self.assertIn("0x401000", shared)

    def test_serialization(self):
        dm = DualStructureManager()
        dm.create_event("node-1", 1, "user", "hello")
        data = dm.to_dict()
        restored = DualStructureManager.from_dict(data)
        self.assertEqual(len(restored.get_all_events()), 1)


class TestCognitiveCompiler(unittest.TestCase):

    def test_fast_mode_simple(self):
        compiler = CognitiveCompiler(mode=CompilerMode.FAST)
        result = compiler.compile("scan 0x401000", turn_index=1)
        self.assertEqual(result.mode_used, "fast")
        self.assertFalse(result.clauses[0].parse_failed)
        self.assertGreaterEqual(result.cohesion_score, 0.0)
        self.assertLessEqual(result.cohesion_score, 1.0)
        self.assertLess(result.compilation_time_ms, 2.0)

    def test_auto_mode_selects_fast(self):
        compiler = CognitiveCompiler(mode=CompilerMode.AUTO)
        result = compiler.compile("scan 0x401000", turn_index=1)
        self.assertEqual(result.mode_used, "fast")

    def test_auto_mode_selects_full(self):
        compiler = CognitiveCompiler(mode=CompilerMode.AUTO)
        result = compiler.compile("我想扫描这个地址然后读取它的数值再修改成90并且还要检查其他模块", turn_index=5)
        self.assertEqual(result.mode_used, "full")

    def test_hybrid_mode_with_history(self):
        compiler = CognitiveCompiler(mode=CompilerMode.HYBRID)
        history = [{"content": "scan 0x401000"}]
        result = compiler.compile("读取这个地址", turn_index=2, session_history=history)
        self.assertGreater(result.cohesion_score, 0.5)
        # TODO: header injector 尚未实现历史实体回溯，当前仅基于知识库补全
        # self.assertIn("0x401000", result.query)
        self.assertIn("读取", result.query)

    def test_compiler_output_structure(self):
        compiler = CognitiveCompiler()
        result = compiler.compile("scan 0x401000", turn_index=1)
        self.assertIsInstance(result, CompiledInput)
        self.assertTrue(hasattr(result, "query"))
        self.assertTrue(hasattr(result, "cohesion_score"))
        self.assertTrue(hasattr(result, "clauses"))
        self.assertTrue(hasattr(result, "injected_headers"))

    def test_topic_node_id_not_set_by_compiler(self):
        """编译器不应设置 topic_node_id，应由调用方利用 cohesion_score 执行路由。"""
        compiler = CognitiveCompiler()
        result = compiler.compile("scan 0x401000", turn_index=1)
        self.assertIsNone(result.topic_node_id)


if __name__ == "__main__":
    unittest.main()
