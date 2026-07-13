"""BayesianOptimizer: 多参数高斯过程优化器。

核心设计：
  - 每个参数独立 GP（忽略参数间耦合，降低维度诅咒）
  - IncrementalGP 增量更新（O(n²) Sherman-Morrison）
  - EI (Expected Improvement) acquisition
  - 参数空间约束：每个参数有 [min, max] 安全区间

文献：
  Snoek et al. (2012) "Practical Bayesian Optimization of Machine Learning Algorithms"
  Frazier (2018) "A Tutorial on Bayesian Optimization"
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.agent.v3_common.adaptive_threshold import IncrementalGP


@dataclass
class ParameterBounds:
    """单个参数的优化边界。"""
    name: str
    min: float
    max: float
    current: float
    # GP 超参数（可共享或独立）
    length_scale: float = 1.0
    noise_variance: float = 0.01

    def clip(self, value: float) -> float:
        return max(self.min, min(self.max, value))

    def normalize(self, value: float) -> float:
        """将参数值归一化到 [-1, 1] 供 GP 使用。"""
        return 2.0 * (self.clip(value) - self.min) / max(1e-9, self.max - self.min) - 1.0

    def denormalize(self, norm: float) -> float:
        """将 GP 输出 [-1, 1] 还原为参数值。"""
        return self.clip(self.min + (norm + 1.0) / 2.0 * (self.max - self.min))


@dataclass
class OptimizationRecord:
    """单次参数评估记录。"""
    params: Dict[str, float]
    reward: float
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class BayesianOptimizer:
    """多参数贝叶斯优化器。

    Usage:
        # 1. 定义要优化的参数及其边界
        bounds = {
            "min_support": ParameterBounds("min_support", 3, 15, 8),
            "max_conflict": ParameterBounds("max_conflict", 1, 8, 3),
            ...
        }

        # 2. 创建优化器
        opt = BayesianOptimizer(bounds)

        # 3. 每次评估后更新
        opt.observe({"min_support": 8, "max_conflict": 3}, reward=0.7)

        # 4. 获取下一组建议参数
        suggestion = opt.suggest()
        # → {"min_support": 9.2, "max_conflict": 2.1, ...}
    """

    def __init__(self, bounds: Dict[str, ParameterBounds],
                 xi: float = 0.01,  # EI 探索参数
                 min_observations: int = 3):
        self._bounds = dict(bounds)
        self._xi = xi
        self._min_obs = min_observations

        # 每个参数一个独立 GP
        self._gps: Dict[str, IncrementalGP] = {}
        for name, b in bounds.items():
            self._gps[name] = IncrementalGP(
                length_scale=b.length_scale,
                signal_variance=1.0,
                noise_variance=b.noise_variance,
                max_n_recompute=30,
            )

        self._records: List[OptimizationRecord] = []
        self._best_reward = -float("inf")
        self._best_params: Optional[Dict[str, float]] = None
        self._n_obs = 0

    # ── Core API ──────────────────────────────────────────────────────

    def observe(self, params: Dict[str, float], reward: float,
                metadata: dict = None) -> None:
        """记录一次参数评估结果。

        Args:
            params: 当前参数配置 {name: value}
            reward: 反馈信号复合值 [-1, +1]
            metadata: 可选审计信息
        """
        # 更新最佳记录
        if reward > self._best_reward:
            self._best_reward = reward
            self._best_params = dict(params)

        # 为每个参数更新 GP
        # 关键：每个 GP 的输入是该参数的归一化值，输出是 reward
        for name, value in params.items():
            if name not in self._bounds:
                continue
            b = self._bounds[name]
            z = np.array([b.normalize(value)], dtype=np.float64)
            self._gps[name].update(z, reward)

        self._records.append(OptimizationRecord(
            params=dict(params),
            reward=reward,
            metadata=metadata or {},
        ))
        self._n_obs += 1

    def suggest(self, strategy: str = "ei") -> Dict[str, float]:
        """建议下一组参数配置。

        Args:
            strategy: "ei" (Expected Improvement) | "mean" | "ucb"

        Returns:
            参数配置字典 {name: value}
        """
        result = {}
        for name, b in self._bounds.items():
            gp = self._gps[name]
            if gp.n_observations() < self._min_obs:
                # 观测不足 → 随机探索
                result[name] = self._random_sample(name)
                continue

            # 在参数空间上搜索最优 acquisition
            best_x = b.current
            best_acq = -float("inf")

            # 网格搜索 + 当前值邻域细化
            candidates = self._candidate_grid(name, n=21)
            for x in candidates:
                z = np.array([b.normalize(x)], dtype=np.float64)
                acq = self._acquisition(gp, z, strategy)
                if acq > best_acq:
                    best_acq = acq
                    best_x = x

            result[name] = b.clip(best_x)

        return result

    def suggest_single(self, name: str, strategy: str = "ei") -> float:
        """建议单个参数的下一值。"""
        if name not in self._bounds:
            raise KeyError(f"Unknown parameter: {name}")
        return self.suggest(strategy).get(name, self._bounds[name].current)

    # ── Acquisition Functions ─────────────────────────────────────────

    def _acquisition(self, gp: IncrementalGP, z: np.ndarray,
                     strategy: str) -> float:
        """计算 acquisition function 值。"""
        mean, var = gp.predict(z)
        std = math.sqrt(max(0.0, var))

        if strategy == "mean":
            return mean

        if strategy == "ucb":
            # Upper Confidence Bound: mean + kappa * std
            return mean + 2.0 * std

        # Expected Improvement (default)
        # EI(x) = E[max(0, f(x) - f_best)]
        if std < 1e-9:
            return 0.0 if mean <= self._best_reward else (mean - self._best_reward)

        # 标准化
        z_score = (mean - self._best_reward - self._xi) / std
        # EI = (mean - f_best - xi) * Phi(Z) + std * phi(Z)
        # 使用近似：
        from math import erf, sqrt, exp, pi
        Phi = 0.5 * (1 + erf(z_score / sqrt(2)))  # 标准正态 CDF
        phi = exp(-0.5 * z_score * z_score) / sqrt(2 * pi)  # 标准正态 PDF
        ei = (mean - self._best_reward - self._xi) * Phi + std * phi
        return ei

    # ── Helpers ───────────────────────────────────────────────────────

    def _random_sample(self, name: str) -> float:
        """在参数边界内随机采样。"""
        b = self._bounds[name]
        return b.min + (b.max - b.min) * np.random.random()

    def _candidate_grid(self, name: str, n: int = 21) -> List[float]:
        """生成候选点网格（均匀 + 当前值邻域）。"""
        b = self._bounds[name]
        # 均匀网格
        uniform = [b.min + (b.max - b.min) * i / (n - 1) for i in range(n)]
        # 当前值邻域细化
        neighborhood = []
        step = (b.max - b.min) / (n - 1)
        for delta in [-2 * step, -step, 0, step, 2 * step]:
            neighborhood.append(b.clip(b.current + delta))
        return list(dict.fromkeys(uniform + neighborhood))  # 去重保序

    # ── Accessors ─────────────────────────────────────────────────────

    @property
    def best_params(self) -> Optional[Dict[str, float]]:
        return self._best_params

    @property
    def best_reward(self) -> float:
        return self._best_reward

    @property
    def n_observations(self) -> int:
        return self._n_obs

    def stats(self) -> dict:
        """诊断统计。"""
        return {
            "n_observations": self._n_obs,
            "best_reward": self._best_reward,
            "best_params": self._best_params,
            "param_stats": {
                name: {
                    "gp_obs": gp.n_observations(),
                    "current": b.current,
                    "bounds": [b.min, b.max],
                }
                for name, (gp, b) in {
                    name: (self._gps[name], self._bounds[name])
                    for name in self._bounds
                }.items()
            },
        }

    def get_records(self, limit: int = 100) -> List[OptimizationRecord]:
        return self._records[-limit:]
