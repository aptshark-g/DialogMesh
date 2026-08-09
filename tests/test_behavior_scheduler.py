"""Behavior chain P3: four-layer scheduler (BC05 §3) + explicit commitment."""
import asyncio

import pytest

from core.agent.behavior.scheduler import (
    BehaviorScheduler,
    ScheduleMode,
    ci_width_proxy,
    is_risk_action,
)
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.explicit_commitment import (
    CommitmentRegistry,
    cold_start_retry_trigger,
    extract_keywords,
    recognize_declaration,
    simulate_with_retry,
)


class TestScheduler:
    def setup_method(self):
        self.s = BehaviorScheduler()

    def test_l1_cost_floor(self):
        d = self.s.decide(token_budget_remaining=0.0)
        assert d.mode == ScheduleMode.STATS
        assert "L1" in d.reason

    def test_l2_risk_hijack(self):
        d = self.s.decide(token_budget_remaining=100, risk_action=True)
        assert d.mode == ScheduleMode.LLM
        assert "L2" in d.reason

    def test_l3_cold_start_explore(self):
        d = self.s.decide(total_turns=2, ci_width=0.0)
        assert d.mode == ScheduleMode.EXPLORE
        assert d.epsilon > 0.5

    def test_l4_converged_stats(self):
        d = self.s.decide(total_turns=50, ci_width=0.05)
        assert d.mode == ScheduleMode.STATS
        assert "L4" in d.reason

    def test_l4_chaotic_llm(self):
        d = self.s.decide(total_turns=50, ci_width=0.25)
        assert d.mode == ScheduleMode.LLM
        assert "L4" in d.reason

    def test_l4_diverged_ask(self):
        d = self.s.decide(total_turns=50, ci_width=0.7)
        assert d.mode == ScheduleMode.ASK

    def test_epsilon_decay(self):
        assert self.s.epsilon_for_turns(3) >= 0.5
        assert 0.1 <= self.s.epsilon_for_turns(12) < 0.5
        assert self.s.epsilon_for_turns(30) <= 0.1
        assert self.s.epsilon_for_turns(60, anchors=100) == 0.02

    def test_risk_keywords(self):
        assert is_risk_action("删除文件")
        assert is_risk_action("grant permission to user")
        assert not is_risk_action("写代码")

    def test_ci_width_proxy(self):
        g = BehaviorGraph()
        assert ci_width_proxy(g) == 1.0  # no data → diverged
        from core.agent.behavior.models import BehaviorStep
        s1 = BehaviorStep("a1", "写代码", "code")
        s2 = BehaviorStep("a2", "测试", "test")
        g.add_step(s1)
        g.add_step(s2)
        for _ in range(20):
            g.record_edge(s1, s2, success=True)
        width = ci_width_proxy(g)
        assert width < 0.15  # converged with 20 samples (all-success → 0)


class TestCommitmentLifecycle:
    def setup_method(self):
        self.reg = CommitmentRegistry()
        self.c = self.reg.add(
            when="用户说部署",
            should="先跑测试再部署",
            rather_than="直接部署",
            because="防止带 bug 上线",
        )

    def test_lifecycle(self):
        assert self.c.status == "pending"
        assert self.reg.arm(self.c.id).status == "armed"
        assert self.reg.fire(self.c.id).status == "fired"
        assert self.reg.complete(self.c.id).status == "done"
        assert self.reg.fire(self.c.id) is None  # terminal, no transition

    def test_cancel_from_pending(self):
        c2 = self.reg.add(when="X", should="Y")
        assert self.reg.cancel(c2.id).status == "cancelled"

    def test_deterministic_match(self):
        self.reg.arm(self.c.id)
        hits = self.reg.match("现在用户说部署完成")
        assert any(h.id == self.c.id for h in hits)
        assert self.reg.match("完全无关的话题") == []

    def test_context_blocks_limit(self):
        for i in range(5):
            c = self.reg.add(when=f"触发词{i}", should=f"行为{i}")
            self.reg.arm(c.id)
        blocks = self.reg.context_blocks("触发词1 触发词2 触发词3 触发词4")
        assert len(blocks) <= 3
        assert all(b["status"] in ("armed", "fired") for b in blocks)

    def test_feedback_flow_to_graph(self):
        from core.agent.behavior.graph_store import BehaviorGraph
        from core.agent.behavior.models import BehaviorStep
        g = BehaviorGraph()
        g.add_step(BehaviorStep("prev_1", "部署服务", "deploy"))
        self.reg.arm(self.c.id)
        self.reg.fire(self.c.id)
        sig = self.reg.feedback(self.c.id, "completed", graph=g)
        assert sig is not None
        assert sig["outcome"] == "completed"
        assert len(g.nodes) >= 2
        assert len(g.edges) >= 1
        assert self.c.status == "done"

    def test_trigger_alone_no_signal(self):
        """Firing must not emit a learning signal (防自我强化)."""
        assert self.reg.feedback(self.c.id, "fired") is None


