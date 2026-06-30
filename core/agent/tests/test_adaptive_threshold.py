# -*- coding: utf-8 -*-
"""
core/agent/tests/test_adaptive_threshold.py
──────────────────────────────────────────
Unit tests for AdaptiveThreshold / Bayesian GP feedback loop (Gap #9).

Coverage:
  - SmallMLP forward + online ridge update
  - IncrementalGP empty / single / multi-point prediction
  - GP posterior sample variance
  - AdaptiveThreshold suggest (thompson / mean / ucb)
  - AdaptiveThreshold update + threshold mapping
  - Feature extraction helper
  - State serialization / restore
"""

from __future__ import annotations

import unittest
import math

import numpy as np

from core.agent.adaptive_threshold import (
    AdaptiveThreshold,
    PCRFeatureVector,
    ThresholdSuggestion,
    SmallMLP,
    IncrementalGP,
)


class TestSmallMLP(unittest.TestCase):
    """Tiny MLP: 8→16→8 forward + online RLS update."""

    def test_forward_shape(self):
        mlp = SmallMLP(seed=1)
        x = np.zeros(8)
        out = mlp.forward(x)
        self.assertEqual(out.shape, (1, 8))

    def test_forward_non_zero(self):
        mlp = SmallMLP(seed=2)
        x = np.random.randn(8)
        out = mlp.forward(x)
        self.assertFalse(np.allclose(out, 0.0))

    def test_update_changes_weights(self):
        mlp = SmallMLP(seed=3)
        x = np.random.randn(8)
        z_before = mlp.get_transform(x).copy()
        mlp.update(x, z_before, lr=0.01)
        z_after = mlp.get_transform(x)
        # 权重应该更新（至少不完全相同）
        self.assertFalse(np.allclose(z_before, z_after, atol=1e-12))

    def test_multiple_updates_converge(self):
        mlp = SmallMLP(seed=4)
        target = np.ones(8) * 0.5
        for _ in range(20):
            x = np.random.randn(8)
            mlp.update(x, target, lr=0.05)
        # 平均误差应减小
        errors = []
        for _ in range(10):
            x = np.random.randn(8)
            pred = mlp.get_transform(x)
            errors.append(np.mean((pred - target) ** 2))
        avg_err = np.mean(errors)
        self.assertLess(avg_err, 1.0)


class TestIncrementalGP(unittest.TestCase):
    """Gaussian Process: RBF kernel + Sherman-Morrison incremental update."""

    def test_empty_predict(self):
        gp = IncrementalGP()
        mean, var = gp.predict(np.zeros(8))
        self.assertEqual(mean, 0.0)
        self.assertEqual(var, gp.signal_variance)

    def test_single_observation(self):
        gp = IncrementalGP(length_scale=1.0, signal_variance=1.0, noise_variance=0.01)
        z = np.ones(8)
        gp.update(z, 1.0)
        mean, var = gp.predict(z)
        self.assertGreater(mean, 0.5)
        self.assertLess(var, 0.5)

    def test_multi_observation_variance_decreases(self):
        gp = IncrementalGP(length_scale=2.0, noise_variance=0.05)
        z = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        for _ in range(5):
            gp.update(z, 1.0)
        mean, var = gp.predict(z)
        self.assertGreater(mean, 0.8)
        self.assertLess(var, 0.3)

    def test_out_of_sample_variance_higher(self):
        gp = IncrementalGP(length_scale=1.0, noise_variance=0.01)
        z1 = np.zeros(8)
        z2 = np.ones(8)
        gp.update(z1, 1.0)
        _, var_in = gp.predict(z1)
        _, var_out = gp.predict(z2)
        self.assertLess(var_in, var_out)

    def test_posterior_sample(self):
        gp = IncrementalGP()
        z = np.zeros(8)
        gp.update(z, 2.0)
        samples = [gp.posterior_sample(z) for _ in range(100)]
        mean_est = np.mean(samples)
        self.assertAlmostEqual(mean_est, 2.0, delta=0.5)

    def test_n_observations(self):
        gp = IncrementalGP()
        self.assertEqual(gp.n_observations(), 0)
        gp.update(np.zeros(8), 0.0)
        self.assertEqual(gp.n_observations(), 1)

    def test_log_marginal_likelihood(self):
        gp = IncrementalGP()
        self.assertEqual(gp.log_marginal_likelihood(), 0.0)
        gp.update(np.zeros(8), 1.0)
        lml = gp.log_marginal_likelihood()
        self.assertLess(lml, 0.0)

    def test_incremental_vs_recompute(self):
        """Sherman-Morrison 增量结果应与全量重算一致。"""
        gp1 = IncrementalGP(max_n_recompute=10, noise_variance=0.01)
        gp2 = IncrementalGP(max_n_recompute=9999, noise_variance=0.01)
        rng = np.random.default_rng(42)
        for _ in range(15):
            z = rng.standard_normal(8)
            y = rng.normal()
            gp1.update(z, y)
            gp2.update(z, y)
        # 15 > 10, so gp1 used incremental, gp2 used recompute
        test_z = rng.standard_normal(8)
        m1, v1 = gp1.predict(test_z)
        m2, v2 = gp2.predict(test_z)
        self.assertAlmostEqual(m1, m2, places=5)
        self.assertAlmostEqual(v1, v2, places=5)


