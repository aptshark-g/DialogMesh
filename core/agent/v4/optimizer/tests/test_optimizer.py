"""Tests for BayesianOptimizer and FeedbackSignal."""
from __future__ import annotations
import pytest
import numpy as np

from core.agent.v4.optimizer.signals import FeedbackSignal
from core.agent.v4.optimizer.optimizer import BayesianOptimizer, ParameterBounds


class TestFeedbackSignal:

    def test_composite_equal_weights(self):
        s = FeedbackSignal()
        s.explicit = 1.0
        s.implicit = 0.5
        s.task = 0.0
        s.convergence = -0.5
        s.diversity = -1.0
        expected = (0.2*1.0 + 0.2*0.5 + 0.2*0.0 + 0.2*(-0.5) + 0.2*(-1.0))
        assert abs(s.composite() - expected) < 0.01

    def test_composite_clamped(self):
        s = FeedbackSignal()
        s.explicit = 2.0
        assert s.composite() <= 1.0

    def test_with_explicit_correction(self):
        s = FeedbackSignal().with_explicit(correction=True, confidence=0.8)
        assert s.explicit == -0.8

    def test_with_explicit_confirm(self):
        s = FeedbackSignal().with_explicit(correction=False, confidence=0.9)
        assert s.explicit == 0.9

    def test_with_task_success(self):
        s = FeedbackSignal().with_task(success=True, duration_sec=60)
        assert s.task > 0.5

    def test_with_task_failure(self):
        s = FeedbackSignal().with_task(success=False)
        assert s.task < 0

    def test_with_convergence_fast(self):
        s = FeedbackSignal().with_convergence(rounds_to_converge=2, total_rounds=10)
        assert s.convergence > 0.5

    def test_with_convergence_slow(self):
        s = FeedbackSignal().with_convergence(rounds_to_converge=8, total_rounds=10)
        assert s.convergence < 0

    def test_with_convergence_no_converge(self):
        s = FeedbackSignal().with_convergence(rounds_to_converge=0, total_rounds=0)
        assert s.convergence < 0

    def test_with_diversity_healthy(self):
        s = FeedbackSignal().with_diversity(n_hypotheses=5, n_domains=3)
        assert s.diversity > 0

    def test_with_diversity_too_few(self):
        s = FeedbackSignal().with_diversity(n_hypotheses=1, n_domains=1)
        assert s.diversity < 0

    def test_set_weights(self):
        s = FeedbackSignal()
        s.set_weights(explicit=0.5, implicit=0.5, task=0.0, convergence=0.0, diversity=0.0)
        assert abs(s.weights["explicit"] - 0.5) < 0.01
        assert abs(s.weights["implicit"] - 0.5) < 0.01

    def test_to_dict(self):
        s = FeedbackSignal().with_explicit(correction=False)
        d = s.to_dict()
        assert "composite" in d
        assert "weights" in d


class TestBayesianOptimizer:

    def test_init(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds)
        assert opt.n_observations == 0
        assert opt.best_reward == -float("inf")

    def test_observe_and_suggest_random(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds, min_observations=5)
        opt.observe({"p1": 3.0}, reward=0.5)
        suggestion = opt.suggest()
        assert 0.0 <= suggestion["p1"] <= 10.0

    def test_observe_updates_best(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds)
        opt.observe({"p1": 3.0}, reward=0.5)
        assert opt.best_reward == 0.5
        assert opt.best_params == {"p1": 3.0}

        opt.observe({"p1": 7.0}, reward=0.8)
        assert opt.best_reward == 0.8
        assert opt.best_params == {"p1": 7.0}

    def test_suggest_ei(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds, min_observations=2)
        for _ in range(5):
            opt.observe({"p1": 8.0 + np.random.normal(0, 0.5)}, reward=0.8 + np.random.normal(0, 0.1))
            opt.observe({"p1": 2.0 + np.random.normal(0, 0.5)}, reward=0.2 + np.random.normal(0, 0.1))
        suggestion = opt.suggest(strategy="ei")
        assert suggestion["p1"] > 5.0

    def test_suggest_ucb(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds, min_observations=2)
        opt.observe({"p1": 5.0}, reward=0.5)
        opt.observe({"p1": 7.0}, reward=0.7)
        suggestion = opt.suggest(strategy="ucb")
        assert 0.0 <= suggestion["p1"] <= 10.0

    def test_multi_param(self):
        bounds = {
            "min_support": ParameterBounds("min_support", 3, 15, 8),
            "max_conflict": ParameterBounds("max_conflict", 1, 8, 3),
        }
        opt = BayesianOptimizer(bounds, min_observations=2)
        for _ in range(4):
            opt.observe({"min_support": 10, "max_conflict": 2}, reward=0.8)
            opt.observe({"min_support": 5, "max_conflict": 6}, reward=0.3)
        suggestion = opt.suggest()
        assert 3 <= suggestion["min_support"] <= 15
        assert 1 <= suggestion["max_conflict"] <= 8

    def test_clip(self):
        b = ParameterBounds("p1", 0.0, 10.0, 5.0)
        assert b.clip(15.0) == 10.0
        assert b.clip(-5.0) == 0.0
        assert b.clip(5.0) == 5.0

    def test_normalize_roundtrip(self):
        b = ParameterBounds("p1", 0.0, 10.0, 5.0)
        for v in [0.0, 5.0, 10.0, 3.14, 7.77]:
            norm = b.normalize(v)
            back = b.denormalize(norm)
            assert abs(back - b.clip(v)) < 0.01

    def test_stats(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds)
        opt.observe({"p1": 5.0}, reward=0.5)
        stats = opt.stats()
        assert stats["n_observations"] == 1
        assert stats["best_reward"] == 0.5
        assert "param_stats" in stats

    def test_get_records(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds)
        for i in range(5):
            opt.observe({"p1": float(i)}, reward=0.1 * i)
        records = opt.get_records(limit=3)
        assert len(records) == 3
        assert records[-1].reward == 0.4

    def test_suggest_single(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds, min_observations=2)
        opt.observe({"p1": 5.0}, reward=0.5)
        opt.observe({"p1": 7.0}, reward=0.7)
        v = opt.suggest_single("p1", strategy="mean")
        assert 0.0 <= v <= 10.0

    def test_unknown_param(self):
        bounds = {"p1": ParameterBounds("p1", 0.0, 10.0, 5.0)}
        opt = BayesianOptimizer(bounds)
        with pytest.raises(KeyError):
            opt.suggest_single("unknown")