class TestDistillation:
    def test_stable_pattern_distills(self):
        from core.agent.behavior.graph_store import BehaviorGraph
        from core.agent.behavior.models import BehaviorStep
        g = BehaviorGraph()
        s1 = BehaviorStep("d1", "写代码", "code")
        s2 = BehaviorStep("d2", "测试", "test")
        g.add_step(s1)
        g.add_step(s2)
        for _ in range(8):
            g.record_edge(s1, s2, success=True)
        reg = CommitmentRegistry()
        created = reg.distill_from_graph(g, min_sample=5, min_success=0.7)
        assert len(created) >= 1
        assert created[0].source == "distilled"
        assert created[0].when == "写代码"
        assert created[0].should == "测试"
        # Idempotent: second run adds nothing.
        assert reg.distill_from_graph(g, min_sample=5, min_success=0.7) == []


class TestDeclaration:
    def test_recognize_chinese(self):
        r = recognize_declaration("以后每次部署前要记得先跑测试")
        assert r is not None
        when, should, conf = r
        assert "部署" in when or "每次部署" in when
        assert "跑测试" in should or "测试" in should
        assert conf >= 0.7

    def test_recognize_english(self):
        r = recognize_declaration("when user asks to deploy, you should run tests first")
        assert r is not None
        assert r[2] == 0.9

    def test_recognize_none(self):
        assert recognize_declaration("今天天气怎么样") is None

    def test_extract_keywords(self):
        keys = extract_keywords("以后每次部署前要记得先跑测试")
        assert len(keys) >= 2
        assert "测试" in keys


class TestReSimulation:
    def test_retry_trigger_gate(self):
        assert cold_start_retry_trigger(turn=2) is True
        assert cold_start_retry_trigger(turn=50) is False
        assert cold_start_retry_trigger(
            {"zone": "ABYSS", "ambiguity": 0.6}, turn=50,
        ) is True
        assert cold_start_retry_trigger(
            {"zone": "ATOMIC", "ambiguity": 0.2}, turn=50,
        ) is False

    def test_simulate_success_first_try(self):
        class FakeLLM:
            async def generate(self, prompt, max_tokens=800):
                return "run the test suite"

        async def go():
            return await simulate_with_retry(
                FakeLLM(), "deploy to prod",
                lambda raw: (True, "ok"), max_attempts=3,
            )

        c = asyncio.run(go())
        assert c is not None
        assert c.source == "distilled"
        assert c.should == "run the test suite"

    def test_simulate_revises_after_failure(self):
        class RevisingLLM:
            def __init__(self):
                self.calls = 0

            async def generate(self, prompt, max_tokens=800):
                self.calls += 1
                if self.calls == 1:
                    return "bad strategy"
                return "revised strategy"

        async def go():
            return await simulate_with_retry(
                RevisingLLM(), "scenario",
                lambda raw: (raw == "revised strategy", raw),
                max_attempts=3,
            )

        c = asyncio.run(go())
        assert c is not None
        assert c.should == "revised strategy"
        assert c.metadata["sim_attempts"] == 2
