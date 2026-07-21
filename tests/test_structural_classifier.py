"""Structural Classifier Tests — grammar-based, zero keywords."""

import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.agent.v4.classifier.structural_classifier import StructuralFeatures


class TestStructuralFeatures(unittest.TestCase):

    def test_empty(self):
        f = StructuralFeatures.extract("")
        self.assertEqual(f.word_count, 0)
        exp, conf = f.expectation_hint()
        self.assertEqual(exp, "UNKNOWN")

    def test_tool_imperative(self):
        f = StructuralFeatures.extract("scan 0x401000")
        self.assertTrue(f.has_imperative)
        self.assertGreaterEqual(f.entity_count, 1)
        exp, conf = f.expectation_hint()
        self.assertEqual(exp, "TOOL")

    def test_tool_with_address(self):
        f = StructuralFeatures.extract("modify memory at 0x7ff12345 and NOP the jump")
        self.assertGreaterEqual(f.entity_count, 1)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "TOOL")

    def test_advisor_question(self):
        f = StructuralFeatures.extract("这个函数为什么被优化掉了？")
        self.assertTrue(f.has_question_mark)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "ADVISOR")

    def test_advisor_how(self):
        f = StructuralFeatures.extract("怎么才能判断这个packer的类型")
        self.assertTrue(f.has_wh_word)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "ADVISOR")

    def test_companion_verbose(self):
        f = StructuralFeatures.extract("我是新手刚开始学逆向工程应该从哪里入手比较好呢")
        self.assertGreaterEqual(f.word_count, 5)
        exp, _ = f.expectation_hint()
        self.assertIn(exp, ["COMPANION", "ADVISOR"])

    def test_noise_repetition(self):
        f = StructuralFeatures.extract("那个 那个 东西 搞一下 搞一下")
        self.assertGreater(f.repetition_ratio, 0.3)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "UNKNOWN")

    def test_short_noise(self):
        f = StructuralFeatures.extract("ok")
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "UNKNOWN")

    def test_cross_language_english(self):
        f = StructuralFeatures.extract("how do I disassemble this binary")
        self.assertTrue(f.has_wh_word)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "ADVISOR")

    def test_cross_language_imperative(self):
        f = StructuralFeatures.extract("find all references to this function")
        self.assertTrue(f.has_imperative)
        exp, _ = f.expectation_hint()
        self.assertEqual(exp, "TOOL")

    def test_confidence_range(self):
        tests = ["scan", "why is this", "ok", "help me learn reverse engineering step by step", ""]
        for t in tests:
            _, conf = StructuralFeatures.extract(t).expectation_hint()
            self.assertGreaterEqual(conf, 0.0)
            self.assertLessEqual(conf, 1.0)

    def test_entity_hex_detection(self):
        f = StructuralFeatures.extract("patch 0x401000 to 0x90 0x90 0x90")
        self.assertGreaterEqual(f.entity_count, 4)

    def test_entity_number_detection(self):
        f = StructuralFeatures.extract("scan 4 bytes at offset 100")
        self.assertGreaterEqual(f.entity_count, 2)

    def test_no_entity_plain_text(self):
        f = StructuralFeatures.extract("hello world how are you")
        self.assertEqual(f.entity_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