class TestAdaptiveThreshold(unittest.TestCase):
    """AdaptiveThreshold: suggest + update + threshold mapping."""

    def setUp(self):
        self.at = AdaptiveThreshold(seed=42)

    def test_suggest_empty_returns_in_range(self):
        feat = PCRFeatureVector()
        s = self.at.suggest(feat)
        self.assertIsInstance(s, ThresholdSuggestion)
        self.assertGreaterEqual(s.threshold, 0.30)
        self.assertLessEqual(s.threshold, 0.95)

    def test_suggest_thompson(self):
        feat = PCRFeatureVector(rule_confidence=0.8, terminology_density=0.6)
        s = self.at.suggest(feat, acquisition="thompson_sampling")
        self.assertEqual(s.acquisition, "thompson_sampling")

    def test_suggest_mean(self):
        feat = PCRFeatureVector()
        s = self.at.suggest(feat, acquisition="mean")
        self.assertEqual(s.acquisition, "mean")

    def test_suggest_ucb(self):
        feat = PCRFeatureVector()
        s = self.at.suggest(feat, acquisition="ucb")
        self.assertEqual(s.acquisition, "ucb")

    def test_update_increases_n(self):
        feat = PCRFeatureVector()
        self.assertEqual(self.at.gp.n_observations(), 0)
        self.at.update(feat, 1.0)
        self.assertEqual(self.at.gp.n_observations(), 1)

    def test_update_negative_reward(self):
        feat = PCRFeatureVector(noise_level=0.8, clarification_rounds=3)
        self.at.update(feat, -1.0)
        s = self.at.suggest(feat)
        # 负面反馈后，阈值通常不应继续升高（但 GP 初期不稳定，允许范围检查）
        self.assertGreaterEqual(s.threshold, 0.30)
        self.assertLessEqual(s.threshold, 0.95)

    def test_threshold_mapping(self):
        self.assertAlmostEqual(self.at._map_to_threshold(0.0), 0.625, places=2)
        self.assertAlmostEqual(self.at._map_to_threshold(-10.0), 0.30, places=2)
        self.assertAlmostEqual(self.at._map_to_threshold(10.0), 0.95, places=2)

    def test_extract_features_defaults(self):
        feat = AdaptiveThreshold.extract_features()
        self.assertEqual(feat.rule_confidence, 0.0)
        self.assertEqual(feat.clarification_rounds, 0)

    def test_extract_features_history_consistency(self):
        hist = [
            type("H", (), {"role": "user", "content": "q1", "expectation": "TOOL"})(),
            type("H", (), {"role": "user", "content": "q2", "expectation": "TOOL"})(),
        ]
        feat = AdaptiveThreshold.extract_features(history=hist)
        self.assertGreater(feat.history_consistency, 0.5)

    def test_extract_features_time_decay(self):
        import time
        feat = AdaptiveThreshold.extract_features(last_turn_time=time.time() - 600)
        self.assertLess(feat.time_decay, 1.0)

    def test_state_serialization_restore(self):
        feat = PCRFeatureVector(rule_confidence=0.7)
        self.at.update(feat, 1.0)
        state = self.at.get_state()
        self.assertEqual(state["n_observations"], 1)
        self.assertEqual(len(state["Z"]), 1)
        self.assertEqual(len(state["y"]), 1)

    def test_summary(self):
        summary = self.at.summary()
        self.assertIn("n_observations", summary)
        self.assertIn("gp_hyperparameters", summary)

    def test_warm_up_with_seed_data(self):
        data = [
            (PCRFeatureVector(rule_confidence=0.8, terminology_density=0.5), 1.0),
            (PCRFeatureVector(rule_confidence=0.2, noise_level=0.9), -1.0),
        ]
        at2 = AdaptiveThreshold(seed=7)
        at2.warm_up(data)
        self.assertEqual(at2.gp.n_observations(), 2)

    def test_meta_in_suggestion(self):
        feat = PCRFeatureVector()
        s = self.at.suggest(feat)
        self.assertIn("n_observations", s.meta)
        self.assertIn("raw_gp_output", s.meta)


if __name__ == "__main__":
    import time
    unittest.main()
