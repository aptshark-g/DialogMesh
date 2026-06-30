# -*- coding: utf-8 -*-
"""
core/agent/tests/test_intent_rule_registry.py
─────────────────────────────────────────────
Unit tests for IntentRuleRegistry (Architecture Gap #3).

Coverage:
  - Basic registration + lookup
  - Conflict detection (same domain, overlapping patterns)
  - No conflict across different domains
  - Fuzz overlap detection
  - Explicit conflicts_with declarations
  - Priority ordering
  - Global check_rule_conflicts
  - Edge cases (invalid rule, empty registry)
"""

from __future__ import annotations

import re
import unittest

from core.agent.intent_rule_registry import (
    IntentRuleRegistry,
    ConflictReport,
    IntentRule,
    check_rule_conflicts,
)


class TestIntentRuleRegistry(unittest.TestCase):
    """IntentRuleRegistry 核心功能测试。"""

    def setUp(self):
        self.registry = IntentRuleRegistry()
        self.registry.clear()

    def _make_rule(self, name, category="tool", patterns=None, domain="memory", priority=100, conflicts_with=None):
        compiled = [re.compile(p) if isinstance(p, str) else p for p in (patterns or [f"rule_{name}"])]
        return IntentRule(
            name=name,
            category=category,
            patterns=compiled,
            required_entities=[],
            optional_entities=[],
            min_confidence=0.6,
            priority=priority,
            is_compound=False,
            domain=domain,
            conflicts_with=conflicts_with or [],
        )

    def test_register_single(self):
        r = self._make_rule("scan")
        conflicts = self.registry.register(r)
        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(self.registry.list_rules()), 1)

    def test_lookup_by_name(self):
        r = self._make_rule("read")
        self.registry.register(r)
        found = self.registry.get_rule("read")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "read")

    def test_lookup_not_found(self):
        self.assertIsNone(self.registry.get_rule("nonexistent"))

    def test_conflict_same_domain_overlap(self):
        r1 = self._make_rule("scan", patterns=["scan memory"], domain="memory")
        r2 = self._make_rule("find", patterns=["find memory"], domain="memory")
        self.registry.register(r1)
        conflicts = self.registry.register(r2)
        # "scan memory" and "find memory" don't overlap (different first word)
        self.assertEqual(len(conflicts), 0)

        # Now register a truly overlapping rule
        r3 = self._make_rule("search", patterns=["scan memory"], domain="memory")
        conflicts = self.registry.register(r3)
        self.assertEqual(len(conflicts), 1)
        # _check_pair reports rule_a=existing, rule_b=new (order depends on call site)
        self.assertIn(conflicts[0].rule_a, ("scan", "search"))
        self.assertIn(conflicts[0].rule_b, ("scan", "search"))

    def test_no_conflict_different_domain(self):
        r1 = self._make_rule("scan", patterns=["scan memory"], domain="memory")
        r2 = self._make_rule("scan", patterns=["scan memory"], domain="file")
        self.registry.register(r1)
        conflicts = self.registry.register(r2)
        # Different domain should not trigger conflict
        self.assertEqual(len(conflicts), 0)

    def test_explicit_conflicts_with(self):
        r1 = self._make_rule("scan", conflicts_with=["read"])
        r2 = self._make_rule("read")
        self.registry.register(r1)
        conflicts = self.registry.register(r2)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].overlap_type, "explicit")

    def test_priority_order(self):
        r1 = self._make_rule("low", priority=10)
        r2 = self._make_rule("high", priority=200)
        self.registry.register(r1)
        self.registry.register(r2)
        names = [r.name for r in self.registry.list_rules()]
        self.assertEqual(names.index("high"), 0)
        self.assertEqual(names.index("low"), 1)

    def test_fuzz_overlap_no_crash(self):
        r1 = self._make_rule("a", patterns=["test_pattern_123"])
        r2 = self._make_rule("b", patterns=["test_pattern_456"])
        self.registry.register(r1)
        self.registry.register(r2)
        # Both registered, no crash, no false overlap
        self.assertEqual(len(self.registry.list_rules()), 2)

    def test_register_invalid_no_name(self):
        r = IntentRule(
            name="",
            category="tool",
            patterns=[re.compile("p")],
            required_entities=[],
            optional_entities=[],
            min_confidence=0.6,
            priority=1,
            is_compound=False,
        )
        with self.assertRaises(ValueError):
            self.registry.register(r)

    def test_register_invalid_empty_patterns(self):
        r = IntentRule(
            name="empty",
            category="tool",
            patterns=[],
            required_entities=[],
            optional_entities=[],
            min_confidence=0.6,
            priority=1,
            is_compound=False,
        )
        with self.assertRaises(ValueError):
            self.registry.register(r)

    def test_conflict_report_str(self):
        cr = ConflictReport(
            rule_a="a",
            rule_b="b",
            domain="test",
            overlap_type="overlap",
            detail="both match 'test'",
            severity="warning",
        )
        s = str(cr)
        self.assertIn("a", s)
        self.assertIn("b", s)
        self.assertIn("overlap", s)

    def test_check_rule_conflicts_global(self):
        r1 = self._make_rule("scan", patterns=["find value"], domain="memory")
        r2 = self._make_rule("find", patterns=["find value"], domain="memory")
        self.registry.register(r1)
        self.registry.register(r2)
        all_conflicts = check_rule_conflicts(registry=self.registry)
        self.assertEqual(len(all_conflicts), 1)

    def test_remove(self):
        r = self._make_rule("tmp")
        self.registry.register(r)
        self.assertEqual(len(self.registry.list_rules()), 1)
        self.registry.remove("tmp")
        self.assertEqual(len(self.registry.list_rules()), 0)
        self.assertIsNone(self.registry.get_rule("tmp"))

    def test_domain_isolation_strict(self):
        r1 = self._make_rule("read_mem", patterns=["read memory"], domain="memory")
        r2 = self._make_rule("read_disk", patterns=["read memory"], domain="disk")
        r3 = self._make_rule("read_mem2", patterns=["read memory"], domain="memory")
        self.registry.register(r1)
        self.registry.register(r2)
        # r1 and r3 share domain=memory, same pattern → conflict
        conflicts = self.registry.register(r3)
        self.assertEqual(len(conflicts), 1)
        self.assertIn(conflicts[0].rule_a, ("read_mem", "read_mem2"))
        self.assertIn(conflicts[0].rule_b, ("read_mem", "read_mem2"))

    def test_duplicate_registration(self):
        r = self._make_rule("dup")
        self.registry.register(r)
        # Re-registering same name updates
        self.registry.register(r)
        self.assertEqual(len(self.registry.list_rules()), 1)

    def test_conflicts_with_nonexistent(self):
        r = self._make_rule("lonely", conflicts_with=["ghost"])
        conflicts = self.registry.register(r)
        # ghost doesn't exist, so no conflict raised
        self.assertEqual(len(conflicts), 0)


if __name__ == "__main__":
    unittest.main()
