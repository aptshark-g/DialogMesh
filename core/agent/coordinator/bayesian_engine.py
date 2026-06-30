# core/agent/coordinator/bayesian_engine.py
"""贝叶斯推断引擎 —— 自适应阈值的概率化升级。

核心能力：
- 用概率分布建模用户画像（Dirichlet 多分类、Beta 二分类、Gaussian 连续值）
- 每次交互 = 观测数据，贝叶斯更新后验
- Thompson Sampling 做阈值选择（探索 vs 利用）
- 新用户从群体先验自动初始化，无需冷启动

对比确定性反馈：
- 旧：base_offset += 1（无不确定性，不收敛）
- 新：P(base_offset=2) = 0.3, P(base_offset=1) = 0.5, ...（收敛到真实分布）

使用方式：
    engine = BayesianEngine()
    
    # 多分类：用户技术水平
    engine.observe_categorical("tech_level", category="beginner", confidence=0.8)
    print(engine.get_posterior("tech_level"))  # {"beginner": 0.7, "intermediate": 0.2, ...}
    
    # 二分类：用户是否不耐烦
    engine.observe_binary("is_impatient", success=True, strength=0.9)
    print(engine.get_posterior_mean("is_impatient"))  # 0.85
    
    # 连续值：维度权重（高斯更新）
    engine.observe_gaussian("multi_intent_weight", value=1.5, variance=0.3)
    
    # Thompson Sampling：从后验采样选择最优参数
    sampled_offset = engine.thompson_sample_gaussian("base_offset", bounds=(-2, 2))
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BetaDistribution:
    """Beta 分布 —— 二分类观测（如：用户是否不耐烦、是否满意）。"""
    alpha: float = 1.0  # 成功计数（+1 平滑）
    beta: float = 1.0   # 失败计数（+1 平滑）
    
    def observe(self, success: bool, strength: float = 1.0) -> None:
        """更新 Beta 分布。
        
        Args:
            success: 观测结果（True=成功/阳性，False=失败/阴性）
            strength: 观测强度（0.1-2.0，低=不确定，高=高置信）
        """
        if success:
            self.alpha += strength
        else:
            self.beta += strength
    
    def mean(self) -> float:
        """后验均值。"""
        return self.alpha / (self.alpha + self.beta)
    
    def variance(self) -> float:
        """后验方差。"""
        a_b = self.alpha + self.beta
        return (self.alpha * self.beta) / (a_b * a_b * (a_b + 1))
    
    def sample(self) -> float:
        """从后验采样。"""
        return np.random.beta(self.alpha, self.beta)
    
    def to_dict(self) -> Dict[str, float]:
        return {"alpha": self.alpha, "beta": self.beta}
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> BetaDistribution:
        return cls(alpha=data.get("alpha", 1.0), beta=data.get("beta", 1.0))


@dataclass
class DirichletDistribution:
    """Dirichlet 分布 —— 多分类观测（如：用户技术水平 beginner/intermediate/expert）。"""
    categories: List[str] = field(default_factory=lambda: ["beginner", "intermediate", "expert"])
    counts: Dict[str, float] = field(default_factory=dict)  # 伪计数
    
    def __post_init__(self):
        # 初始化均匀先验
        for c in self.categories:
            if c not in self.counts:
                self.counts[c] = 1.0  # +1 平滑
    
    def observe(self, category: str, confidence: float = 1.0) -> None:
        """更新 Dirichlet 分布。
        
        Args:
            category: 观测到的类别
            confidence: 观测置信度（0.1-2.0）
        """
        if category in self.counts:
            self.counts[category] += confidence
        else:
            # 新类别：添加到分布，从均匀先验分一点过来
            self.categories.append(category)
            self.counts[category] = 1.0 + confidence
    
    def get_probabilities(self) -> Dict[str, float]:
        """获取各类别的后验概率。"""
        total = sum(self.counts.values())
        return {c: self.counts[c] / total for c in self.categories}
    
    def get_most_likely(self) -> Tuple[str, float]:
        """获取最可能的类别及其概率。"""
        probs = self.get_probabilities()
        best = max(probs, key=probs.get)
        return best, probs[best]
    
    def sample(self) -> str:
        """从后验采样一个类别。"""
        probs = self.get_probabilities()
        categories = list(probs.keys())
        weights = list(probs.values())
        return random.choices(categories, weights=weights, k=1)[0]
    
    def to_dict(self) -> Dict[str, Any]:
        return {"categories": self.categories, "counts": dict(self.counts)}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DirichletDistribution:
        return cls(
            categories=data.get("categories", ["beginner", "intermediate", "expert"]),
            counts=data.get("counts", {}),
        )


@dataclass
class GaussianDistribution:
    """高斯分布 —— 连续值观测（如：维度权重、base_offset）。"""
    mu: float = 0.0    # 均值
    sigma2: float = 1.0  # 方差（先验较宽）
    n_observations: int = 0  # 观测次数
    
    def observe(self, value: float, variance: Optional[float] = None) -> None:
        """更新高斯分布（共轭先验更新）。
        
        Args:
            value: 观测值
            variance: 观测噪声（None=使用当前 sigma2 的 1/10）
        """
        obs_var = variance if variance is not None else max(0.1, self.sigma2 / 10)
        
        # 贝叶斯更新：后验 precision = 先验 precision + 观测 precision
        prior_precision = 1.0 / self.sigma2
        obs_precision = 1.0 / obs_var
        
        posterior_precision = prior_precision + obs_precision
        posterior_sigma2 = 1.0 / posterior_precision
        
        # 后验均值 = 加权平均
        posterior_mu = (self.mu * prior_precision + value * obs_precision) / posterior_precision
        
        self.mu = posterior_mu
        self.sigma2 = posterior_sigma2
        self.n_observations += 1
    
    def mean(self) -> float:
        return self.mu
    
    def std(self) -> float:
        return np.sqrt(self.sigma2)
    
    def sample(self) -> float:
        """从后验采样。"""
        return np.random.normal(self.mu, self.std())
    
    def to_dict(self) -> Dict[str, float]:
        return {"mu": self.mu, "sigma2": self.sigma2, "n_observations": self.n_observations}
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> GaussianDistribution:
        return cls(
            mu=data.get("mu", 0.0),
            sigma2=data.get("sigma2", 1.0),
            n_observations=data.get("n_observations", 0),
        )


class BayesianEngine:
    """贝叶斯推断引擎 —— 管理所有维度的概率分布。"""
    
    # 预设维度
    DEFAULT_BINARY_VARIABLES = [
        "is_impatient",      # 用户是否不耐烦
        "is_expert",         # 用户是否专家
        "needs_tutorial",    # 用户是否需要教程风格
        "prefers_concise",   # 用户是否偏好简洁
        "has_multi_intent",  # 用户是否常有多意图
        "is_satisfied",      # 用户是否满意
    ]
    
    DEFAULT_CATEGORICAL_VARIABLES = {
        "tech_level": ["beginner", "intermediate", "expert"],
        "patience": ["impatient", "neutral", "patient"],
        "style": ["concise", "detailed", "tutorial", "unknown"],
        "attention_span": ["short", "medium", "long"],
    }
    
    DEFAULT_GAUSSIAN_VARIABLES = {
        "base_offset": (0.0, 2.0),          # 全局偏移
        "length_weight": (1.0, 0.5),        # 长度权重
        "multi_intent_weight": (1.0, 0.5),  # 多意图权重
        "ambiguity_weight": (1.0, 0.5),     # 歧义权重
    }
    
    def __init__(self, user_id: str = "anonymous"):
        self.user_id = user_id
        
        # 二分类分布
        self._binary: Dict[str, BetaDistribution] = {
            v: BetaDistribution() for v in self.DEFAULT_BINARY_VARIABLES
        }
        
        # 多分类分布
        self._categorical: Dict[str, DirichletDistribution] = {
            k: DirichletDistribution(categories=v) 
            for k, v in self.DEFAULT_CATEGORICAL_VARIABLES.items()
        }
        
        # 高斯分布
        self._gaussian: Dict[str, GaussianDistribution] = {
            k: GaussianDistribution(mu=mu, sigma2=var)
            for k, (mu, var) in self.DEFAULT_GAUSSIAN_VARIABLES.items()
        }
        
        # 自定义分布（运行时动态添加）
        self._custom_binary: Dict[str, BetaDistribution] = {}
        self._custom_categorical: Dict[str, DirichletDistribution] = {}
        self._custom_gaussian: Dict[str, GaussianDistribution] = {}
        
        # 观测历史（用于调试/分析）
        self._observation_history: List[Dict[str, Any]] = []
    
    # ── 观测接口 ──────────────────────────────────────────────────
    
    def observe_binary(self, variable: str, success: bool, strength: float = 1.0) -> None:
        """二分类观测。"""
        dist = self._get_binary(variable)
        dist.observe(success, strength)
        self._observation_history.append({
            "type": "binary", "variable": variable, "success": success, "strength": strength,
            "posterior_mean": dist.mean(),
        })
    
    def observe_categorical(self, variable: str, category: str, confidence: float = 1.0) -> None:
        """多分类观测。"""
        dist = self._get_categorical(variable)
        dist.observe(category, confidence)
        probs = dist.get_probabilities()
        self._observation_history.append({
            "type": "categorical", "variable": variable, "category": category,
            "confidence": confidence, "posterior": probs,
        })
    
    def observe_gaussian(self, variable: str, value: float, variance: Optional[float] = None) -> None:
        """连续值观测。"""
        dist = self._get_gaussian(variable)
        dist.observe(value, variance)
        self._observation_history.append({
            "type": "gaussian", "variable": variable, "value": value,
            "posterior_mu": dist.mean(), "posterior_std": dist.std(),
        })
    
    def observe_from_features(self, features: Dict[str, Any]) -> None:
        """从特征字典批量观测（与 UserExtractor 输出兼容）。
        
        Args:
            features: {"tech_level": "beginner", "patience_level": "impatient", ...}
        """
        # 技术水平（多分类）
        tech_level = features.get("tech_level")
        if tech_level:
            self.observe_categorical("tech_level", tech_level, confidence=0.8)
        
        # 耐心（多分类 + 二分类）
        patience = features.get("patience_level")
        if patience:
            self.observe_categorical("patience", patience, confidence=0.7)
            if patience == "impatient":
                self.observe_binary("is_impatient", True, strength=0.8)
            elif patience == "patient":
                self.observe_binary("is_impatient", False, strength=0.8)
        
        # 风格
        style = features.get("style")
        if style:
            self.observe_categorical("style", style, confidence=0.7)
            if style == "concise":
                self.observe_binary("prefers_concise", True, strength=0.7)
        
        # 多意图检测（二分类）
        if features.get("multi_intent_detected", False):
            self.observe_binary("has_multi_intent", True, strength=0.9)
    
    # ── 查询接口 ──────────────────────────────────────────────────
    
    def get_binary_mean(self, variable: str) -> float:
        """获取二分类变量的后验均值。"""
        return self._get_binary(variable).mean()
    
    def get_categorical_probs(self, variable: str) -> Dict[str, float]:
        """获取多分类变量的后验概率。"""
        return self._get_categorical(variable).get_probabilities()
    
    def get_most_likely(self, variable: str) -> Tuple[str, float]:
        """获取最可能的类别。"""
        return self._get_categorical(variable).get_most_likely()
    
    def get_gaussian_mean(self, variable: str) -> float:
        """获取高斯变量的后验均值。"""
        return self._get_gaussian(variable).mean()
    
    def get_gaussian_std(self, variable: str) -> float:
        """获取高斯变量的后验标准差。"""
        return self._get_gaussian(variable).std()
    
    def get_uncertainty(self, variable: str) -> float:
        """获取变量的不确定性（方差/归一化）。"""
        if variable in self._binary or variable in self._custom_binary:
            return self._get_binary(variable).variance()
        elif variable in self._gaussian or variable in self._custom_gaussian:
            return self._get_gaussian(variable).std()
        elif variable in self._categorical or variable in self._custom_categorical:
            probs = self._get_categorical(variable).get_probabilities()
            # 熵作为不确定性度量
            from math import log
            entropy = -sum(p * log(p) for p in probs.values() if p > 0)
            max_entropy = log(len(probs))
            return entropy / max_entropy if max_entropy > 0 else 0.0
        return 1.0
    
    # ── Thompson Sampling ───────────────────────────────────────
    
    def thompson_sample_gaussian(self, variable: str, bounds: Optional[Tuple[float, float]] = None) -> float:
        """Thompson Sampling：从后验采样，用于探索-利用权衡。
        
        原理：
        - 不确定性高 → 采样值分散 → 探索新阈值
        - 不确定性低 → 采样值集中 → 利用已知最优
        
        Args:
            variable: 高斯变量名
            bounds: 采样值裁剪范围
        
        Returns:
            采样值（用于阈值选择）
        """
        dist = self._get_gaussian(variable)
        value = dist.sample()
        if bounds:
            value = max(bounds[0], min(bounds[1], value))
        return value
    
    def thompson_sample_categorical(self, variable: str) -> str:
        """Thompson Sampling：从多分类后验采样。"""
        return self._get_categorical(variable).sample()
    
    def thompson_sample_binary(self, variable: str) -> bool:
        """Thompson Sampling：从二分类后验采样。"""
        return self._get_binary(variable).sample() > 0.5
    
    def get_mode_with_thompson(self, complexity_score: int, cost_budget: str = "standard") -> str:
        """使用 Thompson Sampling 选择处理模式。
        
        策略：
        - 从 base_offset 的后验采样一个偏移值
        - 调整复杂度分数：adjusted_score = complexity_score + sampled_offset
        - 根据调整后的分数选择模式
        - 不确定性高时会自动探索（偏移值可能让分数跨边界）
        
        Args:
            complexity_score: 原始复杂度评分（0-10）
            cost_budget: 成本预算
        
        Returns:
            "rule" / "small_model" / "remote_llm"
        """
        # 采样 base_offset（探索-利用）
        offset = self.thompson_sample_gaussian("base_offset", bounds=(-2, 2))
        adjusted_score = complexity_score + offset
        
        # 成本预算调整
        if cost_budget == "free":
            adjusted_score = min(adjusted_score, 5)
        elif cost_budget == "premium":
            adjusted_score = max(0, adjusted_score - 2)
        
        # 阈值也从后验采样（探索）
        rule_threshold = self.thompson_sample_gaussian("rule_threshold", bounds=(2, 4))
        sm_threshold = self.thompson_sample_gaussian("small_model_threshold", bounds=(5, 8))
        
        # 选择模式
        if adjusted_score <= rule_threshold:
            return "rule"
        elif adjusted_score <= sm_threshold:
            return "small_model"
        else:
            return "remote_llm"
    
    # ── 反馈学习（贝叶斯版本）────────────────────────────────────
    
    def record_feedback_bayesian(
        self,
        original_score: int,
        used_mode: str,
        user_correction: bool = False,
        user_repeated: bool = False,
        user_satisfied: Optional[bool] = None,
    ) -> None:
        """贝叶斯反馈学习。
        
        与确定性反馈的区别：
        - 用 Beta 分布建模满意度（is_satisfied）
        - 用 Gaussian 更新 base_offset（观测到偏移量）
        - 用多分类更新用户模式偏好
        """
        # 1. 满意度更新（Beta）
        if user_satisfied is not None:
            self.observe_binary("is_satisfied", user_satisfied, strength=1.0)
        
        # 2. 纠错反馈（说明当前模式不够 → base_offset 应该更高）
        if user_correction:
            # 观测：base_offset 需要增加（高斯更新，观测值=+1，但噪声较大）
            current_offset = self.get_gaussian_mean("base_offset")
            suggested_offset = min(2, current_offset + 1.0)
            self.observe_gaussian("base_offset", value=suggested_offset, variance=0.5)
            
            # 同时降低满意度
            self.observe_binary("is_satisfied", False, strength=0.5)
        
        # 3. 重复问题（说明没理解 → 可能模式不够）
        if user_repeated:
            current_offset = self.get_gaussian_mean("base_offset")
            suggested_offset = min(2, current_offset + 0.5)
            self.observe_gaussian("base_offset", value=suggested_offset, variance=0.8)
        
        # 4. 模式偏好（多分类）
        if used_mode in ["rule", "small_model", "remote_llm"]:
            mode_pref = self._get_categorical("mode_preference")
            mode_pref.observe(used_mode, confidence=0.5)
    
    # ── 内部方法 ──────────────────────────────────────────────────
    
    def _get_binary(self, variable: str) -> BetaDistribution:
        if variable in self._custom_binary:
            return self._custom_binary[variable]
        if variable in self._binary:
            return self._binary[variable]
        self._custom_binary[variable] = BetaDistribution()
        return self._custom_binary[variable]
    
    def _get_categorical(self, variable: str) -> DirichletDistribution:
        if variable in self._custom_categorical:
            return self._custom_categorical[variable]
        if variable in self._categorical:
            return self._categorical[variable]
        self._custom_categorical[variable] = DirichletDistribution(categories=["unknown"])
        return self._custom_categorical[variable]
    
    def _get_gaussian(self, variable: str) -> GaussianDistribution:
        if variable in self._custom_gaussian:
            return self._custom_gaussian[variable]
        if variable in self._gaussian:
            return self._gaussian[variable]
        self._custom_gaussian[variable] = GaussianDistribution()
        return self._custom_gaussian[variable]
    
    # ── 序列化 ───────────────────────────────────────────────────
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "binary": {k: v.to_dict() for k, v in {**self._binary, **self._custom_binary}.items()},
            "categorical": {k: v.to_dict() for k, v in {**self._categorical, **self._custom_categorical}.items()},
            "gaussian": {k: v.to_dict() for k, v in {**self._gaussian, **self._custom_gaussian}.items()},
            "history_count": len(self._observation_history),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BayesianEngine:
        engine = cls(user_id=data.get("user_id", "anonymous"))
        
        for k, v in data.get("binary", {}).items():
            engine._custom_binary[k] = BetaDistribution.from_dict(v)
        for k, v in data.get("categorical", {}).items():
            engine._custom_categorical[k] = DirichletDistribution.from_dict(v)
        for k, v in data.get("gaussian", {}).items():
            engine._custom_gaussian[k] = GaussianDistribution.from_dict(v)
        
        return engine
