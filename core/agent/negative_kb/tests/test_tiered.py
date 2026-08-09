"""TieredNegativeKB 测试 — 负知识约束（恢复 + 接入 executor 前置）。"""

from __future__ import annotations

from core.agent.negative_kb.tiered import TieredNegativeKB, SEED_RULES
from core.agent.negative_kb.models import (
    NegativeLevel, NegativeResult, ContextualNegativeRule,
)
from core.agent.negative_kb.rule_store import RuleStore


def _seeded() -> TieredNegativeKB:
    nk = TieredNegativeKB()
    for rule in SEED_RULES:
        nk.register(rule)
    return nk


def test_hard_block_verified_intercepts():
    """HARD_BLOCK 已验证规则 → 拦截（keyword 快路径）。"""
    nk = _seeded()
    r = nk.check("执行 rm -rf /tmp/x 清理目录")
    assert r.blocked is True
    assert r.level == NegativeLevel.HARD_BLOCK
    assert "危险" in r.message or "禁止" in r.message


def test_warn_not_blocked():
    """WARN 规则 → 返回级别但不拦截。"""
    nk = TieredNegativeKB()
    nk.register(ContextualNegativeRule(
        "w1", NegativeLevel.WARN, "需审批", keywords=["sudo"]))
    r = nk.check("运行 sudo apt install python3")
    assert r.level == NegativeLevel.WARN
    assert r.blocked is False


def test_unrelated_context_no_match():
    """无关上下文 → 空结果。"""
    nk = _seeded()
    r = nk.check("读取 README.md 并总结")
    assert r.level is None
    assert r.blocked is False


def test_unverified_hard_block_not_blocked():
    """未验证 HARD_BLOCK → 不拦截（add_with_verification 降级语义）。"""
    store = RuleStore()
    store.add_with_verification(
        ContextualNegativeRule("h1", NegativeLevel.HARD_BLOCK, "危险",
                               keywords=["boom"]),
        verified=False,
    )
    nk = TieredNegativeKB(store=store)
    r = nk.check("boom 场景触发")
    assert r.blocked is False


def test_stats_counts():
    nk = _seeded()
    nk.check("rm -rf /tmp")
    nk.check("读取文件")
    stats = nk.stats()
    assert stats["rules"] >= 3
    assert stats["keyword_hits"] >= 1
