"""FeedbackSignal: 五路复合信号加权聚合。

五路信号来源：
  Explicit:   用户纠正 Hypothesis 时 → 负信号
  Implicit:   用户接受了 Agent 的建议 → 正信号
  Task:       Task 完成了 → 正信号
  Convergence: Hypothesis 投票收敛速度 → 速度信号
  Diversity:  解释生态的多样性 → 健康信号

聚合方式：加权平均，权重自身可调（meta-param）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class FeedbackSignal:
    """五路复合反馈信号。

    每路信号归一化到 [-1, +1]：
      +1.0 = 强烈正面（参数方向正确）
       0.0 = 中性
      -1.0 = 强烈负面（参数方向错误）
    """
    explicit: float = 0.0      # 用户显式纠正/确认
    implicit: float = 0.0      # 用户行为推断（接受/忽略/重试）
    task: float = 0.0          # 任务完成/失败
    convergence: float = 0.0   # Hypothesis 收敛速度
    diversity: float = 0.0     # 解释生态多样性

    # 权重（meta-param，自身可被 BO 调优）
    weights: Dict[str, float] = field(default_factory=lambda: {
        "explicit": 0.20,
        "implicit": 0.20,
        "task": 0.20,
        "convergence": 0.20,
        "diversity": 0.20,
    })

    def composite(self) -> float:
        """返回加权聚合后的复合信号，范围 [-1, +1]。"""
        w = self.weights
        total_w = sum(w.values())
        if total_w == 0:
            return 0.0
        score = (
            w["explicit"] * self._clamp(self.explicit)
            + w["implicit"] * self._clamp(self.implicit)
            + w["task"] * self._clamp(self.task)
            + w["convergence"] * self._clamp(self.convergence)
            + w["diversity"] * self._clamp(self.diversity)
        ) / total_w
        return self._clamp(score)

    def with_explicit(self, correction: bool, confidence: float = 1.0) -> "FeedbackSignal":
        """用户显式纠正 Hypothesis。

        Args:
            correction: True = 用户纠正了（负信号），False = 用户确认了（正信号）
            confidence: 信号置信度
        """
        self.explicit = -confidence if correction else +confidence
        return self

    def with_implicit(self, accepted: bool, retry_count: int = 0) -> "FeedbackSignal":
        """从用户行为推断信号。

        Args:
            accepted: 用户是否接受了建议
            retry_count: 用户重试次数（越多越负面）
        """
        if accepted:
            self.implicit = 0.5
        else:
            self.implicit = max(-1.0, -0.3 * (1 + retry_count))
        return self

    def with_task(self, success: bool, duration_sec: float = 0.0) -> "FeedbackSignal":
        """任务完成信号。

        Args:
            success: 任务是否成功
            duration_sec: 任务耗时（越快越好）
        """
        if success:
            # 耗时越短，信号越强（上限 +1.0）
            speed_bonus = max(0.0, 1.0 - duration_sec / 300.0) * 0.3
            self.task = 0.7 + speed_bonus
        else:
            self.task = -0.8
        return self

    def with_convergence(self, rounds_to_converge: int, total_rounds: int = 0) -> "FeedbackSignal":
        """Hypothesis 投票收敛速度信号。

        Args:
            rounds_to_converge: 多少轮投票后收敛
            total_rounds: 总投票轮数（0 表示未收敛）
        """
        if total_rounds == 0 or rounds_to_converge == 0:
            # 未收敛 → 负面
            self.convergence = -0.5
            return self
        ratio = rounds_to_converge / max(1, total_rounds)
        # 收敛越快（ratio 越小）→ 信号越强
        self.convergence = max(-1.0, 1.0 - 2.0 * ratio)
        return self

    def with_diversity(self, n_hypotheses: int, n_domains: int) -> "FeedbackSignal":
        """解释生态多样性信号。

        Args:
            n_hypotheses: 活跃 Hypothesis 数量
            n_domains: 涉及的知识域数量
        """
        # 太少 = 单一解释风险；太多 = 过度碎片化
        if n_hypotheses < 2:
            self.diversity = -0.3  # 缺乏竞争
        elif n_hypotheses > 20:
            self.diversity = -0.2  # 过度碎片化
        else:
            self.diversity = 0.3 + 0.1 * min(n_domains, 5)
        self.diversity = self._clamp(self.diversity)
        return self

    def set_weights(self, **kwargs) -> "FeedbackSignal":
        """动态调整信号权重（由 meta-optimizer 调用）。"""
        for k, v in kwargs.items():
            if k in self.weights:
                self.weights[k] = max(0.0, min(1.0, v))
        # 归一化
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total
        return self

    @staticmethod
    def _clamp(v: float) -> float:
        return max(-1.0, min(1.0, v))

    def to_dict(self) -> dict:
        return {
            "explicit": self.explicit,
            "implicit": self.implicit,
            "task": self.task,
            "convergence": self.convergence,
            "diversity": self.diversity,
            "weights": dict(self.weights),
            "composite": self.composite(),
        }
