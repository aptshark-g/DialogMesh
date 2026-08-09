"""Association Chain deep tests — golden samples + adversarial assertions (A18).

Phase 5: replaces shallow ``>0`` assertions with exact behavioral checks:
boundary values, math-exact fusion, side-effect freedom, and state transitions.
Covers D-4/D-5/D-10/D-11/D-12/D-14/D-16 artifacts.
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.association.l2_5_belief import (
    select_belief_mode, BeliefAccumulator, Evidence,
)
from core.agent.association.skeleton_library import SkeletonLibrary
from core.agent.association.causal_substrate import CausalSubstrate
from core.agent.association.causal_provenance import (
    diverge, converge, SOURCE_CONFIDENCE, CausalHypothesis,
)
from core.agent.intent.fusion_decider import FusionDecider
from core.agent.intent.models import ChainVotes, ChainVote, SubIntent
from core.agent.intent.ambiguity_gate import (
    AmbiguityGate, AmbiguitySignals, AmbiguityResolver,
)
from core.agent.intent.models import AmbiguityDecision
from core.agent.association.l3_intent import MultiPerspectiveValidator
from core.agent.association.l4_temporal import L4TemporalEngine
from core.agent.association.association_funnel import AssociationFunnel


# ═══════════════════════════════════════════════════════════════════════
# D-4: A13 belief-mode selector boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestBeliefModeSelector:
    def test_complexity_boundary(self):
        class IC:
            complexity_level = 0.8
            noise_level = 0.0
        assert select_belief_mode(IC(), 0.0) == "single_step"
        IC.complexity_level = 0.81
        assert select_belief_mode(IC(), 0.0) == "bayesian"

    def test_noise_boundary(self):
        class IC:
            complexity_level = 0.0
            noise_level = 0.7
        assert select_belief_mode(IC(), 0.0) == "single_step"
        IC.noise_level = 0.71
        assert select_belief_mode(IC(), 0.0) == "bayesian"

    def test_ambiguity_boundary(self):
        assert select_belief_mode(None, 0.5) == "single_step"
        assert select_belief_mode(None, 0.51) == "bayesian"


# ═══════════════════════════════════════════════════════════════════════
# D-4: Bayesian backbone actually converges (not just "probability changes")
# ═══════════════════════════════════════════════════════════════════════

class TestBeliefConvergence:
    def test_causal_evidence_dominates(self):
        acc = BeliefAccumulator()
        for turn in range(1, 6):
            acc.ingest(Evidence("e1", "延迟", "causes", 0.9, turn))
        st = acc.status()
        assert st["locked"] == "诊断", st["locked"]
        assert st["probabilities"]["诊断"] > 0.85
        # 7D decision surface must reflect support, not just probability.
        scores = acc.decision_scores()
        assert scores["诊断"] > scores["吐槽"]

    def test_weak_evidence_stays_unlocked(self):
        acc = BeliefAccumulator()
        for turn in range(1, 3):
            acc.ingest(Evidence("e1", "加密算法", "co_occurrence", 0.2, turn))
        st = acc.status()
        assert st["locked"] is None
        assert st["entropy"] > 0.5  # stuck → LLM trigger region
        assert st["needs_llm"] is True

    def test_force_crystal_at_turn_5(self):
        acc = BeliefAccumulator()
        for turn in range(1, 6):
            acc.ingest(Evidence("e1", "弱信号", "co_occurrence", 0.15, turn))
        assert acc.locked_intent is not None
        assert acc.turn_count == 5


# ═══════════════════════════════════════════════════════════════════════
# D-9: skeleton library integrity
# ═══════════════════════════════════════════════════════════════════════

class TestSkeletonLibraryDeep:
    VALID_CONSTRAINT_FIELDS = {
        "domain_hint", "has_feedback", "involves_dissipation",
        "involves_storage", "causal_direction", "involves_transformation",
    }

    def test_twenty_skeletons(self):
        lib = SkeletonLibrary()
        assert len(lib.skeletons) == 20

    def test_requires_fields_are_real_constraints(self):
        lib = SkeletonLibrary()
        for sk in lib.skeletons:
            for req in sk.requires:
                assert req in self.VALID_CONSTRAINT_FIELDS, f"{sk.name}: {req}"

    def test_names_unique(self):
        lib = SkeletonLibrary()
        names = [s.name for s in lib.skeletons]
        assert len(names) == len(set(names))

    def test_requires_coverage_scoring(self):
        from core.agent.association.models import CausalConstraints
        from core.agent.association.skeleton_matcher import SkeletonMatcher
        lib = SkeletonLibrary()
        m = SkeletonMatcher(lib)
        # dissipation-only constraint should rank source_dissipate at 1.0
        match = m.match(CausalConstraints(
            domain_hint="general", involves_dissipation=True,
        ))
        assert match is not None
        assert "DISSIPATE" in [r.name for r in match.roles]


# ═══════════════════════════════════════════════════════════════════════
# D-10: causal substrate — to_prior caps + HARD_BLOCK handling
# ═══════════════════════════════════════════════════════════════════════

class TestCausalSubstrateDeep:
    def test_to_prior_caps_at_07(self):
        from core.agent.association.models import SkeletonMatch
        m = SkeletonMatch(roles=[], coverage=0.99, score=0.99)
        assert m.to_prior() == 0.7  # A22: never 1.0
        m2 = SkeletonMatch(roles=[], coverage=0.6, score=0.6)
        assert m2.to_prior() == 0.3
        m3 = SkeletonMatch(roles=[], coverage=0.4, score=0.4)
        assert m3.to_prior() == 0.0

    def test_process_chain_blocked_flag(self):
        class Step:
            def __init__(self, s):
                self.action_summary = s
        class Edge:
            from_step_id = "a"
            to_step_id = "b"
        class G:
            nodes = {"a": Step("run build"), "b": Step("deploy")}
            edges = {"e1": Edge()}
        cs = CausalSubstrate(G())
        results = cs.process_chain([Step("run build"), Step("deploy")])
        assert results, "chain of 2 should produce a result"
        assert "blocked" in results[0]


# ═══════════════════════════════════════════════════════════════════════
# D-12: provenance — math-exact fusion + reversibility gate
# ═══════════════════════════════════════════════════════════════════════

class TestProvenanceDeep:
    def test_source_fusion_is_math_exact(self):
        # 1 - (1-0.95)(1-0.7) = 0.985
        hs = [
            CausalHypothesis("a", "b", "bond_graph", "bond x", SOURCE_CONFIDENCE["bond_graph"]),
            CausalHypothesis("a", "b", "behavior", "seq y", SOURCE_CONFIDENCE["behavior"]),
        ]
        r = converge(hs, do_validator=None, evidence_facts=[])
        assert math.isclose(r.confidence, 0.985, abs_tol=1e-9)

    def test_hard_block_short_circuits(self):
        class DV:
            def verify_negative(self, f, t):
                return "HARD_BLOCK"
        hs = [CausalHypothesis("a", "b", "bond_graph", "x", 0.95)]
        r = converge(hs, do_validator=DV(), evidence_facts=[])
        assert r.accepted is False
        assert r.rejected and r.rejected[0]["reason"] == "do-calculus HARD_BLOCK"

    def test_overfit_rejected_coverage_100(self):
        hs = [CausalHypothesis("a", "b", "llm", "机制 1", 0.3)]
        r = converge(hs, do_validator=None, evidence_facts=["机制 1 exactly"])
        # coverage == 1.0 → overfit → reject (A24)
        assert r.accepted is False

    def test_diverge_filters_non_mechanism_lines(self):
        class LLM:
            def generate(self, prompt, **kw):
                return "机制: 转换损耗\n这是一句无关解释\n机制: 存储积累"
        hs = diverge("a", "b", llm=LLM())
        llm_hs = [h for h in hs if h.source == "llm"]
        assert len(llm_hs) == 2, f"expected 2 mechanism lines, got {len(llm_hs)}"
        assert all("机制" in h.rationale for h in llm_hs)


# ═══════════════════════════════════════════════════════════════════════
# D-11: FusionDecider — strategy boundaries + side-effect freedom
# ═══════════════════════════════════════════════════════════════════════

class TestFusionDeciderDeep:
    def _votes(self, confs):
        return ChainVotes(votes={
            f"c{i}": ChainVote(f"c{i}", c, "accept", "r")
            for i, c in enumerate(confs)
        })

    def test_strategy_selection_by_std(self):
        d = FusionDecider()
        c = SubIntent(id="s1", text="x")
        r1 = d.decide(c, self._votes([0.8, 0.85, 0.82]), pcr_complexity=0.0)
        assert r1.fusion_method == "vote_consensus"  # std < 0.3
        r2 = d.decide(c, self._votes([0.95, 0.2, 0.8]), pcr_complexity=0.0)
        assert r2.fusion_method == "weighted_mix"     # 0.3 <= std <= 0.45
        r3 = d.decide(c, self._votes([0.99, 0.01, 0.98]), pcr_complexity=0.0)
        assert r3.fusion_method == "llm_adjudicate"   # std > 0.45

    def test_pcr_complexity_forces_llm(self):
        class LLM:
            def generate(self, prompt, **kw):
                return '{"accept": true, "confidence": 0.8}'
        d = FusionDecider(llm=LLM())
        c = SubIntent(id="s1", text="x")
        r = d.decide(c, self._votes([0.9, 0.85, 0.82]), pcr_complexity=0.9)
        assert r.fusion_method == "llm_adjudicate"

    def test_weighted_mix_no_side_effect(self):
        d = FusionDecider()
        c = SubIntent(id="s1", text="x")
        votes = ChainVotes(votes={
            "literal": ChainVote("literal", 0.9, "accept", "a"),
            "discourse": ChainVote("discourse", 0.9, "accept", "b"),
        })
        before = {k: v.confidence for k, v in votes.votes.items()}
        d.decide(c, votes, pcr_noise=0.8)  # noise would boost literal/damp discourse
        after = {k: v.confidence for k, v in votes.votes.items()}
        assert before == after, "weighted_mix must not mutate ChainVote objects"


# ═══════════════════════════════════════════════════════════════════════
# D-11: AmbiguityGate triggers + Resolver level ordering
# ═══════════════════════════════════════════════════════════════════════

class TestAmbiguityDeep:
    def test_gate_action_escalation(self):
        g = AmbiguityGate()
        assert g.evaluate(AmbiguitySignals(entropy=0.2, confidence=0.9)).action == "pass"
        assert g.evaluate(AmbiguitySignals(
            entropy=0.9, confidence=0.1, chain_disagreement=0.8,
        )).action == "llm_resolve"
        assert g.evaluate(AmbiguitySignals(
            entropy=0.9, confidence=0.05, chain_disagreement=0.9, pcr_noise=0.9,
        )).action == "ask_user"

    def test_resolver_levels_ascending(self):
        # history present → context inheritance first
        r1 = AmbiguityResolver(history=["上轮主题"]).resolve(
            "新问题", AmbiguityDecision(trigger="high_entropy", score=0.6, action="auto_resolve"))
        assert r1["method"] == "context_inheritance"
        # no history, no behavior/profile, no llm → ask_user
        r2 = AmbiguityResolver().resolve(
            "新问题", AmbiguityDecision(trigger="high_entropy", score=0.9, action="ask_user"))
        assert r2["method"] == "ask_user"
        assert r2["resolved"] is False


# ═══════════════════════════════════════════════════════════════════════
# D-11: validate_split conservative verdict
# ═══════════════════════════════════════════════════════════════════════

class TestValidateSplitDeep:
    def test_no_context_rejects_split(self):
        val = MultiPerspectiveValidator()
        r = val.validate_split(["修复延迟", "优化告警"], {}, pcr_zone="MIXED")
        assert r["accepted"] is False  # no evidence → no consensus → reject
        assert r["ratio"] == 0.0
        assert r["total"] == 2


# ═══════════════════════════════════════════════════════════════════════
# D-16: triparty reconcile — injection + blocking + window trim
# ═══════════════════════════════════════════════════════════════════════

class TestTripartyDeep:
    def test_behavior_injection_and_blocking(self):
        eng = L4TemporalEngine()
        eng.record("DIAG", turn=1)
        eng.record("FIX", turn=2)
        r = eng.triparty_reconcile(
            behavior_sequences=[("FIX", "EXPLORE"), ("EXPLORE", "QUERY")],
            engineering_constraints={
                "forbidden_transitions": [["DIAG", "VENT"]],
                "resource_constraints": {"EXPLORE": False},
            },
        )
        matrix = r["reconciled_matrix"]
        assert matrix["DIAG"]["FIX"] == 1.0
        assert "EXPLORE" not in matrix.get("FIX", {}), "blocked transition leaked"
        assert matrix["EXPLORE"]["QUERY"] == 1.0
        assert any(b["to"] == "EXPLORE" for b in r["blocked_transitions"])

    def test_window_trimmed_after_injection(self):
        eng = L4TemporalEngine(window_size=2)
        for i in range(30):
            eng.record(f"I{i}", turn=i)
        assert len(eng._intent_sequence) <= eng.window * 3


# ═══════════════════════════════════════════════════════════════════════
# D-5: fine entry run_layers produces all six layers
# ═══════════════════════════════════════════════════════════════════════

class TestRunLayersDeep:
    def test_all_layers_present(self):
        f = AssociationFunnel()
        r = f.run_layers("scan 0x401000 with frida hook", pcr_zone="ATOMIC")
        layers = r["layers"]
        assert set(layers.keys()) == {"l1", "l1_5", "l2_5", "l3", "l4", "l5"}
        assert layers["l1_5"].consensus is True  # no-context → consensus passthrough
        assert layers["l5"]["structural_prior"] <= 0.7  # A22 cap
