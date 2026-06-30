# -*- coding: utf-8 -*-
"""
core/agent/adaptive_threshold.py
────────────────────────────────
Bayesian adaptive threshold for PCR feedback loop (Architecture Gap #9).

Purpose:
  Continuously learn the optimal PCR confidence thresholds from user feedback
  using a Gaussian Process (GP) regressor with a small MLP feature
  transformer. The GP is updated incrementally via Sherman-Morrison so
  that every new feedback sample costs O(n²) instead of O(n³) matrix
  inversion. Exploration is driven by Thompson Sampling.

8-dimensional feature space:
  1. rule_confidence     – raw rule-matching confidence [0,1]
  2. history_consistency – Jaccard similarity with previous turn expectations
  3. query_length_norm   – normalised token count of the query
  4. terminology_density – ratio of domain-specific terms (statistical density)
  5. noise_level         – PCR noise estimator output [0,1]
  6. clarification_rounds – how many clarifications have occurred
  7. time_decay          – elapsed seconds since last user turn (exponential)
  8. user_feedback_signal – explicit or implicit feedback score [-1,+1]

Architecture:
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  8-D input   │────→│  Small MLP   │────→│  GP Kernel   │
  │  features    │     │  transform   │     │  prediction  │
  └──────────────┘     └──────────────┘     └──────────────┘
                              │                    │
                              ▼                    ▼
                       ┌──────────────┐     ┌──────────────┐
                       │  ReLU + Lin  │     │ Thompson     │
                       │  8→16→8      │     │ Sampling     │
                       └──────────────┘     └──────────────┘

Integration:
  • Instantiated by PCRLifecycleManager during warm-up.
  • After each evaluate() call, the manager extracts the 8-D feature vector
    and calls AdaptiveThreshold.update() with the (implicit or explicit)
    user feedback reward.
  • The next evaluate() uses AdaptiveThreshold.suggest_threshold() to set
    the parser confidence threshold dynamically.

Dependencies:
  • numpy (only)
  • No PyTorch / scikit-learn to keep the dependency footprint minimal.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("adaptive_threshold")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class PCRFeatureVector:
    """8-dimensional feature vector for the GP."""
    rule_confidence: float = 0.0
    history_consistency: float = 0.0
    query_length_norm: float = 0.0
    terminology_density: float = 0.0
    noise_level: float = 0.0
    clarification_rounds: int = 0
    time_decay: float = 1.0
    user_feedback_signal: float = 0.0

    def to_array(self) -> np.ndarray:
        return np.array([
            self.rule_confidence,
            self.history_consistency,
            self.query_length_norm,
            self.terminology_density,
            self.noise_level,
            float(self.clarification_rounds) / 10.0,  # normalise
            self.time_decay,
            self.user_feedback_signal,
        ], dtype=np.float64)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PCRFeatureVector":
        return cls(
            rule_confidence=float(d.get("rule_confidence", 0.0)),
            history_consistency=float(d.get("history_consistency", 0.0)),
            query_length_norm=float(d.get("query_length_norm", 0.0)),
            terminology_density=float(d.get("terminology_density", 0.0)),
            noise_level=float(d.get("noise_level", 0.0)),
            clarification_rounds=int(d.get("clarification_rounds", 0)),
            time_decay=float(d.get("time_decay", 1.0)),
            user_feedback_signal=float(d.get("user_feedback_signal", 0.0)),
        )


@dataclass(frozen=False)
class ThresholdSuggestion:
    """Output of the adaptive threshold suggestion."""
    threshold: float = 0.5
    mean: float = 0.0
    variance: float = 0.0
    acquisition: str = "thompson_sampling"
    meta: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Small MLP Feature Transformer
# ═══════════════════════════════════════════════════════════════════════════════

class SmallMLP:
    """
    Tiny fully-connected network: 8 → 16 → 8.
    No backpropagation; weights are fixed random projections + learned
    output layer via closed-form ridge regression (updated online).
    """

    def __init__(self, in_dim: int = 8, hidden_dim: int = 16, out_dim: int = 8,
                 ridge_lambda: float = 1e-3, seed: int = 42):
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        self.out_dim = out_dim
        self.ridge_lambda = ridge_lambda

        rng = np.random.default_rng(seed)
        # Fixed random projection (like an untrained bottleneck)
        self.W1 = rng.normal(0.0, 1.0 / math.sqrt(in_dim), (in_dim, hidden_dim))
        self.b1 = np.zeros(hidden_dim)

        # Learnable output layer — updated via ridge regression
        self.W2 = rng.normal(0.0, 1.0 / math.sqrt(hidden_dim), (hidden_dim, out_dim))
        self.b2 = np.zeros(out_dim)

        # Ridge regression accumulators
        self._A = ridge_lambda * np.eye(hidden_dim)  # X^T X + λI
        self._B = np.zeros((hidden_dim, out_dim))    # X^T Y
        self._n = 0

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass: x → ReLU(x @ W1 + b1) @ W2 + b2."""
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        h = np.maximum(0.0, x @ self.W1 + self.b1)  # ReLU
        return h @ self.W2 + self.b2

    def update(self, x: np.ndarray, target: np.ndarray, lr: float = 0.01) -> None:
        """
        Online update of W2 via recursive least-squares (RLS) ridge regression.
        This is equivalent to a rank-1 Sherman-Morrison update on the
        covariance matrix of hidden features.
        """
        x = np.asarray(x, dtype=np.float64).reshape(1, -1)
        target = np.asarray(target, dtype=np.float64).reshape(1, -1)

        # Hidden representation
        h = np.maximum(0.0, x @ self.W1 + self.b1)  # (1, hidden)

        # Recursive least-squares update
        # A_{n+1} = A_n + h^T h
        # B_{n+1} = B_n + h^T target
        self._A += h.T @ h
        self._B += h.T @ target
        self._n += 1

        # W2 = A^{-1} B (ridge solution)
        try:
            A_inv = np.linalg.inv(self._A)
            self.W2 = A_inv @ self._B
        except np.linalg.LinAlgError:
            logger.warning("MLP ridge update failed (singular matrix); skipping.")

        # Update bias with momentum
        pred = h @ self.W2 + self.b2
        err = target - pred
        self.b2 += lr * err.mean(axis=0)

    def get_transform(self, x: np.ndarray) -> np.ndarray:
        """Return the output of the MLP (the transformed feature)."""
        return self.forward(x).flatten()


