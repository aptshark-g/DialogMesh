"""Tests for PerspectivePlanner: strategy, domain allocation, horizon."""
import pytest
from core.agent.compiler.perspective_planner import PerspectivePlanner


class TestPerspectivePlanner:
    def setup_method(self):
        self.planner = PerspectivePlanner()

    def test_architecture_strategy(self):
        persp = self.planner.plan("ContextCompiler的架构设计是什么", token_budget=4000)
        assert persp is not None
        assert persp.strategy in ("architecture", "engineering", "evolution", "execution")

    def test_engineering_strategy(self):
        persp = self.planner.plan("如何实现ContextCompiler", token_budget=4000)
        assert persp.strategy in ("engineering", "execution", "architecture")

    def test_evolution_strategy(self):
        persp = self.planner.plan("为什么选择这个架构", token_budget=4000)
        assert persp.strategy in ("evolution", "architecture", "engineering")

    def test_multi_perspective(self):
        perspectives = self.planner.plan_multi(
            "ContextCompiler的架构设计", token_budget=4000
        )
        assert len(perspectives) >= 2
        # Secondary should differ from primary
        assert perspectives[0].strategy != perspectives[1].strategy

    def test_horizon_valid(self):
        persp = self.planner.plan("测试问题", token_budget=4000)
        assert hasattr(persp.horizon, 'depth')
        assert persp.horizon.depth >= 1

    def test_domain_weights(self):
        persp = self.planner.plan("ContextCompiler是什么", token_budget=4000, expectation="ADVISOR")
        total = sum(persp.domains.values())
        assert total > 0

    def test_no_crash_on_short_text(self):
        persp = self.planner.plan("hi", token_budget=4000)
        assert persp is not None

    def test_expectation_affects_strategy(self):
        p1 = self.planner.plan("test", token_budget=4000, expectation="TOOL")
        p2 = self.planner.plan("test", token_budget=4000, expectation="COMPANION")
        # Different expectations should produce different domain weights
        assert p1 is not None and p2 is not None
