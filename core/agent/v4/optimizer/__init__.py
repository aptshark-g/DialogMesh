"""core/agent/v4/optimizer/__init__.py

Bayesian Parameter Optimizer for DialogMesh v4.

最小可行设计：
  - 3 个文件：signals.py, optimizer.py, __init__.py
  - 5-8 个参数，独立 GP，O(n²) 增量更新
  - EI acquisition
  - 读/写 WorldParams，不做独立存储

Usage:
    from core.agent.v4.optimizer import BayesianOptimizer, FeedbackSignal, ParameterBounds
    from core.agent.v4.world.params import WorldParams

    # 1. 定义要优化的参数边界
    bounds = {
        "min_support": ParameterBounds("min_support", 3, 15, wp.min_support),
        "max_conflict": ParameterBounds("max_conflict", 1, 8, wp.max_conflict),
        ...
    }

    # 2. 创建优化器
    opt = BayesianOptimizer(bounds)

    # 3. 系统运行一段时间后，收集反馈
    signal = FeedbackSignal()
        .with_explicit(correction=False, confidence=0.9)
        .with_task(success=True, duration_sec=120)
    reward = signal.composite()  # → 0.7

    # 4. 记录观测
    opt.observe(current_params, reward)

    # 5. 获取下一组建议
    next_params = opt.suggest()
"""
from __future__ import annotations

from .signals import FeedbackSignal
from .optimizer import BayesianOptimizer, ParameterBounds, OptimizationRecord

__all__ = [
    "FeedbackSignal",
    "BayesianOptimizer",
    "ParameterBounds",
    "OptimizationRecord",
]