# ═══════════════════════════════════════════════════════════════════════════════
# Gaussian Process with Sherman-Morrison Incremental Update
# ═══════════════════════════════════════════════════════════════════════════════

class IncrementalGP:
    """
    Gaussian Process regressor with RBF kernel, updated incrementally.

    Key implementation:
      • K_inv is maintained via the Sherman-Morrison-Woodbury formula
        when a new data point arrives.
      • This avoids O(n³) matrix inversion after every observation.
      • Predictive mean and variance use K_inv directly.
    """

    def __init__(self, length_scale: float = 1.0, signal_variance: float = 1.0,
                 noise_variance: float = 0.01, max_n_recompute: int = 50):
        self.length_scale = length_scale
        self.signal_variance = signal_variance
        self.noise_variance = noise_variance
        self.max_n_recompute = max_n_recompute

        # Observations (transformed features)
        self.Z: List[np.ndarray] = []
        self.y: List[float] = []

        # Cached inverse covariance matrix
        self.K_inv: Optional[np.ndarray] = None
        self._n: int = 0

    # ── Kernel ──────────────────────────────────────────────────────────────

    def _kernel(self, z1: np.ndarray, z2: np.ndarray) -> float:
        """RBF (squared-exponential) kernel."""
        diff = z1 - z2
        sq_dist = np.dot(diff, diff)
        return self.signal_variance * math.exp(-0.5 * sq_dist / (self.length_scale ** 2))

    def _kernel_vec(self, z: np.ndarray, Z: List[np.ndarray]) -> np.ndarray:
        """Compute kernel vector k(z, Z) for a list of points."""
        return np.array([self._kernel(z, zi) for zi in Z], dtype=np.float64)

    # ── Incremental update ────────────────────────────────────────────────────

    def update(self, z: np.ndarray, reward: float) -> None:
        """
        Add a new observation and update K_inv incrementally.

        Algorithm (Sherman-Morrison for rank-1 block update):
          Let K_n  = n×n covariance matrix (with noise on diagonal)
          Let k    = [k(z, z_1), ..., k(z, z_n)]^T
          Let k_nn = k(z, z) + noise_variance

          K_{n+1} = [ K_n   k
                      k^T  k_nn ]

          Using block-matrix inversion (Woodbury/Sherman-Morrison):
          S  = k_nn - k^T K_n^{-1} k      (Schur complement, scalar)
          K_{n+1}^{-1} = [
              K_n^{-1} + K_n^{-1} k S^{-1} k^T K_n^{-1}   ,  -K_n^{-1} k S^{-1}
              -S^{-1} k^T K_n^{-1}                        ,   S^{-1}
          ]
        """
        z = np.asarray(z, dtype=np.float64).flatten()
        self.Z.append(z)
        self.y.append(reward)
        self._n += 1

        if self._n <= self.max_n_recompute or self.K_inv is None:
            # Recompute from scratch for small n or first time
            self._recompute_K_inv()
        else:
            # Incremental update
            self._incremental_update(z)

    def _recompute_K_inv(self) -> None:
        """Full O(n³) inversion — used when n is small or as fallback."""
        n = self._n
        K = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(n):
                K[i, j] = self._kernel(self.Z[i], self.Z[j])
        K += self.noise_variance * np.eye(n)
        try:
            self.K_inv = np.linalg.inv(K)
        except np.linalg.LinAlgError:
            logger.error("K inversion failed; adding jitter.")
            K += 1e-5 * np.eye(n)
            self.K_inv = np.linalg.inv(K)

    def _incremental_update(self, z_new: np.ndarray) -> None:
        """Sherman-Morrison block update: O(n²) instead of O(n³)."""
        n = self._n - 1  # old size
        k_vec = self._kernel_vec(z_new, self.Z[:n])  # (n,)
        k_nn = self._kernel(z_new, z_new) + self.noise_variance

        # Schur complement S = k_nn - k^T K_inv k
        A_inv = self.K_inv  # (n, n)
        v = A_inv @ k_vec  # (n,)
        S = k_nn - np.dot(k_vec, v)

        if S < 1e-12:
            logger.warning("Near-zero Schur complement (S=%.3e); adding jitter.", S)
            S += 1e-6

        S_inv = 1.0 / S

        # Block matrix inversion
        top_left = A_inv + S_inv * np.outer(v, v)
        top_right = -S_inv * v.reshape(-1, 1)
        bottom_left = -S_inv * v.reshape(1, -1)
        bottom_right = np.array([[S_inv]])

        self.K_inv = np.block([
            [top_left, top_right],
            [bottom_left, bottom_right]
        ])

    # ── Prediction ──────────────────────────────────────────────────────────

    def predict(self, z: np.ndarray) -> Tuple[float, float]:
        """
        Predictive mean and variance at point z.

        Returns:
            (mean, variance)  where variance >= 0
        """
        z = np.asarray(z, dtype=np.float64).flatten()

        if self._n == 0:
            return 0.0, self.signal_variance

        k_star = self._kernel_vec(z, self.Z)  # (n,)

        # Mean = k_star^T K_inv y
        alpha = self.K_inv @ np.array(self.y, dtype=np.float64)
        mean = float(np.dot(k_star, alpha))

        # Variance = k(z,z) - k_star^T K_inv k_star
        v = self.K_inv @ k_star
        k_zz = self._kernel(z, z)
        variance = float(k_zz - np.dot(k_star, v))
        variance = max(0.0, variance)

        return mean, variance

    def posterior_sample(self, z: np.ndarray) -> float:
        """Draw a single sample from the posterior at z."""
        mean, var = self.predict(z)
        if var <= 1e-12:
            return mean
        return float(np.random.normal(mean, math.sqrt(var)))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def n_observations(self) -> int:
        return self._n

    def log_marginal_likelihood(self) -> float:
        """Compute log p(y | X) for hyperparameter tuning (if needed)."""
        if self._n == 0 or self.K_inv is None:
            return 0.0
        y = np.array(self.y, dtype=np.float64)
        alpha = self.K_inv @ y
        # log p(y) = -0.5 y^T alpha - 0.5 log|K| - n/2 log(2π)
        # Using log|K| = -log|K_inv| (since det(K) = 1/det(K_inv))
        sign, logdet = np.linalg.slogdet(self.K_inv)
        if sign <= 0:
            return -1e9
        return -0.5 * np.dot(y, alpha) + 0.5 * logdet - 0.5 * self._n * math.log(2 * math.pi)


