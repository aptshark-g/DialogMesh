# core/agent/coordinator/adaptive_threshold.py
"""自适应阈值系统 —— 根据用户历史行为动态调整复杂度评估阈值。

核心思路：
1. 每个用户有独立的 ThresholdProfile（阈值画像）
2. 从反馈学习：用户纠错 = 当前模式不够，提升阈值
3. 从模式学习：分析用户历史查询分布，自动调整权重
4. 阈值画像随用户画像一起持久化

使用方式：
    # 基础评估（无用户偏好）
    score = evaluator.evaluate(query)
    
    # 自适应评估（带用户阈值画像）
    profile = user_profile.threshold_profile
    score = evaluator.evaluate(query, threshold_profile=profile)
    
    # 记录反馈
    profile.record_feedback(
        original_score=score.total,
        used_mode="rule",
        user_correction=True,  # 用户纠正了回复
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from core.agent.coordinator.bayesian_engine import BayesianEngine
except ImportError:
    BayesianEngine = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class ThresholdProfile:
    """用户自适应阈值画像 —— 确定性 + 贝叶斯双引擎。
    
    架构：
    - 确定性引擎：快速路径，线性反馈（保留原有行为）
    - 贝叶斯引擎：概率推断，Thompson Sampling，处理不确定性
    
    默认使用确定性引擎，当观测数据足够（>10次）且不确定性高时，
    自动切换到贝叶斯 Thompson Sampling。
    """
    user_id: str
    
    # 维度权重调整（默认 1.0，可动态调整 0.5-2.0）
    length_weight: float = 1.0
    entity_weight: float = 1.0
    intent_weight: float = 1.0
    history_weight: float = 1.0
    cohesion_weight: float = 1.0
    ambiguity_weight: float = 1.0
    task_switch_weight: float = 1.0
    multi_intent_weight: float = 1.0
    
    # 全局阈值调整（基础分偏移）
    base_offset: int = 0  # -2 ~ +2，整体难度感知偏移
    
    # 模式边界调整（默认 3/7）
    rule_threshold: int = 3      # 0-3 改为可调整（如 2-4）
    small_model_threshold: int = 7  # 4-7 改为可调整（如 5-8）
    
    # 学习统计
    total_evaluations: int = 0
    rule_count: int = 0
    small_model_count: int = 0
    remote_llm_count: int = 0
    correction_count: int = 0  # 用户纠错次数
    satisfaction_estimate: float = 0.8  # 满意度估计（0-1）
    
    # 历史窗口（最近20次评估）
    recent_scores: List[int] = field(default_factory=list)
    recent_modes: List[str] = field(default_factory=list)
    
    # ── 贝叶斯引擎（概率推断）────────────────────────────────────
    use_bayesian: bool = True  # 是否启用贝叶斯引擎
    bayesian_data: Optional[Dict[str, Any]] = None  # BayesianEngine 序列化数据
    
    # 缓存（非序列化）
    _bayesian_engine: Optional[Any] = field(default=None, repr=False)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # 确保权重在合理范围
        self._clamp_weights()
        self._init_bayesian()
    
    def _init_bayesian(self) -> None:
        """初始化贝叶斯引擎。"""
        if not self.use_bayesian or BayesianEngine is None:
            return
        if self.bayesian_data is not None:
            self._bayesian_engine = BayesianEngine.from_dict(self.bayesian_data)
        else:
            self._bayesian_engine = BayesianEngine(user_id=self.user_id)
    
    def _get_bayesian(self) -> Optional[Any]:
        """获取贝叶斯引擎（懒加载）。"""
        if self._bayesian_engine is None and self.use_bayesian and BayesianEngine is not None:
            self._init_bayesian()
        return self._bayesian_engine
    
    def _clamp_weights(self):
        """将权重限制在合理范围。"""
        for attr in ['length_weight', 'entity_weight', 'intent_weight', 
                     'history_weight', 'cohesion_weight', 'ambiguity_weight',
                     'task_switch_weight', 'multi_intent_weight']:
            val = getattr(self, attr)
            setattr(self, attr, max(0.5, min(2.0, val)))
        self.base_offset = max(-2, min(2, self.base_offset))
        self.rule_threshold = max(2, min(4, self.rule_threshold))
        self.small_model_threshold = max(5, min(8, self.small_model_threshold))
    
    # ── 反馈学习 ──────────────────────────────────────────────────
    
    def record_feedback(self, original_score: int, used_mode: str, 
                        user_correction: bool = False, 
                        user_repeated: bool = False,
                        user_satisfied: Optional[bool] = None,
                        features: Optional[Dict[str, Any]] = None) -> None:
        """记录用户反馈，触发阈值调整。
        
        Args:
            original_score: 原始复杂度评分
            used_mode: 实际使用的处理模式（rule/small_model/remote_llm）
            user_correction: 用户是否纠正了回复（说明当前模式不够）
            user_repeated: 用户是否重复了类似问题（说明没理解）
            user_satisfied: 用户是否满意（如果明确知道）
            features: 用户特征字典（传递给贝叶斯引擎做特征推断）
        """
        self.total_evaluations += 1
        self.recent_scores.append(original_score)
        self.recent_modes.append(used_mode)
        
        # 保持窗口
        if len(self.recent_scores) > 20:
            self.recent_scores.pop(0)
            self.recent_modes.pop(0)
        
        # 更新模式分布
        if used_mode == "rule":
            self.rule_count += 1
        elif used_mode == "small_model":
            self.small_model_count += 1
        elif used_mode == "remote_llm":
            self.remote_llm_count += 1
        
        # 纠错反馈：当前模式不够，提升该用户的难度感知
        if user_correction:
            self.correction_count += 1
            self._adjust_for_correction(original_score, used_mode)
        
        # 重复问题：可能是当前模式没理解，轻微提升
        if user_repeated:
            self.base_offset = min(2, self.base_offset + 0.5)
        
        # 满意度反馈
        if user_satisfied is not None:
            # 指数移动平均
            alpha = 0.3
            self.satisfaction_estimate = alpha * (1.0 if user_satisfied else 0.0) + \
                                         (1 - alpha) * self.satisfaction_estimate
        
        # 贝叶斯反馈更新（概率引擎）
        self._bayesian_feedback(original_score, used_mode, user_correction, user_repeated, user_satisfied, features)
        
        # 定期全局调整
        self._global_adjustment()
        self._clamp_weights()
    
    def _bayesian_feedback(self, original_score: int, used_mode: str,
                           user_correction: bool, user_repeated: bool,
                           user_satisfied: Optional[bool],
                           features: Optional[Dict[str, Any]] = None) -> None:
        """贝叶斯反馈更新 —— 与确定性反馈并行。"""
        be = self._get_bayesian()
        if be is None:
            return
        
        # 1. 记录模式偏好（多分类）
        be.observe_categorical("mode_preference", used_mode, confidence=0.5)
        
        # 2. 满意度（二分类）
        if user_satisfied is not None:
            be.observe_binary("is_satisfied", user_satisfied, strength=1.0)
        
        # 3. 纠错反馈（贝叶斯更新 base_offset）
        if user_correction:
            current_offset = self.base_offset
            suggested_offset = min(2, current_offset + 1.0)
            be.observe_gaussian("base_offset", value=suggested_offset, variance=0.5)
            be.observe_binary("is_satisfied", False, strength=0.5)
        
        # 4. 重复问题（贝叶斯更新 base_offset）
        if user_repeated:
            current_offset = self.base_offset
            suggested_offset = min(2, current_offset + 0.5)
            be.observe_gaussian("base_offset", value=suggested_offset, variance=0.8)
        
        # 5. 从用户特征推断（多分类 + 二分类更新）
        if features:
            be.observe_from_features(features)
        
        # 6. 同步 bayesian_data 用于持久化
        self.bayesian_data = be.to_dict()
    
    def record_features(self, features: Dict[str, Any]) -> None:
        """从用户特征更新贝叶斯后验（不修改确定性统计）。
        
        用于在 _extract_and_update_user_features 中传递特征，
        避免重复计数 total_evaluations。
        """
        be = self._get_bayesian()
        if be is None:
            return
        be.observe_from_features(features)
        self.bayesian_data = be.to_dict()
    
    def _adjust_for_correction(self, original_score: int, used_mode: str) -> None:
        """根据纠错调整阈值。
        
        策略：
        - rule 模式被纠错 → 提高 base_offset（整体更难）
        - small_model 被纠错 → 提高 small_model 阈值（更多走 remote_llm）
        - remote_llm 被纠错 → 提高 multi_intent_weight（用户可能需求更复杂）
        """
        if used_mode == "rule":
            # 简单模式处理不了，整体提升
            self.base_offset = min(2, self.base_offset + 1)
            logger.info(f"User {self.user_id}: rule mode insufficient, base_offset += 1 → {self.base_offset}")
        
        elif used_mode == "small_model":
            # 小模型不够，降低 small_model 阈值上限（让更多查询走到 remote_llm）
            self.small_model_threshold = max(5, self.small_model_threshold - 1)
            logger.info(f"User {self.user_id}: small_model insufficient, threshold -= 1 → {self.small_model_threshold}")
        
        elif used_mode == "remote_llm":
            # 大模型都不够，可能用户确实需要更多思考
            self.multi_intent_weight = min(2.0, self.multi_intent_weight + 0.3)
            self.ambiguity_weight = min(2.0, self.ambiguity_weight + 0.3)
            logger.info(f"User {self.user_id}: remote_llm insufficient, raising multi_intent/ambiguity weights")
    
    def _global_adjustment(self) -> None:
        """基于历史分布的全局调整。
        
        策略：
        - 如果用户 80%+ 查询触发 small_model/remote_llm → 该用户整体偏难，base_offset + 1
        - 如果用户 80%+ 查询触发 rule → 该用户整体偏简单，base_offset - 1
        - 如果满意度持续低于 0.5 → 提高所有权重（更谨慎）
        """
        if len(self.recent_modes) < 10:
            return  # 数据不足
        
        recent_complex = sum(1 for m in self.recent_modes if m in ("small_model", "remote_llm"))
        complex_ratio = recent_complex / len(self.recent_modes)
        
        if complex_ratio > 0.8:
            # 用户整体偏难，轻微提升 base_offset（避免漏判）
            self.base_offset = min(2, self.base_offset + 0.5)
            logger.debug(f"User {self.user_id}: complex user detected, base_offset += 0.5")
        
        elif complex_ratio < 0.2:
            # 用户整体偏简单，轻微降低 base_offset（避免过度复杂化）
            self.base_offset = max(-2, self.base_offset - 0.5)
            logger.debug(f"User {self.user_id}: simple user detected, base_offset -= 0.5")
        
        # 满意度调整
        if self.satisfaction_estimate < 0.5:
            # 用户不满意，更谨慎地提高所有权重
            for attr in ['length_weight', 'entity_weight', 'intent_weight', 
                         'history_weight', 'cohesion_weight', 'ambiguity_weight',
                         'task_switch_weight', 'multi_intent_weight']:
                val = getattr(self, attr)
                setattr(self, attr, min(2.0, val + 0.1))
            logger.info(f"User {self.user_id}: low satisfaction, raising all weights")
    
    # ── 权重应用 ──────────────────────────────────────────────────
    
    def apply_weights(self, raw_scores: Dict[str, int]) -> int:
        """将原始分数应用权重调整后计算总分。
        
        Args:
            raw_scores: {"length": 2, "entity": 1, ...}
        
        Returns:
            加权后的总分（0-10，封顶）
        """
        weights = {
            "length": self.length_weight,
            "entity": self.entity_weight,
            "intent": self.intent_weight,
            "history": self.history_weight,
            "cohesion": self.cohesion_weight,
            "ambiguity": self.ambiguity_weight,
            "task_switch": self.task_switch_weight,
            "multi_intent": self.multi_intent_weight,
        }
        
        total = 0.0
        for key, raw in raw_scores.items():
            weight = weights.get(key, 1.0)
            total += raw * weight
        
        # 应用全局偏移
        total += self.base_offset
        
        # 封顶 0-10
        return int(max(0, min(10, round(total))))
    
    def get_mode(self, score: int) -> str:
        """根据自适应阈值判断模式。
        
        如果贝叶斯引擎启用且数据足够（>5次观测），
        使用 Thompson Sampling 从后验采样阈值。
        否则使用确定性阈值。
        """
        be = self._get_bayesian()
        if be is not None and self.total_evaluations > 5:
            return be.get_mode_with_thompson(score, cost_budget="standard")
        if score <= self.rule_threshold:
            return "rule"
        elif score <= self.small_model_threshold:
            return "small_model"
        else:
            return "remote_llm"
    # ── 序列化 ───────────────────────────────────────────────────
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化阈值画像（包含贝叶斯数据）。"""
        if self._bayesian_engine is not None:
            self.bayesian_data = self._bayesian_engine.to_dict()
        return {
            "user_id": self.user_id,
            "length_weight": self.length_weight,
            "entity_weight": self.entity_weight,
            "intent_weight": self.intent_weight,
            "history_weight": self.history_weight,
            "cohesion_weight": self.cohesion_weight,
            "ambiguity_weight": self.ambiguity_weight,
            "task_switch_weight": self.task_switch_weight,
            "multi_intent_weight": self.multi_intent_weight,
            "base_offset": self.base_offset,
            "rule_threshold": self.rule_threshold,
            "small_model_threshold": self.small_model_threshold,
            "total_evaluations": self.total_evaluations,
            "rule_count": self.rule_count,
            "small_model_count": self.small_model_count,
            "remote_llm_count": self.remote_llm_count,
            "correction_count": self.correction_count,
            "satisfaction_estimate": self.satisfaction_estimate,
            "recent_scores": self.recent_scores,
            "recent_modes": self.recent_modes,
            "use_bayesian": self.use_bayesian,
            "bayesian_data": self.bayesian_data,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ThresholdProfile:
        return cls(
            user_id=data.get("user_id", "anonymous"),
            length_weight=data.get("length_weight", 1.0),
            entity_weight=data.get("entity_weight", 1.0),
            intent_weight=data.get("intent_weight", 1.0),
            history_weight=data.get("history_weight", 1.0),
            cohesion_weight=data.get("cohesion_weight", 1.0),
            ambiguity_weight=data.get("ambiguity_weight", 1.0),
            task_switch_weight=data.get("task_switch_weight", 1.0),
            multi_intent_weight=data.get("multi_intent_weight", 1.0),
            base_offset=data.get("base_offset", 0),
            rule_threshold=data.get("rule_threshold", 3),
            small_model_threshold=data.get("small_model_threshold", 7),
            total_evaluations=data.get("total_evaluations", 0),
            rule_count=data.get("rule_count", 0),
            small_model_count=data.get("small_model_count", 0),
            remote_llm_count=data.get("remote_llm_count", 0),
            use_bayesian=data.get("use_bayesian", True),
            bayesian_data=data.get("bayesian_data", None),
            correction_count=data.get("correction_count", 0),
            satisfaction_estimate=data.get("satisfaction_estimate", 0.8),
            recent_scores=data.get("recent_scores", []),
            recent_modes=data.get("recent_modes", []),
            metadata=data.get("metadata", {}),
        )
