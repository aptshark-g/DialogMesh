"""Tests for InertiaWeightGraph feed path (P7 / R2 shared lifecycle)."""

from __future__ import annotations

import pytest

from core.agent.v4.cognitive.inertia_graph import InertiaWeightGraph


@pytest.fixture
def graph(tmp_path):
    return InertiaWeightGraph(persist_path=str(tmp_path / "inertia.json"))


def test_feed_evidence_confirms_pattern(graph):
    """3+ perspectives above 0.5 → candidate → confirmed."""
    graph.feed_evidence("quality_centric", {
        "design": 0.9, "engineering": 0.85, "behavior": 0.78,
    })
    p = graph.pattern("quality_centric")
    assert p is not None
    assert p.state == "confirmed"
    assert p.weight >= 0.5
    assert sum(1 for v in p.evidence.values() if v > 0.5) >= 3


def test_feed_evidence_single_source_stays_candidate(graph):
    """One weak perspective → remains candidate, low weight."""
    graph.feed_evidence("whitebox_pref", {"design": 0.6})
    p = graph.pattern("whitebox_pref")
    assert p.state == "candidate"
    assert p.weight < 0.5


def test_feed_evidence_reaches_stable(graph):
    """5+ perspectives + 30+ stable rounds → stable."""
    for _ in range(35):
        graph.feed_evidence("adversarial_thinking", {
            "design": 0.9, "engineering": 0.85, "behavior": 0.78,
            "llm": 0.82, "meta": 0.88,
        })
    p = graph.pattern("adversarial_thinking")
    assert p.state == "stable"
    assert p.weight > 0.7


def test_feed_counter_weakens_pattern(graph):
    """Counter-examples reduce weight and move toward weakening."""
    graph.feed_evidence("quality_centric", {
        "design": 0.9, "engineering": 0.85, "behavior": 0.78,
    })
    for _ in range(3):
        graph.feed_counter("quality_centric", "behavior")
    p = graph.pattern("quality_centric")
    assert p.counter_examples >= 3
    assert p.state in ("weakening", "broken")
    assert p.weight < 0.5


def test_feed_auto_registers_unknown_pattern(graph):
    """Missing pattern auto-seeded as candidate."""
    p = graph.feed_evidence("novel_pattern", {"behavior": 0.55})
    assert p.state == "candidate"
    assert "behavior" in p.evidence
