"""PCR V2 tests — design-contract assertions (DESIGN_PCR.md §8).

Golden-set zone expectations come from DESIGN_PCR.md §8.2 — the design
contract, NOT measured output. Do not weaken these to match current
behavior; that is exactly the fake-test pattern we retired.

Items the current implementation cannot yet meet are marked
xfail(reason="P1 ...") — they stay RED until the P1 router work (real X
semantic distance with subgraph/retrieval prior, Z mood de-bias, bilingual
consistency) makes them pass, then the xfail marker is removed.

Structural invariants (zone mapping, coordinate ranges, no hardcoded
keywords) are asserted unconditionally — they are model-free and stable.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.agent.pcr_router_v2 import PCRRouterV2, StructuralFeatures

# Skip LLM review in tests (adds latency, not needed for structural correctness)
PCRRouterV2._llm_review_enabled = False

# ══════════════════════════════════════════════════════════════════════
# Structural features — pure, model-free, deterministic
# ══════════════════════════════════════════════════════════════════════

def test_structural_hex_entity():
    sf = StructuralFeatures.extract("scan 0x401000 and patch with NOP")
    assert sf.entity_count >= 1, f"Should find hex: got {sf.entity_count}"
    assert sf.verb_count >= 1, f"Should find verbs: got {sf.verb_count}"


def test_structural_chinese_question():
    sf = StructuralFeatures.extract("为什么这个函数被优化掉了？")
    assert sf.question_markers >= 1
    assert sf.cjk_ratio > 0.5


def test_structural_imperative():
    sf = StructuralFeatures.extract("run the test!")
    assert sf.imperative_markers >= 1


def test_structural_empty():
    sf = StructuralFeatures.extract("")
    assert sf.word_count == 0
    assert sf.verb_count == 0


# ══════════════════════════════════════════════════════════════════════
# Zone mapping — deterministic, design thresholds (DESIGN_PCR §8.1)
# ══════════════════════════════════════════════════════════════════════

def test_zone_from_xyz_design_thresholds():
    """Each zone maps exactly per the design baseline (0.2/0.2, 0.7/0.7/0.5)."""
    cases = [
        ((0.1, 0.1, 0.0), "ATOMIC"),
        ((0.8, 0.8, 0.6), "ABYSS"),
        ((0.3, 0.6, 0.2), "PRECISION"),
        ((0.6, 0.3, -0.2), "EXPLORE"),
        ((0.5, 0.5, 0.0), "MIXED"),   # no zone condition satisfied exactly at boundary
        ((0.5, 0.5, -0.6), "PSYCHE"),
        ((0.4, 0.4, 0.0), "MIXED"),
    ]
    for (x, y, z), expected in cases:
        zone = PCRRouterV2._zone_from_xyz(x, y, z)
        assert zone == expected, f"({x},{y},{z}) -> {zone}, expected {expected}"


def test_zone_mapping_is_complete():
    """All zones map to valid execution modes."""
    zones = {"ATOMIC": "cache", "PSYCHE": "small_model", "EXPLORE": "retrieval",
             "PRECISION": "cot", "ABYSS": "react", "MIXED": "slow"}
    for zone, expected_mode in zones.items():
        mode = PCRRouterV2._execution_mode(zone)
        assert mode == expected_mode, f"{zone} → {mode} (expected {expected_mode})"


def test_no_hardcoded_keywords():
    """Verify zero keyword lists in PCR V2 code."""
    text = (Path(__file__).parent.parent / "core/agent/pcr_router_v2.py").read_text(encoding="utf-8")
    import re
    keyword_sets = re.findall(r'\w+\s*=\s*\{[^}]{30,}\}', text)
    bad = [s for s in keyword_sets if any(ord(c) > 127 for c in s)]
    assert len(bad) == 0, f"Hardcoded word sets found: {bad[:3]}"


# ══════════════════════════════════════════════════════════════════════
# End-to-end routing — GOLDEN SET (design contract, DESIGN_PCR §8.2)
# ══════════════════════════════════════════════════════════════════════

GOLDEN = [
    ("删除这个文件", "ATOMIC"),
    ("delete this file", "ATOMIC"),
    ("把上个月所有未读邮件归档并生成报表", "PRECISION"),
    ("量子退火在物流调度里到底怎么用", "EXPLORE"),
    ("帮我查一下人类存在的意义相关的论文", "ABYSS"),
    ("我好烦，什么都不想做", "PSYCHE"),
    ("你知道昨天新闻里说的那个模型吗，随便聊聊", "MIXED"),
    ("How to deploy k8s cluster with terraform", "PRECISION"),
    ("why do cats purr", "EXPLORE"),
    ("fix the bug in auth module please", "ATOMIC"),
    ("I feel exhausted and want to quit everything", "PSYCHE"),
]


@pytest.mark.xfail(strict=True, reason="P1 维度改造未落地: X 语义距离/中文 Y/Z 情绪未达标 (§9.5)")
def test_golden_set_design_contract():
    """Golden set asserts DESIGN expectations. Fails loudly on any gap."""
    for text, expected in GOLDEN:
        r = PCRRouterV2.route(text)
        if r.zone != expected:
            pytest.fail(
                f"'{text}' -> {r.zone} ({r.x_axis:.2f},{r.y_axis:.2f},{r.z_axis:+.2f}); "
                f"design expects {expected}"
            )


@pytest.mark.xfail(strict=True, reason="P1: X semantic distance needs subgraph/retrieval prior (§5)")
def test_golden_x_separates_familiar_vs_novel():
    """Familiar short command must be ATOMIC (low X); cross-domain question must not."""
    familiar = PCRRouterV2.route("删除这个文件")
    novel = PCRRouterV2.route("量子退火在物流调度里到底怎么用")
    assert familiar.x_axis < 0.2, f"familiar X={familiar.x_axis:.2f} should be < 0.2"
    assert novel.x_axis > 0.5, f"novel X={novel.x_axis:.2f} should be > 0.5"


@pytest.mark.xfail(strict=True, reason="P1: Z mood argmax bias — 10/14 queries hit solution_seeking")
def test_z_does_not_force_solution():
    """A pure why-question must not be solution_seeking (z should be <= 0)."""
    if PCRRouterV2._mood_vectors is None:
        pytest.skip("mood vectors not loaded — Z degradation path cannot be tested here")
    r = PCRRouterV2.route("为什么这个函数被优化掉了")
    assert r.z_axis <= 0, f"why-question z={r.z_axis:+.2f} should be <= 0"


@pytest.mark.xfail(strict=True, reason="P1: same intent across languages must route consistently")
def test_bilingual_intent_consistency():
    """删除这个文件 / delete this file are the same intent → same zone."""
    zh = PCRRouterV2.route("删除这个文件").zone
    en = PCRRouterV2.route("delete this file").zone
    assert zh == en, f"zh={zh} en={en} should agree"


def test_v2_coordinates_in_range():
    r = PCRRouterV2.route("帮我分析这个加密算法是什么")
    assert 0 <= r.x_axis <= 1
    assert 0 <= r.y_axis <= 1
    assert -1 <= r.z_axis <= 1
    assert r.structural is not None
    assert r.structural.cjk_ratio > 0
    assert "sf_verb" in r.metadata and "sf_entity" in r.metadata


# ══════════════════════════════════════════════════════════════════════
# Legacy compatibility — RuleBasedPCR exists and delegates to V2
# ══════════════════════════════════════════════════════════════════════

def test_rule_based_legacy_adapter():
    """RuleBasedPCR.evaluate is a real adapter onto PCRRouterV2.route."""
    from core.agent.pcr.rule_based import RuleBasedPCR
    legacy = RuleBasedPCR()
    out = legacy.evaluate("delete this file")
    r = PCRRouterV2.route("delete this file")
    assert out.expectation == r.zone, f"adapter zone {out.expectation} != route zone {r.zone}"
    assert out.execution_mode == r.execution_mode
    assert out.implementation == "rule_based_v2"
