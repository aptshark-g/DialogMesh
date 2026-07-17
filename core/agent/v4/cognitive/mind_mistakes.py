"""MistakeMemory — learns which patterns lead to failure.

Extracts from MetaConsumer analysis: consecutive rejects, low confidence,
overheat patterns. Stores as avoidance rules for future turns.

Feeds back: adjusts ReasoningPolicy to avoid known failure modes.
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
from typing import Dict, List


class MistakeMemory:
    """Cross-session mistake pattern learning.

    Each mistake pattern (consecutive_rejects, no_evidence, overheat)
    is tracked with context. When the same context triggers a pattern
    3+ times, it's stored as an avoidance rule.
    """

    def __init__(self):
        self._patterns: Dict[str, dict] = {}  # pattern_id → {count, last_seen, context}
        self._avoidance_rules: Dict[str, List[str]] = {}  # context_key → [warnings]

    def learn_from_warnings(self, warnings: List[str], suggestions: List[str], context: dict = None) -> int:
        """Learn from MetaConsumer warnings + policy suggestions.

        warnings: ["consecutive_rejects", "no_observe_evidence"]
        suggestions: ["switch perspective", "expand relations"]
        context: current StrategyContext or similar
        """
        if not warnings:
            return 0

        context_key = self._context_to_key(context or {})
        learned = 0

        for warning in warnings:
            pid = f"{context_key}:{warning}"
            entry = self._patterns.get(pid, {'count': 0, 'last_seen': 0, 'warnings': []})
            entry['count'] += 1
            entry['last_seen'] = time.time()
            entry['warnings'] = list(set(entry.get('warnings', []) + [warning]))

            # After 3 occurrences, store as avoidance rule
            if entry['count'] >= 3:
                self._avoidance_rules.setdefault(context_key, [])
                for sg in suggestions:
                    if sg not in self._avoidance_rules[context_key]:
                        self._avoidance_rules[context_key].append(sg)
                learned += 1

            self._patterns[pid] = entry

        return learned

    def should_avoid(self, context: dict) -> List[str]:
        """Get avoidance suggestions for current context."""
        key = self._context_to_key(context)
        return self._avoidance_rules.get(key, [])

    def apply_to_policy(self, policy, context: dict) -> bool:
        """Modify policy to avoid known failure modes."""
        avoid = self.should_avoid(context)
        if not avoid or not hasattr(policy, 'reason'):
            return False

        if "switch perspective" in avoid and policy.perspective:
            policy.perspective = None  # reset — let system choose freely
        if "expand relations" in avoid:
            policy.expand_relations = ["all"]
        if "lower depth" in avoid and policy.depth_adjust > 0:
            policy.depth_adjust = -2
        if "seek evidence" in avoid:
            policy.explanation_mode = "evidence_first"

        return True

    def _context_to_key(self, ctx: dict) -> str:
        perspective = ctx.get('perspective', 'general')
        domain = ctx.get('domain', '')[:20]
        depth = ctx.get('depth', 0)
        return f"{perspective}_{domain}_{depth}"

    def save(self, path: str = "data/mind_mistakes.json"):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'patterns': self._patterns,
                'avoidance_rules': self._avoidance_rules,
                'version': 1,
            }, f, indent=2, ensure_ascii=False)

    def load(self, path: str = "data/mind_mistakes.json") -> bool:
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._patterns = data.get('patterns', {})
        self._avoidance_rules = data.get('avoidance_rules', {})
        return True


class MindMistakes:
    """Top-level Mind component — mistake learning + persistence."""

    def __init__(self, persist_path: str = "data/mind_mistakes.json"):
        self.memory = MistakeMemory()
        self._persist_path = persist_path

    def load(self) -> bool:
        return self.memory.load(self._persist_path)

    def learn(self, warnings: list, suggestions: list, context: dict = None) -> int:
        return self.memory.learn_from_warnings(warnings, suggestions, context)

    def apply(self, policy, context: dict) -> bool:
        return self.memory.apply_to_policy(policy, context)

    def save(self):
        self.memory.save(self._persist_path)

    def stats(self) -> dict:
        return {
            "patterns": len(self.memory._patterns),
            "rules": len(self.memory._avoidance_rules),
        }
