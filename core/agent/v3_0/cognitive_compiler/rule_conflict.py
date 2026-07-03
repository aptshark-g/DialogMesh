# -*- coding: utf-8 -*-
from __future__ import annotations
import itertools
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class RuleConflictDetector:
    def __init__(self):
        self._rules: List[Tuple[str, str, float]] = []

    def register_rule(self, pattern: str, category: str, confidence: float) -> None:
        self._rules.append((pattern, category, confidence))

    def register_rules_from_parser(self, parser: Any) -> None:
        for rule in getattr(parser, "_rules", []):
            if len(rule) >= 3:
                self._rules.append((str(rule[0]), str(rule[1]), float(rule[2])))

    def check_overlaps(self) -> List[Dict[str, Any]]:
        conflicts = []
        for (p1, c1, _), (p2, c2, _) in itertools.combinations(self._rules, 2):
            if c1 == c2:
                continue
            overlap_score = self._estimate_overlap(p1, p2)
            if overlap_score > 0.3:
                conflicts.append({"pattern_a": p1[:50], "category_a": c1, "pattern_b": p2[:50], "category_b": c2, "overlap_score": round(overlap_score, 3), "message": f"Patterns for {c1} and {c2} may overlap (score={overlap_score:.2f})"})
        return conflicts

    def _estimate_overlap(self, p1: str, p2: str) -> float:
        try:
            r1 = re.compile(p1, re.IGNORECASE)
            r2 = re.compile(p2, re.IGNORECASE)
        except re.error:
            return 0.0
        test_inputs = ["scan this memory", "read the value", "write to address", "how do I hack", "help me please", "set config value", "exit now", "analyze this code", "scan memory at 0x004000", "read value at 0x100"]
        matches_both = sum(1 for t in test_inputs if r1.search(t) and r2.search(t))
        matches_either = sum(1 for t in test_inputs if r1.search(t) or r2.search(t))
        return matches_both / max(1, matches_either)

    def generate_report(self) -> Dict[str, Any]:
        conflicts = self.check_overlaps()
        total = len(self._rules)
        return {"total_rules": total, "conflict_count": len(conflicts), "conflicts": conflicts, "has_conflicts": len(conflicts) > 0}

__all__ = ["RuleConflictDetector"]