# ═══════════════════════════════════════════════════════════════════════════════
# Adaptive Threshold (main API)
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveThreshold:
    """
    Bayesian adaptive threshold for PCR feedback loop.

    Usage:
        at = AdaptiveThreshold()
        at.warm_up()

        # At each turn
        feat = PCRFeatureVector(rule_confidence=0.8, noise_level=0.2, ...)
        suggestion = at.suggest(feat)
        parser.set_threshold(suggestion.threshold)

        # After observing user feedback (implicit or explicit)
        reward = compute_reward(user_turn_result)  # e.g. +1 if success, -1 if clarification
        at.update(feat, reward)
    """

    def __init__(self, seed: int = 42,
                 fast_path_mode: str = "adaptive",
                 fast_path_entity_threshold: float = 0.85,
                 fast_path_intent_threshold: float = 0.40):
        """
        Args:
            seed: Random seed for reproducibility.
            fast_path_mode: "adaptive" (GP动态调控) | "custom" (固定) |
                            "conservative" (entity=0.95, intent=0.6) |
                            "aggressive" (entity=0.75, intent=0.3).
            fast_path_entity_threshold: 自定义模式下的实体阈值。
            fast_path_intent_threshold: 自定义模式下的意图阈值。
        """
        self.mlp = SmallMLP(in_dim=8, hidden_dim=16, out_dim=8, seed=seed)
        self.gp = IncrementalGP(
            length_scale=1.0,
            signal_variance=1.0,
            noise_variance=0.05,
            max_n_recompute=50,
        )
        self._seed = seed
        self._rng = np.random.default_rng(seed)

        # Default threshold (will be refined by GP)
        self._default_threshold = 0.5

        # Fast Path 阈值配置
        self._fast_path_mode = fast_path_mode
        self._fast_path_entity_base = fast_path_entity_threshold
        self._fast_path_intent_base = fast_path_intent_threshold
        self._fast_path_entity_current = fast_path_entity_threshold
        self._fast_path_intent_current = fast_path_intent_threshold

        # Track last suggested threshold for each feature (for debugging)
        self._history: List[Dict[str, Any]] = []

        logger.info(
            "AdaptiveThreshold: mode=%s, entity_base=%.2f, intent_base=%.2f",
            fast_path_mode, fast_path_entity_threshold, fast_path_intent_threshold,
        )

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def warm_up(self, initial_data: Optional[List[Tuple[PCRFeatureVector, float]]] = None) -> None:
        """
        Optional warm-up with seed data (e.g. from past sessions).
        Each tuple is (feature_vector, reward).
        """
        if initial_data:
            for feat, reward in initial_data:
                self.update(feat, reward)
            logger.info("Warm-up complete: %d seed observations.", len(initial_data))

    def shutdown(self) -> None:
        """Idempotent shutdown."""
        self._history.clear()

    # ── Core API ────────────────────────────────────────────────────────────

    def update(self, feature: PCRFeatureVector, reward: float) -> None:
        """
        Incorporate a new observation (feature, reward) into the model.

        Reward convention:
          +1.0  → user succeeded without clarification (excellent)
          +0.5  → user succeeded with minor clarification
           0.0  → neutral / no feedback
          -0.5  → user needed significant clarification
          -1.0  → parser failed or user complained
        """
        x = feature.to_array()
        z = self.mlp.get_transform(x)
        self.gp.update(z, reward)
        # Also update the MLP output layer (online ridge regression)
        self.mlp.update(x, z, lr=0.01)

        self._history.append({
            "feature": feature.to_array().tolist(),
            "reward": reward,
            "timestamp": time.time(),
        })

        if len(self._history) % 10 == 0:
            logger.info(
                "AdaptiveThreshold updated: n=%d, last_reward=%.2f",
                self.gp.n_observations(), reward,
            )

    def suggest(self, feature: PCRFeatureVector,
                acquisition: str = "thompson_sampling") -> ThresholdSuggestion:
        """
        Suggest a parser confidence threshold for the given feature vector.

        acquisition strategies:
          "thompson_sampling"  – sample from posterior (default, balances explore/exploit)
          "mean"               – use predictive mean (pure exploitation)
          "ucb"                – upper confidence bound (mean + 2*sqrt(var))
        """
        x = feature.to_array()
        z = self.mlp.get_transform(x)
        mean, var = self.gp.predict(z)

        if acquisition == "thompson_sampling":
            raw = self.gp.posterior_sample(z)
        elif acquisition == "mean":
            raw = mean
        elif acquisition == "ucb":
            raw = mean + 2.0 * math.sqrt(var)
        else:
            raw = mean

        # Map raw GP output to [0.3, 0.95] threshold range
        # raw is expected to be roughly in [-1, 1] after some training
        threshold = self._map_to_threshold(raw)

        return ThresholdSuggestion(
            threshold=threshold,
            mean=mean,
            variance=var,
            acquisition=acquisition,
            meta={
                "raw_gp_output": raw,
                "n_observations": self.gp.n_observations(),
                "feature": feature.to_array().tolist(),
            },
        )

    def suggest_fast_path(self, feature: PCRFeatureVector) -> Tuple[float, float]:
        """
        返回 Fast Path 阈值 (entity_threshold, intent_threshold)。
        模式决定调控策略：
          adaptive: 使用 GP 动态调控（基于当前特征微调）
          custom: 使用初始化传入的固定值
          conservative: 固定高阈值（0.95, 0.6）
          aggressive: 固定低阈值（0.75, 0.3）
        """
        if self._fast_path_mode == "custom":
            return self._fast_path_entity_base, self._fast_path_intent_base
        if self._fast_path_mode == "conservative":
            return 0.95, 0.60
        if self._fast_path_mode == "aggressive":
            return 0.75, 0.30

        # adaptive: 使用 GP 微调基础阈值
        suggestion = self.suggest(feature, acquisition="mean")
        # 将主阈值映射到 fast path 偏移
        # 主阈值高（0.8+）→ fast path 更严格（+0.05）
        # 主阈值低（0.4-）→ fast path 更宽松（-0.05）
        offset = (suggestion.threshold - 0.5) * 0.10
        entity = min(0.98, max(0.70, self._fast_path_entity_base + offset))
        intent = min(0.80, max(0.20, self._fast_path_intent_base + offset))
        self._fast_path_entity_current = entity
        self._fast_path_intent_current = intent
        return entity, intent

    def _map_to_threshold(self, raw: float) -> float:
        """Map raw GP output to a valid threshold in [0.30, 0.95]."""
        # Sigmoid-like mapping: 0.3 + 0.65 * (1 + tanh(raw)) / 2
        mapped = 0.30 + 0.65 * (1.0 + math.tanh(raw)) / 2.0
        return round(min(0.95, max(0.30, mapped)), 4)

    # ── Feature extraction helpers (convenience) ────────────────────────────

    @staticmethod
    def extract_features(
        rule_confidence: float = 0.0,
        history: Optional[List[Any]] = None,
        query: str = "",
        terminology_density: float = 0.0,
        noise_level: float = 0.0,
        clarification_count: int = 0,
        last_turn_time: Optional[float] = None,
        user_feedback: float = 0.0,
    ) -> PCRFeatureVector:
        """
        Convenience factory: build a feature vector from raw observables.
        """
        # History consistency: Jaccard of last two expectations
        history_consistency = 0.0
        if history and len(history) >= 2:
            last = [h for h in history if getattr(h, "role", "") == "user"]
            if len(last) >= 2:
                # Simple heuristic: if expectations match, consistency is high
                e1 = getattr(last[-1], "expectation", "UNKNOWN")
                e2 = getattr(last[-2], "expectation", "UNKNOWN")
                history_consistency = 1.0 if e1 == e2 and e1 != "UNKNOWN" else 0.3

        # Query length normalised
        tokens = len(query.split()) if query else 0
        query_length_norm = min(1.0, tokens / 50.0)

        # Time decay (exponential)
        time_decay = 1.0
        if last_turn_time is not None:
            elapsed = time.time() - last_turn_time
            time_decay = math.exp(-elapsed / 300.0)  # 5-minute half-life

        return PCRFeatureVector(
            rule_confidence=rule_confidence,
            history_consistency=history_consistency,
            query_length_norm=query_length_norm,
            terminology_density=terminology_density,
            noise_level=noise_level,
            clarification_rounds=clarification_count,
            time_decay=time_decay,
            user_feedback_signal=user_feedback,
        )

    # ── Diagnostics / Persistence ─────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Serialize state for checkpointing (not weights, just data)."""
        return {
            "n_observations": self.gp.n_observations(),
            "Z": [z.tolist() for z in self.gp.Z],
            "y": self.gp.y,
            "history_length": len(self._history),
            "default_threshold": self._default_threshold,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore observations from a checkpoint."""
        Z_data = state.get("Z", [])
        y_data = state.get("y", [])
        for z_list, reward in zip(Z_data, y_data):
            z = np.array(z_list, dtype=np.float64)
            self.gp.update(z, reward)
        logger.info("Restored %d observations from checkpoint.", len(y_data))

    def summary(self) -> Dict[str, Any]:
        """Human-readable summary for telemetry."""
        return {
            "n_observations": self.gp.n_observations(),
            "log_marginal_likelihood": self.gp.log_marginal_likelihood(),
            "history_length": len(self._history),
            "default_threshold": self._default_threshold,
            "gp_hyperparameters": {
                "length_scale": self.gp.length_scale,
                "signal_variance": self.gp.signal_variance,
                "noise_variance": self.gp.noise_variance,
            },
        }
