# -*- coding: utf-8 -*-
"""
core/agent/gates.py
───────────────────
三层门控与双轨策略主入口（v2.4 新增）。

Gate-0: 极速门控（Hard Gate）— 硬规则匹配，0-2ms
Gate-1: 策略门控（PCR Gate）— 规则引擎完整评估，3-5ms
Gate-2: 编排门控（Orchestration Gate）— Router LLM 动态选择蓝图，30-200ms

默认轨道：Track-0（规则引擎），覆盖 95% 请求。
扩展轨道：Track-1（LLM 编排），仅在规则失效时触发。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.intent_parser import IntentParser
from core.agent.models import IntentContext, ParseContext, ParseResult

from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext
from core.agent.blueprints import (
    Blueprint, BLUEPRINT_ZERO, BLUEPRINT_REGISTRY, validate_blueprint_registry,
)
from core.agent.orchestrator import (
    BlueprintExecutor, RouterOutputValidator, RouterDecision, ExecutionResult,
)


@dataclass
class GateResult:
    """门控执行结果。"""
    track: str          # "track_0" | "track_1" | "fallback"
    blueprint_id: str
    execution_result: Optional[ExecutionResult] = None
    pcr_output: Optional[PCROutput_v1] = None
    latency_ms: float = 0.0
    trace: List[str] = field(default_factory=list)
    # 新增：反馈链路（用于 PCR 阈值自适应）
    was_accurate: Optional[bool] = None  # 用户反馈：这次决策是否正确
    required_clarification: bool = False  # 是否触发了澄清


# ═══════════════════════════════════════════════════════════════════════════════
# 阈值自适应（P0 修复：PCR 反馈闭环）
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveThresholds:
    """
    PCR 阈值自适应管理器。

    设计：每个会话独立维护自己的阈值，保护隐私。
    反馈信号：
      - 触发澄清 → 降低 noise_fast_path 阈值（更谨慎）
      - 直接成功 → 保持或略微提高阈值（更激进）
      - 用户反馈不准确 → 大幅调整阈值

    调整策略（指数加权移动平均，EMA alpha=0.3）：
      - 每次交互后，根据结果更新阈值
      - 阈值范围 clamp 在 [0.1, 0.9]，防止极端值
    """

    DEFAULTS = {
        "noise_fast_path": 0.30,     # Gate-0/1: noise < 阈值 → 快速通过
        "confidence_min": 0.80,      # Gate-0/1: confidence > 阈值 → 快速通过
        "complexity_tutorial": 0.50,   # Orchestration: complexity > 阈值 → 教程模式
        "noise_deep": 0.30,          # Orchestration: complexity > 0.7 and noise > 阈值 → 深度分析
    }

    # 调整步长
    DELTA_UP = 0.02     # 成功时提高阈值（更宽容）
    DELTA_DOWN = 0.05   # 失败时降低阈值（更谨慎）
    CLAMP_MIN = 0.10
    CLAMP_MAX = 0.90

    def __init__(self, overrides: Optional[Dict[str, float]] = None):
        self.thresholds = dict(self.DEFAULTS)
        if overrides:
            self.thresholds.update(overrides)
        # 反馈历史：(threshold_name, old_value, result_bool)
        self._feedback_buffer: List[Tuple[str, float, bool]] = []

    def get(self, key: str) -> float:
        return self.thresholds.get(key, self.DEFAULTS.get(key, 0.5))

    def feedback(self, required_clarification: bool, was_accurate: Optional[bool] = None) -> None:
        """
        接收反馈，调整阈值。

        :param required_clarification: 是否触发了澄清（True = 决策不够自信）
        :param was_accurate: 用户是否确认结果准确（True = 正确，False = 错误，None = 未知）
        """
        if was_accurate is False:
            # 用户明确说错了 → 大幅降低阈值（更谨慎）
            self._adjust("noise_fast_path", -self.DELTA_DOWN * 2)
            self._adjust("confidence_min", +self.DELTA_DOWN * 2)
        elif required_clarification:
            # 触发了澄清 → 决策不够自信 → 降低 noise_fast_path（更谨慎）
            self._adjust("noise_fast_path", -self.DELTA_DOWN)
            self._adjust("confidence_min", +self.DELTA_DOWN)
        elif was_accurate is True:
            # 用户确认正确 → 略微提高阈值（更激进）
            self._adjust("noise_fast_path", +self.DELTA_UP)
            self._adjust("confidence_min", -self.DELTA_UP)
        # 否则（was_accurate=None，无反馈）→ 不调整

    def _adjust(self, key: str, delta: float) -> None:
        """调整单个阈值，并 clamp。"""
        old = self.thresholds[key]
        new = max(self.CLAMP_MIN, min(self.CLAMP_MAX, old + delta))
        self.thresholds[key] = new
        self._feedback_buffer.append((key, old, new > old))

    def to_dict(self) -> Dict[str, float]:
        return dict(self.thresholds)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "AdaptiveThresholds":
        return cls(overrides=data)

    def __repr__(self) -> str:
        return f"AdaptiveThresholds({self.thresholds})"


# ═══════════════════════════════════════════════════════════════════════════════
# Gate-0: 极速门控（Hard Gate）
# ═══════════════════════════════════════════════════════════════════════════════

class HardGate:
    """
    基于硬规则（关键词 + 历史）的快速匹配。
    0-2ms，不调用任何引擎实例，不经过 LLM。
    """

    # 高置信度工具关键词（直接命中 → 100% TOOL）
    HIGH_CONFIDENCE_TOOL_PATTERNS = [
        r"^scan\b", r"^read\b", r"^write\b", r"^patch\b",
        r"^disassemble\b", r"^trace\b", r"^dump\b",
        r"^扫描", r"^读取", r"^写入", r"^修改", r"^追踪",
    ]

    @classmethod
    def evaluate(cls, text: str, history: List[Any]) -> Optional[GateResult]:
        import re
        text_lower = text.lower().strip()
        if not text_lower:
            return None

        # 1. 强关键词匹配（最简规则，零历史依赖）
        for pattern in cls.HIGH_CONFIDENCE_TOOL_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return GateResult(
                    track="track_0",
                    blueprint_id="RULE_FAST_PATH",
                    trace=["Gate-0: high-confidence tool keyword matched"],
                )

        # 2. 历史连续推断（如果上一轮是 TOOL + 本轮是代词/继续词）
        if history:
            last_entry = history[-1]
            exp = getattr(last_entry, "expectation", None) or last_entry.get("expectation", "UNKNOWN")
            if exp == "TOOL" and text_lower in ("continue", "go", "next", "继续", "下一步", "ok"):
                return GateResult(
                    track="track_0",
                    blueprint_id="RULE_FAST_PATH",
                    trace=["Gate-0: history continuity inferred"],
                )

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Gate-1: 策略门控（PCR Gate）
# ═══════════════════════════════════════════════════════════════════════════════

class PCRGate:
    """
    调用 RuleBasedPCR 完整评估，输出结构化认知包。
    如果输出满足低噪声 + 无歧义 + 已知意图，直接走 BLUEPRINT_ZERO。
    """

    @classmethod
    def evaluate(cls, text: str, history: List[Any],
                 pcr_instance: RuleBasedPCR,
                 adaptive: Optional[AdaptiveThresholds] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> Tuple[PCROutput_v1, Optional[GateResult]]:
        inp = PCRInput_v1(query=text, session_history=history, metadata=metadata or {})
        pcr_out = pcr_instance.evaluate(inp)

        # 使用自适应阈值（P0 修复：反馈闭环）
        noise_threshold = adaptive.get("noise_fast_path") if adaptive else 0.3
        confidence_threshold = adaptive.get("confidence_min") if adaptive else 0.8

        # 检查是否满足 Track-0 条件
        if (pcr_out.expectation != "UNKNOWN" and
            pcr_out.noise_level < noise_threshold and
            getattr(pcr_out, "confidence", 0.5) > confidence_threshold):
            return pcr_out, GateResult(
                track="track_0",
                blueprint_id="RULE_FAST_PATH",
                pcr_output=pcr_out,
                trace=[
                    f"Gate-1: PCR expectation={pcr_out.expectation}, "
                    f"noise={pcr_out.noise_level:.2f} < {noise_threshold:.2f}, "
                    f"confidence>{confidence_threshold:.2f} → Track-0"
                ],
            )

        return pcr_out, None


# ═══════════════════════════════════════════════════════════════════════════════
# Gate-2: 编排门控（Orchestration Gate）
# ═══════════════════════════════════════════════════════════════════════════════

class OrchestrationGate:
    """
    基于 Router LLM 或规则选择器动态选择 Blueprint。
    输入：PCR 结构化输出（非原文）。
    输出：Blueprint ID + 执行结果。
    """

    def __init__(self, executor: Optional[BlueprintExecutor] = None,
                 router_llm_fn: Optional[Any] = None):
        self.executor = executor or BlueprintExecutor()
        self.router_llm_fn = router_llm_fn  # 可选：LLM 调用函数

    def evaluate(self, text: str, history: List[Any],
                 pcr_out: PCROutput_v1,
                 pcr_instance: RuleBasedPCR,
                 parser_instance: IntentParser,
                 adaptive: Optional[AdaptiveThresholds] = None) -> GateResult:
        start_ms = time.time() * 1000

        # 1. 构建 ExecutionContext
        ctx = ExecutionContext(
            raw_input=text,
            history=history,
            pcr_instance=pcr_instance,
            parser_instance=parser_instance,
        )
        ctx.intent_context = IntentContext.from_pcr_output(pcr_out)

        # 2. 选择 Blueprint（默认：规则选择器，如果 router_llm_fn 存在则尝试）
        bp_id = self._select_blueprint(pcr_out, adaptive=adaptive)
        custom_tools: List[str] = []
        reason_code = "RULE_SELECTOR"

        # 如果配置了 LLM Router，尝试调用（生产环境中可选）
        if self.router_llm_fn is not None:
            llm_decision = self._call_router_llm(pcr_out)
            if llm_decision is not None:
                bp_id = llm_decision.blueprint_id
                custom_tools = llm_decision.custom_tools
                reason_code = llm_decision.reason_code
                ctx.router_decision = llm_decision

        blueprint = BLUEPRINT_REGISTRY.get(bp_id, BLUEPRINT_ZERO)

        # 3. 执行 Blueprint
        result = self.executor.execute(blueprint, ctx)

        # 4. 如果执行失败且返回 fallback，执行 fallback blueprint
        if result.status == "fallback" and result.fallback_to:
            fallback_bp = BLUEPRINT_REGISTRY.get(result.fallback_to, BLUEPRINT_ZERO)
            self.executor.reset()
            result = self.executor.execute(fallback_bp, ctx)
            result.fallback_to = fallback_bp.id

        latency_ms = (time.time() * 1000) - start_ms

        return GateResult(
            track="track_1" if blueprint.requires_llm else "track_0",
            blueprint_id=blueprint.id,
            execution_result=result,
            pcr_output=pcr_out,
            latency_ms=latency_ms,
            trace=[
                f"Gate-2: reason={reason_code}, selected={blueprint.id}, "
                f"status={result.status}, latency={latency_ms:.1f}ms"
            ],
        )

    def _select_blueprint(self, pcr_out: PCROutput_v1, adaptive: Optional[AdaptiveThresholds] = None) -> str:
        """
        基于规则的 Blueprint 选择器（默认实现，不依赖 LLM）。
        根据 PCR 输出特征选择最合适的预置蓝图。
        
        P0 修复：使用自适应阈值替代硬编码值。
        """
        expectation = pcr_out.expectation
        noise = pcr_out.noise_level
        complexity = pcr_out.complexity_level
        profile = pcr_out.cognitive_profile

        # 使用自适应阈值（默认回退到硬编码）
        noise_threshold = adaptive.get("noise_fast_path") if adaptive else 0.3
        complexity_tutorial_threshold = adaptive.get("complexity_tutorial") if adaptive else 0.5
        noise_deep_threshold = adaptive.get("noise_deep") if adaptive else 0.3

        # 高噪声 + 未知意图 → 直接 fallback 到规则路径（最安全）
        if expectation == "UNKNOWN" and noise > (0.7 if adaptive is None else 0.7):
            return "RULE_FAST_PATH"

        # 低元认知 + 中高复杂度 → 新手教程模式
        metacognition = getattr(profile, "metacognition", 0.0)
        if metacognition < 0.3 and complexity > complexity_tutorial_threshold:
            return "LLM_TUTORIAL"

        # 高复杂度 + 有噪声 → 深度分析（先澄清）
        if complexity > 0.7 and noise > noise_deep_threshold:
            return "LLM_DEEP"

        # 默认：规则快速路径
        return "RULE_FAST_PATH"

    def _call_router_llm(self, pcr_out: PCROutput_v1) -> Optional[RouterDecision]:
        """
        调用外部 Router LLM（可选）。
        如果未配置或调用失败，返回 None（降级到规则选择器）。
        """
        if self.router_llm_fn is None:
            return None

        try:
            # 构建结构化输入（不含原文）
            router_input = {
                "pcr_summary": {
                    "expectation": pcr_out.expectation,
                    "noise_level": pcr_out.noise_level,
                    "complexity_level": pcr_out.complexity_level,
                    "cognitive_profile": {
                        "metacognition": getattr(pcr_out.cognitive_profile, "metacognition", 0.0),
                        "stability": getattr(pcr_out.cognitive_profile, "stability", 0.0),
                    }
                },
                "available_blueprints": list(BLUEPRINT_REGISTRY.keys()),
            }
            raw_output = self.router_llm_fn(router_input)
            decision = RouterOutputValidator.validate(raw_output, list(BLUEPRINT_REGISTRY.keys()))
            return decision
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# DualTrackOrchestrator — 主入口
# ═══════════════════════════════════════════════════════════════════════════════

class DualTrackOrchestrator:
    """
    双轨策略主入口：编排三层门控，返回最终结果。

    使用方式：
        orchestrator = DualTrackOrchestrator(pcr, parser)
        result = orchestrator.process("scan memory at 0x1000", history=[])
    """

    def __init__(self,
                 pcr_instance: RuleBasedPCR,
                 parser_instance: IntentParser,
                 router_llm_fn: Optional[Any] = None,
                 enable_gate0: bool = True,
                 enable_gate2: bool = True):
        self.pcr = pcr_instance
        self.parser = parser_instance
        self.gate0 = HardGate() if enable_gate0 else None
        self.gate1 = PCRGate()
        self.gate2 = OrchestrationGate(router_llm_fn=router_llm_fn) if enable_gate2 else None

    def process(self, text: str, history: List[Any] = None, adaptive: Optional[AdaptiveThresholds] = None, metadata: Optional[Dict[str, Any]] = None) -> GateResult:
        """
        处理用户输入，按三层门控顺序执行：
        Gate-0 → Gate-1 → Gate-2（fallback）。
        
        P0 修复：支持自适应阈值传入。
        P1 修复：支持 metadata（含 user_type_hint）传入 PCR。
        """
        history = history or []
        start_ms = time.time() * 1000
        trace: List[str] = []

        # ── Gate-0: 极速门控 ─────────────────────────────────────
        if self.gate0 is not None:
            g0 = self.gate0.evaluate(text, history)
            if g0 is not None:
                g0.latency_ms = (time.time() * 1000) - start_ms
                g0.trace = trace + g0.trace + [f"Total latency: {g0.latency_ms:.2f}ms"]
                return g0

        # ── Gate-1: 策略门控（PCR）────────────────────────────────
        pcr_out, g1 = self.gate1.evaluate(text, history, self.pcr, adaptive=adaptive, metadata=metadata)
        trace.append(
            f"Gate-1: PCR expectation={pcr_out.expectation}, "
            f"noise={pcr_out.noise_level:.2f}"
        )
        if g1 is not None:
            g1.latency_ms = (time.time() * 1000) - start_ms
            g1.trace = trace + g1.trace
            return g1

        # ── Gate-2: 编排门控（Router / Executor）──────────────────
        if self.gate2 is not None:
            g2 = self.gate2.evaluate(text, history, pcr_out,
                                     self.pcr, self.parser, adaptive=adaptive)
            g2.trace = trace + g2.trace
            return g2

        # ── 最终 Fallback：直接返回 BLUEPRINT_ZERO ─────────────────
        return GateResult(
            track="fallback",
            blueprint_id="RULE_FAST_PATH",
            pcr_output=pcr_out,
            latency_ms=(time.time() * 1000) - start_ms,
            trace=trace + ["All gates bypassed → fallback to RULE_FAST_PATH"],
        )
