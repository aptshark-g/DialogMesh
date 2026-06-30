# -*- coding: utf-8 -*-
"""
core/agent/intent_parser/rule_registry.py
──────────────────────────────────────────
IntentRule 注册表 + 冲突检测引擎（P1 修复）。

功能：
  1. 运行时规则注册（线程安全）
  2. 自动冲突检测：fuzz 生成测试字符串，检查多规则同时匹配
  3. 冲突图构建（规则名 → 冲突规则名集合）
  4. 领域隔离：不同 domain 的规则永不冲突
  5. 静态分析脚本：python -m core.agent.intent_parser.rule_registry --check

设计：
  - 替代 intent_parser.py 中的全局 _RULES 列表和 register_intent_rule() 函数
  - 向后兼容：旧函数调用委托到 Registry 单例
"""

from __future__ import annotations

import logging
import random
import re
import string
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger("intent_parser.rule_registry")


@dataclass
class IntentRule:
    """意图规则定义（从 intent_parser.py 迁移并增强）。"""
    category: str  # IntentCategory.value
    patterns: List[re.Pattern]
    required_entities: List[str] = field(default_factory=list)
    optional_entities: List[str] = field(default_factory=list)
    min_confidence: float = 0.5
    priority: int = 0
    is_compound: bool = False
    decomposition_hints: List[str] = field(default_factory=list)
    name: str = ""
    domain: Optional[str] = None
    conflicts_with: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictReport:
    """单条冲突报告。"""
    rule_a: str
    rule_b: str
    domain: Optional[str]
    overlap_type: str  # "pattern" | "explicit" | "fuzz"
    detail: str
    severity: str  # "warning" | "error"
    sample_text: Optional[str] = None  # fuzz 发现的冲突样本


