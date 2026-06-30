# -*- coding: utf-8 -*-
"""
core/agent/blueprints.py
────────────────────────
Blueprint 定义 + 默认库 + 启动校验（v2.4 新增）。

Blueprint 定义**固定的、不可变的**工具执行序列 + 准入条件。
LLM 只能**选择**已注册的 Blueprint，不能**发明**新的执行计划。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from core.agent.tools.cognitive_tools import CognitiveTools


@dataclass(frozen=True)
class Blueprint:
    """
    策略蓝图：预定义的工具执行序列 + 准入条件 + 元数据。
    支持子蓝图嵌套，实现复杂策略的分层组合。

    frozen=True：运行时不可修改，防止 LLM 注入篡改。
    """
    id: str
    description: str
    steps: List[Union[str, "Blueprint"]]
    gate: str                    # 准入条件（伪代码，供 Executor / Gate 解析）
    latency_budget_ms: int
    requires_llm: bool = False   # 是否含 LLM 调用工具（用于配额/计费）
    fallback_id: Optional[str] = None  # 执行失败时的降级蓝图 ID
    max_nesting_depth: int = 3   # 最大嵌套深度限制

    # 手动定义 __init__ 以支持 strategy_steps 向后兼容（dataclass 不生成）
    def __init__(
        self,
        id: str,
        description: str,
        steps: Optional[List[Union[str, "Blueprint"]]] = None,
        strategy_steps: Optional[List[str]] = None,
        gate: str = "",
        latency_budget_ms: int = 0,
        requires_llm: bool = False,
        fallback_id: Optional[str] = None,
        max_nesting_depth: int = 3,
    ):
        # steps 优先；strategy_steps 为向后兼容别名（v2.4 前使用 strategy_steps）
        actual_steps = steps if steps is not None else (strategy_steps or [])
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "steps", actual_steps)
        object.__setattr__(self, "gate", gate)
        object.__setattr__(self, "latency_budget_ms", latency_budget_ms)
        object.__setattr__(self, "requires_llm", requires_llm)
        object.__setattr__(self, "fallback_id", fallback_id)
        object.__setattr__(self, "max_nesting_depth", max_nesting_depth)

    # 向后兼容：strategy_steps 作为 steps 的别名（已废弃）
    @property
    def strategy_steps(self) -> List[str]:
        """兼容旧代码：返回所有步骤中的字符串（工具名）。"""
        return [s for s in self.steps if isinstance(s, str)]

    def validate_tools(self, known_blueprints: Optional[Dict[str, "Blueprint"]] = None) -> None:
        """校验所有步骤合法（工具名已注册或子蓝图已存在）。启动时调用。"""
        registered = CognitiveTools.list_registered()
        bp_registry = known_blueprints or {}
        for step in self.steps:
            if isinstance(step, str):
                if step not in registered and step not in bp_registry:
                    raise ValueError(
                        f"Blueprint '{self.id}' references unknown tool/blueprint: {step}"
                    )
            elif isinstance(step, Blueprint):
                step.validate_tools(known_blueprints=bp_registry)
            else:
                raise ValueError(f"Blueprint '{self.id}' has invalid step type: {type(step)}")

    def expand(self, known_blueprints: Optional[Dict[str, "Blueprint"]] = None, depth: int = 0) -> List[str]:
        """递归展开嵌套蓝图为扁平工具序列。"""
        if depth > self.max_nesting_depth:
            raise ValueError(f"Blueprint '{self.id}' exceeds max nesting depth {self.max_nesting_depth}")
        bp_registry = known_blueprints or {}
        flat: List[str] = []
        for step in self.steps:
            if isinstance(step, str):
                if step in bp_registry:
                    flat.extend(bp_registry[step].expand(bp_registry, depth + 1))
                else:
                    flat.append(step)
            elif isinstance(step, Blueprint):
                flat.extend(step.expand(bp_registry, depth + 1))
        return flat



# ── 预置默认蓝图库 ───────────────────────────────────────────────────

BLUEPRINT_ZERO = Blueprint(
    id="RULE_FAST_PATH",
    description=(
        "现有规则引擎的完整流水线，不做任何 LLM 决策。"
        "这是默认路径，覆盖 95% 请求。"
    ),
    steps=[
        "pcr_evaluate",
        "intent_parser_full_pipeline",
    ],
    gate="pcr.confidence > 0.9 and pcr.noise < 0.3",
    latency_budget_ms=5,
    requires_llm=False,
    fallback_id=None,
)

BLUEPRINT_TUTORIAL = Blueprint(
    id="LLM_TUTORIAL",
    description=(
        "新手模式：强制解释 + 逐步引导。"
        "适用于低元认知 + 中高复杂度。"
    ),
    steps=[
        "pcr_evaluate",
        "extract_entities",
        "detect_ambiguities",
        "llm_generate_explanation",  # LLM 调用点
        "build_task_graph",
    ],
    gate="profile.metacognition < 0.3 and complexity > 0.5",
    latency_budget_ms=200,
    requires_llm=True,
    fallback_id="RULE_FAST_PATH",
)

BLUEPRINT_DEEP = Blueprint(
    id="LLM_DEEP",
    description=(
        "深度分析模式：先歧义消解，再构建 TaskGraph。"
        "适用于高复杂度 + 存在实体歧义。"
    ),
    steps=[
        "pcr_evaluate",
        "extract_entities",
        "detect_ambiguities",
        "ask_user",                    # 先澄清，再构建
        "build_task_graph",
    ],
    gate="complexity > 0.7 and ambiguities != []",
    latency_budget_ms=500,
    requires_llm=False,  # ask_user 是规则生成，不含 LLM
    fallback_id="LLM_TUTORIAL",
)

BLUEPRINT_CUSTOM = Blueprint(
    id="LLM_CUSTOM",
    description=(
        "Router LLM 动态选择工具组合。"
        "仅在规则完全失效时启用。"
    ),
    steps=[],  # 由 Router LLM 在 custom_modifiers 中指定
    gate="pcr.expectation == UNKNOWN",
    latency_budget_ms=500,
    requires_llm=True,
    fallback_id="RULE_FAST_PATH",
)


# ── 蓝图注册表 ───────────────────────────────────────────────────────

BLUEPRINT_REGISTRY: Dict[str, Blueprint] = {
    b.id: b for b in [BLUEPRINT_ZERO, BLUEPRINT_TUTORIAL, BLUEPRINT_DEEP, BLUEPRINT_CUSTOM]
}


def validate_blueprint_registry() -> None:
    """
    启动时校验所有 Blueprint。
    - 检查 steps 中的工具名/子蓝图已注册
    - 检查 fallback_id 指向已存在的蓝图
    - 检查嵌套深度不超限
    """
    for bp in BLUEPRINT_REGISTRY.values():
        # 1. 校验工具/子蓝图
        bp.validate_tools(known_blueprints=BLUEPRINT_REGISTRY)

        # 2. 校验 fallback
        if bp.fallback_id and bp.fallback_id not in BLUEPRINT_REGISTRY:
            raise ValueError(
                f"Blueprint '{bp.id}' fallback_id '{bp.fallback_id}' "
                f"not found in BLUEPRINT_REGISTRY"
            )

        # 3. 校验展开后深度（触发循环依赖检测）
        try:
            bp.expand(known_blueprints=BLUEPRINT_REGISTRY)
        except ValueError as exc:
            raise ValueError(f"Blueprint '{bp.id}' expansion failed: {exc}") from exc

    # 4. 检查 RULE_FAST_PATH 存在（必须）
    if "RULE_FAST_PATH" not in BLUEPRINT_REGISTRY:
        raise ValueError("BLUEPRINT_REGISTRY must contain 'RULE_FAST_PATH'")



# 启动时自动校验（导入即校验）
validate_blueprint_registry()
