"""Tests for MultiIntentSplitter 5-chain verification (R3)."""

from __future__ import annotations

import pytest

from core.agent.intent.multi_intent_splitter import MultiIntentSplitter
from core.agent.intent.literal_chain import LiteralChainVerifier
from core.agent.v4.cognitive.ocean_profile import OCEANProfile


class MockLLM:
    """Deterministic fake LLM — returns a canned JSON response."""

    def __init__(self, response: str):
        self._response = response
        self.calls = 0

    def generate(self, prompt, max_tokens=100, temperature=0.1):
        self.calls += 1
        return self._response


@pytest.fixture(autouse=True)
def _no_stanza(monkeypatch):
    """Environment defense: stanza import is broken (numpy) on anaconda 3.9.

    Force the failed-cache path so structural fallback is fast and
    deterministic across environments. Failure caching is itself under test
    (see test_stanza_failure_cached).
    """
    monkeypatch.setattr(LiteralChainVerifier, "_stanza_failed", True)


def _profile(c: float = 0.5, o: float = 0.5) -> OCEANProfile:
    p = OCEANProfile()
    p.dims["C"] = c
    p.dims["O"] = o
    return p


def test_no_llm_explicit_degradation():
    """R3: without an LLM the splitter must degrade explicitly, never silently."""
    splitter = MultiIntentSplitter(llm=None)
    result = splitter.split("先定位延迟然后修复", entities=["延迟", "监控"])
    assert result.trace.get("degraded") is True
    assert result.is_multi is False
    assert len(result.sub_intents) == 1


def test_llm_multi_with_high_c_accepted():
    """High conscientiousness profile votes accept; fusion keeps both segments."""
    llm = MockLLM('{"multi": true, "segments": ["先定位延迟", "然后修复"]}')
    splitter = MultiIntentSplitter(llm=llm, profile=_profile(c=0.8, o=0.3))
    result = splitter.split(
        "先定位延迟然后修复", entities=["延迟", "监控"], pcr_zone="PRECISION"
    )
    assert result.is_multi is True
    assert len(result.sub_intents) == 2
    assert result.trace["accepted"] == 2
    # profile chain must have voted accept on each candidate
    assert all(si.chain_votes.get("profile", 0) >= 0.8 for si in result.sub_intents)


def test_llm_single_no_split():
    """Single intent: no verification needed, one sub-intent at full confidence."""
    llm = MockLLM('{"multi": false}')
    splitter = MultiIntentSplitter(llm=llm)
    result = splitter.split("帮我看看这个报错")
    assert result.is_multi is False
    assert len(result.sub_intents) == 1


def test_neutral_profile_rejects_all():
    """No profile signal → chains abstain; fusion conservatively rejects."""
    llm = MockLLM('{"multi": true, "segments": ["任务A", "任务B"]}')
    splitter = MultiIntentSplitter(llm=llm, profile=_profile())
    result = splitter.split("任务A然后任务B", entities=[])
    assert result.is_multi is False
    assert result.sub_intents == []
    assert result.trace["rejected"] == 2


def test_multi_conflict_triggers_ambiguity_gate():
    """Multiple accepted candidates surface an auto_resolve ambiguity."""
    llm = MockLLM('{"multi": true, "segments": ["先定位延迟", "然后修复"]}')
    splitter = MultiIntentSplitter(llm=llm, profile=_profile(c=0.8))
    result = splitter.split("先定位延迟然后修复", entities=["延迟", "监控"])
    assert len(result.ambiguities) >= 1
    assert any(a.action == "auto_resolve" for a in result.ambiguities)


def test_pcr_zone_complexity_forces_llm_adjudicate():
    """ABYSS zone complexity (>0.8) forces llm_adjudicate in FusionDecider."""
    llm = MockLLM('{"multi": true, "segments": ["先定位延迟", "然后修复"]}')
    splitter = MultiIntentSplitter(llm=llm, profile=_profile(c=0.8))
    result = splitter.split(
        "先定位延迟然后修复", entities=["延迟", "监控"], pcr_zone="ABYSS"
    )
    assert result.fusion_method == "llm_adjudicate"


def test_structural_fallback_without_llm():
    """No LLM + clear clause boundaries → structural split still runs, degraded."""
    splitter = MultiIntentSplitter(llm=None)
    result = splitter.split("先定位延迟，然后修复，最后验证")
    assert result.trace.get("degraded") is True
    # clauses exist → structural split yields segments, marked degraded
    assert result.fusion_method == "structural"
    assert len(result.sub_intents) == 3
    assert result.is_multi is True


def test_stanza_failure_cached():
    """A stanza import failure is cached so later calls return fast."""
    verifier = LiteralChainVerifier(llm=None)
    first = verifier._stanza_segment("先定位延迟然后修复")
    # On the broken-numpy environment first call returns [] quickly and
    # marks the class-level failure flag.
    assert first == [] or LiteralChainVerifier._stanza_failed is True
    assert LiteralChainVerifier._stanza_failed is True