class IntentRuleRegistry:
    """
    线程安全的 IntentRule 注册表，带自动冲突检测。
    """

    _instance: Optional["IntentRuleRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._rules: List[IntentRule] = []
        self._by_name: Dict[str, IntentRule] = {}
        self._conflict_graph: Dict[str, Set[str]] = defaultdict(set)
        self._reports: List[ConflictReport] = []
        self._mutex = threading.Lock()
        self._fuzz_seeds = list(string.ascii_letters + string.digits + " ")

    # ── 核心 API ───────────────────────────────────────────────────────

    def register(self, rule: IntentRule) -> List[ConflictReport]:
        """注册规则，返回本次注册触发的新冲突报告。"""
        if not rule.name:
            raise ValueError("IntentRule name cannot be empty")
        if not rule.patterns:
            raise ValueError("IntentRule patterns cannot be empty")
        new_reports: List[ConflictReport] = []

        with self._mutex:
            if rule.name and rule.name in self._by_name:
                logger.warning("Rule '%s' already registered, overwriting", rule.name)
                # 移除旧规则的冲突边
                old = self._by_name[rule.name]
                for other_name in list(self._conflict_graph.get(old.name, [])):
                    self._conflict_graph[other_name].discard(old.name)
                self._conflict_graph.pop(old.name, None)
                self._rules = [r for r in self._rules if r.name != rule.name]

            self._rules.append(rule)
            if rule.name:
                self._by_name[rule.name] = rule

            # 按优先级排序
            self._rules.sort(key=lambda r: -r.priority)

            # 冲突检测
            new_reports = self._detect_conflicts(rule)
            for rep in new_reports:
                self._conflict_graph[rep.rule_a].add(rep.rule_b)
                self._conflict_graph[rep.rule_b].add(rep.rule_a)
                self._reports.append(rep)
                logger.warning(
                    "[%s] %s vs %s (domain=%s): %s",
                    rep.severity.upper(), rep.rule_a, rep.rule_b,
                    rep.domain or "N/A", rep.detail,
                )

        return new_reports

    def get_conflicts(self, rule_name: str) -> Set[str]:
        """获取与某规则冲突的所有规则名。"""
        return set(self._conflict_graph.get(rule_name, []))

    def all_conflicts(self) -> Dict[str, Set[str]]:
        """返回完整冲突图。"""
        return dict(self._conflict_graph)

    def all_reports(self) -> List[ConflictReport]:
        return list(self._reports)

    def list_rules(self) -> List[IntentRule]:
        return list(self._rules)

    def get_rule(self, name: str) -> Optional[IntentRule]:
        return self._by_name.get(name)

    def remove(self, name: str) -> bool:
        """移除指定名称的规则。返回是否成功移除。"""
        with self._mutex:
            rule = self._by_name.pop(name, None)
            if rule is None:
                return False
            self._rules.remove(rule)
            self._conflict_graph.pop(name, None)
            for neighbors in self._conflict_graph.values():
                neighbors.discard(name)
            return True

    def clear(self) -> None:
        """清空所有规则（仅用于测试隔离）。"""
        with self._mutex:
            self._rules.clear()
            self._by_name.clear()
            self._conflict_graph.clear()
            self._reports.clear()

    def check_all(self, fuzz_samples: int = 100) -> List[ConflictReport]:
        """静态检查所有规则之间的冲突（CI 调用）。"""
        reports: List[ConflictReport] = []
        with self._mutex:
            for i, a in enumerate(self._rules):
                for b in self._rules[i + 1 :]:
                    if a.domain and b.domain and a.domain != b.domain:
                        continue
                    reps = self._check_pair(a, b, fuzz_samples)
                    reports.extend(reps)
        return reports

    def clear(self) -> None:
        """清空所有规则（仅用于测试隔离）。"""
        with self._mutex:
            self._rules.clear()
            self._by_name.clear()
            self._conflict_graph.clear()
            self._reports.clear()

    def _detect_conflicts(self, rule: IntentRule) -> List[ConflictReport]:
        """检测新规则与已有规则的冲突。"""
        reports: List[ConflictReport] = []
        for existing in self._rules:
            if existing is rule:
                continue
            if existing.name == rule.name:
                continue
            # 领域隔离
            if rule.domain and existing.domain and rule.domain != existing.domain:
                continue
            reports.extend(self._check_pair(rule, existing, fuzz_samples=50))
        return reports

    def _check_pair(self, a: IntentRule, b: IntentRule, fuzz_samples: int) -> List[ConflictReport]:
        """检查两个规则之间的冲突。"""
        reports: List[ConflictReport] = []
        domain = a.domain or b.domain

        # 1. 显式冲突声明
        if a.name and b.name:
            if a.name in b.conflicts_with or b.name in a.conflicts_with:
                reports.append(ConflictReport(
                    rule_a=a.name, rule_b=b.name, domain=domain,
                    overlap_type="explicit", detail="Declared in conflicts_with",
                    severity="warning",
                ))

        # 2. Pattern 字符串重叠（同 domain 且相同 pattern 字符串）
        a_patterns = {p.pattern for p in a.patterns}
        b_patterns = {p.pattern for p in b.patterns}
        common = a_patterns & b_patterns
        if common:
            reports.append(ConflictReport(
                rule_a=a.name, rule_b=b.name, domain=domain,
                overlap_type="pattern", detail=f"Share {len(common)} identical patterns: {list(common)[:3]}",
                severity="warning",
            ))

        # 3. Fuzz 测试：生成随机字符串，检查是否同时匹配
        fuzz_hit = self._fuzz_overlap(a, b, fuzz_samples)
        if fuzz_hit:
            reports.append(ConflictReport(
                rule_a=a.name, rule_b=b.name, domain=domain,
                overlap_type="fuzz", detail=f"Fuzz test overlap ({fuzz_samples} samples)",
                severity="error",
                sample_text=fuzz_hit,
            ))

        return reports

    def _fuzz_overlap(self, a: IntentRule, b: IntentRule, n: int) -> Optional[str]:
        """
        生成随机字符串测试两个规则是否同时匹配。
        如果找到冲突样本，返回该字符串；否则返回 None。
        """
        random.seed(42)  # 可重复
        for _ in range(n):
            length = random.randint(5, 60)
            text = "".join(random.choices(self._fuzz_seeds, k=length))
            a_match = any(p.search(text) for p in a.patterns)
            b_match = any(p.search(text) for p in b.patterns)
            if a_match and b_match:
                return text
        return None

    # ── 向后兼容 ───────────────────────────────────────────────────────

    def _legacy_register(self, rule: IntentRule) -> None:
        """兼容旧版 register_intent_rule 的调用签名。"""
        self.register(rule)


# ── 全局单例 ───────────────────────────────────────────────────────────

_REGISTRY = IntentRuleRegistry()


def register_intent_rule(rule: IntentRule) -> None:
    """向后兼容：委托到 Registry 单例。"""
    _REGISTRY.register(rule)


def check_rule_conflicts(registry=None, fuzz_samples: int = 100) -> List[ConflictReport]:
    """静态检查所有规则冲突（CI 调用）。可传入自定义 registry，否则使用全局单例。"""
    target = registry if registry is not None else _REGISTRY
    return target.check_all(fuzz_samples=fuzz_samples)


def get_conflict_graph() -> Dict[str, Set[str]]:
    return _REGISTRY.all_conflicts()


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="IntentRule 冲突检测")
    parser.add_argument("--check", action="store_true", help="运行全量冲突检测")
    parser.add_argument("--fuzz-samples", type=int, default=100, help="Fuzz 测试样本数")
    parser.add_argument("--fail-on-error", action="store_true", help="发现 error 级冲突时退出码 1")
    args = parser.parse_args()

    if args.check:
        reports = check_rule_conflicts(fuzz_samples=args.fuzz_samples)
        print(f"\n{'='*60}")
        print(f"Conflict check complete: {len(reports)} conflicts found")
        print(f"{'='*60}")
        for r in reports:
            print(f"[{r.severity.upper()}] {r.rule_a} vs {r.rule_b} ({r.overlap_type})")
            print(f"  detail: {r.detail}")
            if r.sample_text:
                print(f"  sample: {r.sample_text!r}")
        errors = [r for r in reports if r.severity == "error"]
        if errors and args.fail_on_error:
            sys.exit(1)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(0)
