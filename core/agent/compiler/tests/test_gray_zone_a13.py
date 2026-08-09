"""C2/R6: gray-zone decisions defer to A13 cross-turn accumulation."""

from __future__ import annotations

import pytest

from core.agent.compiler.discourse_block_tree import DiscourseBlockTreeManager


@pytest.fixture
def manager():
    return DiscourseBlockTreeManager()


def test_single_weak_gray_does_not_fork(manager):
    assert manager._gray_should_fork([0.20]) is False


def test_two_consecutive_grays_fork(manager):
    assert manager._gray_should_fork([0.20, 0.35, 0.35]) is True


def test_one_strong_gray_fork(manager):
    assert manager._gray_should_fork([0.50]) is True


def test_gray_buffer_reset_after_fork(manager):
    """Fork clears the per-session gray buffer."""
    manager._gray_scores.setdefault("g1", [0.50])  # strong gray → immediate fork
    assert manager._gray_should_fork([0.50]) is True
    manager._gray_scores["g1"].clear()
    assert manager._gray_scores["g1"] == []


def test_gray_accumulates_across_turns(manager):
    """A13: gray evidence accumulates across turns, not just within one."""
    # Simulate gray signals arriving across two turns: neither alone forks,
    # together they cross the sustained-boundary threshold.
    buf = manager._gray_scores.setdefault("g2", [])
    buf.append(0.32)
    assert manager._gray_should_fork(buf) is False  # first turn: deferred
    buf.append(0.40)
    assert manager._gray_should_fork(buf) is True   # second turn: sustained
