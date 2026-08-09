"""I9 测试补全：FusionDecider（三策略 + PCR 调控）+ AmbiguityGate（5 触发器）。

覆盖 R3 拍板：T1 融合裁决（fusion_decider 三策略自动选 + PCR
complexity/noise 调控）+ T1 灰区判定（ambiguity_gate 5 触发器 →
pass/auto/llm/ask_user 升级决策）。
"""

from __future__ import annotations

from core.agent.intent.models import (
    SubIntent, ChainVote, ChainVotes,
)
from core.agent.intent.ambiguity_gate import AmbiguitySignals, AmbiguityGate
from core.agent.intent.fusion_decider import FusionDecider


def _candidate(text="修复bug") -> SubIntent:
    return SubIntent(id="s0", text=text, entities=["bug"])


def _votes(*pairs) -> ChainVotes:
    """pairs: (chain, confidence, decision)."""
    return ChainVotes(votes={
        name: ChainVote(chain=name, confidence=conf, decision=dec)
        for name, conf, dec in pairs
    })


# ── FusionDecider ──────────────────────────────────────────────────────

def test_fusion_vote_consensus_low_spread():
    """std < 0.3 → majority vote (0ms)，accept 胜出。"""
    d = FusionDecider()
    votes = _votes(
        ("profile", 0.8, "accept"), ("association", 0.75, "accept"),
        ("discourse", 0.7, "accept"), ("literal", 0.72, "accept"),
    )
    r = d.decide(_candidate(), votes)
    assert r.fusion_method == "vote_consensus"
    assert len(r.sub_intents) == 1
    assert r.trace["accept"] == 4


def test_fusion_reject_when_minority():
    votes = _votes(
        ("profile", 0.9, "accept"), ("association", 0.85, "reject"),
        ("discourse", 0.8, "reject"), ("literal", 0.9, "reject"),
    )
    r = FusionDecider().decide(_candidate(), votes)
    assert r.trace["method"] == "vote_consensus"
    assert len(r.sub_intents) == 0  # reject 多数 → 候选不通过


def test_fusion_weighted_mix_mid_spread():
    """0.3 ≤ std ≤ 0.45 → confidence-weighted blend。"""
    votes = _votes(
        ("profile", 0.95, "accept"), ("association", 0.3, "reject"),
        ("discourse", 0.9, "accept"), ("literal", 0.1, "reject"),
    )
    r = FusionDecider().decide(_candidate(), votes)
    assert r.fusion_method == "weighted_mix"
    assert 0 <= r.split_confidence <= 1


def test_fusion_llm_adjudicate_high_spread():
    """std > 0.45 → LLM 仲裁。"""
    class MockLLM:
        def generate(self, prompt, max_tokens=100, temperature=0.1):
            return '{"accept": true, "confidence": 0.9, "reason": "ok"}'
    votes = _votes(
        ("profile", 1.0, "accept"), ("association", 0.0, "reject"),
        ("discourse", 1.0, "accept"), ("literal", 0.0, "reject"),
    )
    r = FusionDecider(llm=MockLLM()).decide(_candidate(), votes)
    assert r.fusion_method == "llm_adjudicate"
    assert len(r.sub_intents) == 1


def test_fusion_pcr_complexity_forces_llm():
    """I6: PCR complexity>0.8 强制 LLM 仲裁（无视低分散度）。"""
    class MockLLM:
        def generate(self, prompt, max_tokens=100, temperature=0.1):
            return '{"accept": false, "confidence": 0.2, "reason": "pcr"}'
    votes = _votes(
        ("profile", 0.8, "accept"), ("association", 0.78, "accept"),
        ("discourse", 0.75, "accept"), ("literal", 0.8, "accept"),
    )
    r = FusionDecider(llm=MockLLM()).decide(
        _candidate(), votes, pcr_complexity=0.9)
    assert r.fusion_method == "llm_adjudicate"
    assert len(r.sub_intents) == 0  # LLM 否决


def test_fusion_pcr_noise_weights_literal():
    """I6: PCR noise>0.7 加权 literal×1.5 / discourse×0.7。"""
    # std ∈ [0.3, 0.45] 触发 weighted_mix（conf 0.95/0.1/0.85/0.2 → pstdev≈0.38）
    votes = _votes(
        ("literal", 0.95, "accept"), ("association", 0.1, "reject"),
        ("discourse", 0.85, "accept"), ("profile", 0.2, "reject"),
    )
    r_clean = FusionDecider().decide(_candidate(), votes)
    r_noisy = FusionDecider().decide(_candidate(), votes, pcr_noise=0.8)
    assert r_clean.fusion_method == "weighted_mix"
    assert r_noisy.fusion_method == "weighted_mix"
    # 噪声加权改变置信度（literal×1.5 / discourse×0.7 生效）
    assert abs(r_noisy.split_confidence - r_clean.split_confidence) > 0.01
    assert len(r_noisy.sub_intents) == 1


# ── AmbiguityGate ──────────────────────────────────────────────────────

def test_gate_pass_no_triggers():
    g = AmbiguityGate()
    d = g.evaluate(AmbiguitySignals())
    assert d.action == "pass"
    assert d.trigger == ""


def test_gate_low_confidence_auto_resolve():
    g = AmbiguityGate()
    d = g.evaluate(AmbiguitySignals(confidence=0.2))
    assert d.trigger == "low_confidence"
    assert d.action == "auto_resolve"


def test_gate_high_entropy_llm_resolve():
    g = AmbiguityGate()
    d = g.evaluate(AmbiguitySignals(
        entropy=0.9, confidence=0.3, chain_disagreement=0.6))
    assert "high_entropy" in d.trigger
    assert d.action == "llm_resolve"


def test_gate_conflict_ask_user():
    g = AmbiguityGate()
    d = g.evaluate(AmbiguitySignals(
        entropy=0.9, confidence=0.1, chain_disagreement=0.9,
        multi_intent_conflict=True, needs_clarification=True))
    assert d.action == "ask_user"
    assert "multi_intent_conflict" in d.trigger


def test_gate_pcr_noise_escalates():
    g = AmbiguityGate()
    base = AmbiguitySignals(entropy=0.9, confidence=0.3,
                            chain_disagreement=0.6)
    d_low = g.evaluate(base)  # 3 triggers → score 0.6 → llm_resolve
    assert d_low.action == "llm_resolve"
    d_noisy = g.evaluate(AmbiguitySignals(
        entropy=0.9, confidence=0.3, chain_disagreement=0.6, pcr_noise=0.9))
    # pcr_noise 推高 score（0.6+0.18=0.78）→ 升级到 ask_user
    assert d_noisy.score > d_low.score
    assert d_noisy.action == "ask_user"
