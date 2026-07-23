"""BudgetAllocator: 三层预算分配算法

设计文档: docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md §5
- 必要层: 200 tokens（不可裁剪，用户消息本身）
- 策略层: 300 tokens（意图感知分配）
- 弹性层: 200 tokens（溢出预算，仅在子 token 预算充足时使用）

分配规则:
- 主域(60%) → 180 tokens
- 辅助域1(25%) → 75 tokens
- 辅助域2(15%) → 45 tokens
- 域填不满时，剩余量分配给下一优先级域
- 所有域都填不满时，剩余预算返还给必要层
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DomainBudget:
    """单个域的预算分配结果."""
    domain: str
    role: str  # primary | auxiliary
    budget_tokens: int
    used_tokens: int = 0
    remaining_tokens: int = 0

    def __post_init__(self):
        self.remaining_tokens = self.budget_tokens

    def consume(self, tokens: int) -> int:
        """消费预算，返回实际消费的 tokens."""
        actual = min(tokens, self.remaining_tokens)
        self.used_tokens += actual
        self.remaining_tokens -= actual
        return actual


@dataclass
class BudgetPlan:
    """完整的预算分配计划."""
    mandatory_tokens: int          # 必要层（不可裁剪）
    strategy_tokens: int           # 策略层（意图感知分配）
    flexible_tokens: int           # 弹性层（溢出）
    strategy_plan: List[DomainBudget] = field(default_factory=list)
    compile_strategy: str = "balanced"  # primary_deep | balanced | summary_fallback

    @property
    def total_budget(self) -> int:
        return self.mandatory_tokens + self.strategy_tokens + self.flexible_tokens

    @property
    def total_used(self) -> int:
        return self.mandatory_tokens + sum(d.used_tokens for d in self.strategy_plan)

    @property
    def total_remaining(self) -> int:
        return self.total_budget - self.total_used


class BudgetAllocator:
    """三层预算分配器：必要层 → 策略层 → 弹性层.

    用法:
        allocator = BudgetAllocator()
        plan = allocator.allocate("task", strategy_budget=300)
        # plan.strategy_plan[0] = DomainBudget(domain="E", budget_tokens=180, ...)
    """

    # 意图 → 域选择矩阵 (主域, 辅助域1, 辅助域2)
    # 设计文档 §4.2
    _INTENT_DOMAIN_MAP: Dict[str, tuple] = {
        "task":        ("E", "B", "P"),   # 工程操作
        "query":       ("C", "E", "P"),   # 信息查询
        "correction":  ("B", "E", "K"),   # 纠正
        "discussion":  ("P", "C", "E"),   # 思路讨论
        "casual":      ("C", "P", None),  # 闲聊（无辅助域2）
        "topic_switch":("C", "B", "P"),   # 话题切换
    }

    # 默认预算配置
    _DEFAULT_MANDATORY = 200
    _DEFAULT_STRATEGY  = 300
    _DEFAULT_FLEXIBLE  = 200

    # 分配比例
    _PRIMARY_PCT    = 0.60
    _AUX1_PCT       = 0.25
    _AUX2_PCT       = 0.15

    def __init__(
        self,
        mandatory_tokens: int = _DEFAULT_MANDATORY,
        strategy_tokens: int = _DEFAULT_STRATEGY,
        flexible_tokens: int = _DEFAULT_FLEXIBLE,
    ):
        self.mandatory_tokens = mandatory_tokens
        self.strategy_tokens = strategy_tokens
        self.flexible_tokens = flexible_tokens

    def allocate(
        self,
        intent_category: str,
        strategy_tokens: Optional[int] = None,
        user_strategy: Optional[str] = None,
    ) -> BudgetPlan:
        """根据意图类别分配策略层预算.

        Args:
            intent_category: task|query|correction|discussion|casual|topic_switch
            strategy_tokens: 可覆盖默认策略层预算
            user_strategy:   quality_first | balanced | cost_first

        Returns:
            BudgetPlan: 包含各域预算分配的完整计划
        """
        strategy = strategy_tokens or self.strategy_tokens
        domains = self._resolve_domains(intent_category)
        ratios = self._apply_strategy_ratios(user_strategy)

        # 按比例分配策略层预算
        primary_tokens = int(strategy * ratios["primary"])
        aux1_tokens    = int(strategy * ratios["aux1"])
        aux2_tokens    = strategy - primary_tokens - aux1_tokens  # 避免舍入误差

        plan = BudgetPlan(
            mandatory_tokens=self.mandatory_tokens,
            strategy_tokens=strategy,
            flexible_tokens=self.flexible_tokens,
        )

        # 主域
        plan.strategy_plan.append(DomainBudget(
            domain=domains[0],
            role="primary",
            budget_tokens=primary_tokens,
        ))

        # 辅助域1
        plan.strategy_plan.append(DomainBudget(
            domain=domains[1],
            role="auxiliary",
            budget_tokens=aux1_tokens,
        ))

        # 辅助域2（可能为 None，如 casual 意图）
        if domains[2] is not None:
            plan.strategy_plan.append(DomainBudget(
                domain=domains[2],
                role="auxiliary",
                budget_tokens=aux2_tokens,
            ))
        else:
            # 无辅助域2时，其预算返还给主域
            plan.strategy_plan[0].budget_tokens += aux2_tokens
            plan.strategy_plan[0].remaining_tokens += aux2_tokens

        plan.compile_strategy = self._select_compile_strategy(plan)
        return plan

    def redistribute_surplus(self, plan: BudgetPlan) -> BudgetPlan:
        """预算重分配：域填不满时，剩余量给下一优先级域.

        设计文档 §5.3:
        - 某个域填不满 → 剩余给下一优先级域
        - 所有域都填不满 → 剩余返还给必要层（加长用户消息窗口）
        """
        for i in range(len(plan.strategy_plan) - 1):
            current = plan.strategy_plan[i]
            if current.remaining_tokens > 0:
                surplus = current.remaining_tokens
                next_domain = plan.strategy_plan[i + 1]
                next_domain.budget_tokens += surplus
                next_domain.remaining_tokens += surplus
                current.remaining_tokens = 0

        # 最后一域仍有剩余 → 返还给必要层
        last = plan.strategy_plan[-1]
        if last.remaining_tokens > 0:
            plan.mandatory_tokens += last.remaining_tokens
            last.remaining_tokens = 0

        return plan

    def _resolve_domains(self, intent_category: str) -> tuple:
        """解析意图对应的域组合."""
        return self._INTENT_DOMAIN_MAP.get(intent_category, ("E", "B", "P"))

    def _apply_strategy_ratios(self, user_strategy: Optional[str]) -> Dict[str, float]:
        """根据用户策略调整分配比例.

        设计文档 §10.4:
        - quality_first: 70/20/10
        - balanced:      60/25/15
        - cost_first:    50/25/舍弃辅助域2
        """
        if user_strategy == "quality_first":
            return {"primary": 0.70, "aux1": 0.20, "aux2": 0.10}
        if user_strategy == "cost_first":
            return {"primary": 0.50, "aux1": 0.25, "aux2": 0.25}
        return {"primary": self._PRIMARY_PCT, "aux1": self._AUX1_PCT, "aux2": self._AUX2_PCT}

    def _select_compile_strategy(self, plan: BudgetPlan) -> str:
        """根据预算填充预期选择编译策略.

        设计文档 §7.2:
        - primary_deep: 主域预算充足（>150 tokens）
        - balanced: 默认
        - summary_fallback: 策略层预算紧张（<200 tokens）
        """
        primary = plan.strategy_plan[0].budget_tokens if plan.strategy_plan else 0
        if primary > 150:
            return "primary_deep"
        if plan.strategy_tokens < 200:
            return "summary_fallback"
        return "balanced"
