# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/orchestrator.py
────────────────────────────────────────────
DialogMesh Agent v3.0 — 多层 LLM 认知编排器（Orchestrator）。

用途：
- 整合 6 个 LLM 实例（PCR → Intent → Planning → Meta-Cognitive → Answer + Reflective），
  形成完整的认知双工流水线。
- 协调算法引擎与 LLM 引擎的并行执行，通过融合引擎加权融合。
- 所有耗时操作均为异步，不阻塞事件循环。
- 与 CognitiveCompiler、ContextManager、Observability、ToolRegistry 深度集成。

处理流程（单轮）：
  1. PCR Analysis   (PCR-LLM ∥ Algorithm PCR)
  2. Intent Parsing   (Intent-LLM ∥ Algorithm IntentParser)
  3. Planning         (PlanningSkill → TaskGraph)
  4. Execution      (ToolRegistry → 工具执行)
  5. Answer         (Answer-LLM 读取 Cognitive Tree 活跃分支)
  6. Meta-Cognitive (异步，验证本轮输出)
  7. Reflective     (异步，跨轮复盘)

设计原则：
- 每个 LLM 调用后，通过 CognitiveCompiler 将结果写入 Cognitive Tree。
- 超时/失败时自动降级到算法引擎或规则引擎。
- 遥测：每个 phase 记录 latency、confidence、error。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from core.agent.models import IntentCategory, TaskStatus
from core.agent.v3_0.cognitive_compiler.compiler import CognitiveCompiler
from core.agent.v3_0.cognitive_compiler.event_bus import EventBus
from core.agent.v3_0.cognitive_compiler.meta_cognitive import MetaCognitiveValidator
from core.agent.v3_0.cognitive_compiler.reflective import ReflectiveAnalyzer
from core.agent.v3_0.cognitive_compiler.profile_updater import ProfileUpdater
from core.agent.v3_0.cognitive_compiler.expertise_probe_v3 import ColdStartProbe
from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
    CogType,
)
from core.agent.v3_0.context_manager.manager import ContextManager
from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    IntentContext_v3,
    Intent_v3,
    TaskGraph_v3,
    TaskNode_v3,
    UserMessage_v3,
    WebSocketEvent,
)
from core.agent.v3_0.llm_providers.base import GenerateRequest_v3, GenerateResult_v3
from core.agent.v3_0.observability.telemetry import Telemetry
from core.agent.v3_0.planning.planner import PlanningSkill
from core.agent.v3_0.planning.models import PlanResult
from core.agent.v3_0.tool_registry.registry import ToolRegistry
from core.agent.v3_0.orchestrator.algorithm_engine import AlgorithmEngine
from core.agent.v3_0.orchestrator.fusion_engine import FusionEngine, FusionStrategy
from core.agent.v3_0.orchestrator.hybrid_engine import HybridEngine
from core.agent.v3_0.llm_providers.llm_instances import (
    PCRLLM,
    IntentLLM,
    PlanningLLM,
    MetaCognitiveLLM,
    ReflectiveLLM,
    AnswerLLM,
)


from core.agent.v3_0.orchestrator.models import (
    FusionResult,
    FusionSource,
    LLMInstanceResult,
    OrchestratorConfig,
    OrchestratorResult,
    TurnContext,
    TurnPhase,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# LLM 实例封装
# ═══════════════════════════════════════════════════════════════════════════

class Orchestrator:
    """DialogMesh v3.0 多层 LLM 认知编排器。

    整合 6 个 LLM 实例，按以下顺序处理每轮用户输入：
      1. PCR Analysis   (并行：PCR-LLM + Algorithm PCR)
      2. Intent Parsing (并行：Intent-LLM + Algorithm IntentParser)
      3. Planning       (PlanningSkill，依赖 Intent 输出)
      4. Execution      (ToolRegistry，依赖 Planning 输出)
      5. Answer         (Answer-LLM，读取 Cognitive Tree 活跃分支)
      6. Meta-Cognitive (异步后台验证)
      7. Reflective     (异步后台复盘)

    Args:
        config: 编排器配置
        llm_provider: LLM Provider 或 ProviderManager
        cognitive_compiler: 认知编译器
        context_manager: 上下文管理器
        planning_skill: 规划技能
        tool_registry: 工具注册中心
        observability: 可观测性门面
        event_bus: 事件总线
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        llm_provider: Optional[Any] = None,
        cognitive_compiler: Optional[CognitiveCompiler] = None,
        context_manager: Optional[ContextManager] = None,
        planning_skill: Optional[PlanningSkill] = None,
        tool_registry: Optional[ToolRegistry] = None,
        observability: Optional[Telemetry] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config or OrchestratorConfig()
        self.provider = llm_provider
        self.compiler = cognitive_compiler
        self.context_manager = context_manager
        self.planning_skill = planning_skill
        self.tool_registry = tool_registry
        self.observability = observability
        self.event_bus = event_bus or EventBus()

        # 算法引擎（降级 fallback）
        self.algorithm_engine = AlgorithmEngine()

        # 融合引擎
        self.fusion_engine = FusionEngine(self.config)
        # 算法引擎（认知双工快思考层）
        self.algorithm_engine = AlgorithmEngine()
        # 认知双工引擎
        self.meta_validator = MetaCognitiveValidator()
        self.reflective_analyzer = ReflectiveAnalyzer()
        self.profile_updater = ProfileUpdater()
        self.cold_start_probe = ColdStartProbe()

        self.hybrid_engine = HybridEngine(
            algorithm_engine=self.algorithm_engine,
            fusion_engine=self.fusion_engine,
            high_confidence_threshold=self.config.fusion_high_threshold,
            low_confidence_threshold=self.config.fusion_low_threshold,
            llm_timeout_ms=self.config.pcr_timeout_ms,
        )


        # LLM 实例缓存
        self._llm_instances: Dict[str, LLMInstance] = {}
        self._init_llm_instances()
        # LLMEngine 实例（新版本子类）
        self._llm_engines: Dict[str, Any] = {}
        self._init_llm_engines()


        # 状态
        self._closed = False
        self._turn_counter = 0

        logger.info("Orchestrator initialized (v3.0.0)")

    # ── 初始化 ────────────────────────────────────────────────────────────

    def _init_llm_instances(self) -> None:
        """初始化 6 个 LLM 实例的封装。"""
        if not self.provider or not self.compiler:
            logger.warning("LLM provider or compiler not provided, LLM instances disabled")
            return

        templates = self._get_prompt_templates()
        instance_configs = [
            ("PCR-LLM", CogType.PERCEPTION, self.config.enable_pcr_llm, templates["pcr"]),
            ("Intent-LLM", CogType.HYPOTHESIS, self.config.enable_intent_llm, templates["intent"]),
            ("Planning-LLM", CogType.REASONING, self.config.enable_planning_llm, templates["planning"]),
            ("Meta-Cognitive-LLM", CogType.VALIDATION, self.config.enable_meta_cognitive_llm, templates["meta_cognitive"]),
            ("Reflective-LLM", CogType.REFLECTION, self.config.enable_reflective_llm, templates["reflective"]),
            ("Answer-LLM", CogType.COMMUNICATION, self.config.enable_answer_llm, templates["answer"]),
        ]

        for name, cog_type, enabled, template in instance_configs:
            if enabled:
                self._llm_instances[name] = LLMInstance(
                    name=name,
                    provider=self.provider,
                    cognitive_compiler=self.compiler,
                    config=self.config,
                    cog_type=cog_type,
                    prompt_template=template,
                )
                logger.debug("LLM instance initialized: %s", name)

    def _get_prompt_templates(self) -> Dict[str, str]:
        """获取 6 个 LLM 实例的 Prompt 模板。

        对应工程文档: ENGINEERING_MULTILAYER_LLM.md §5.3
        """
        return {
            "pcr": """你是一位认知分析师，负责分析用户输入的语义特征。

输入："{user_input}"
上下文：{context}

请输出 JSON：
{{
  "noise_analysis": {{
    "semantic_noise": 0.0-1.0,
    "structural_noise": 0.0-1.0,
    "referential_noise": 0.0-1.0
  }},
  "expectation_inference": {{
    "primary": "TOOL|ADVISOR|COMPANION|UNKNOWN",
    "confidence": 0.0-1.0,
    "reasoning": "..."
  }},
  "cognitive_snapshot": {{
    "metacognition": 0.0-1.0,
    "divergence": 0.0-1.0,
    "stability": 0.0-1.0
  }},
  "confidence": 0.0-1.0
}}""",

            "intent": """你是一位意图分析师，负责从用户输入中提取深层意图和隐含实体。

输入："{user_input}"
已提取实体：{entities}
对话历史（最近 3 轮）：{history}

请输出 JSON：
{{
  "intent_inference": {{
    "primary_intent": "...",
    "confidence": 0.0-1.0,
    "implied_entities": [{{"type": "...", "value": "...", "reasoning": "..."}}],
    "ambiguity_assessment": "..."
  }},
  "confidence": 0.0-1.0
}}""",

            "planning": """你是一位规划师，负责根据意图和可用工具生成任务计划。

意图：{intent}
可用工具：{tools}
用户画像：{profile}

请输出 JSON：
{{
  "plan": {{
    "mode": "DYNAMIC|SKILL_ENHANCED|MIXED",
    "nodes": [{{"name": "...", "tool": "...", "params": {{}}}}],
    "alternatives": [{{"name": "...", "confidence": 0.0-1.0}}]
  }},
  "confidence": 0.0-1.0
}}""",

            "meta_cognitive": """你是一位元认知监督者，负责验证推理质量。

待验证节点：{node_content}
节点类型：{node_type}
来源 LLM：{source_llm}
相关证据节点：{evidence_nodes}

请输出 JSON：
{{
  "factuality_check": {{"score": 0.0-1.0, "reasoning": "..."}},
  "consistency_check": {{"score": 0.0-1.0, "conflicting_nodes": [...], "reasoning": "..."}},
  "plausibility_check": {{"score": 0.0-1.0, "reasoning": "..."}},
  "hallucination_risk": 0.0-1.0,
  "recommendation": "VALIDATE|INVALIDATE|REQUEST_CLARIFICATION",
  "confidence": 0.0-1.0
}}""",

            "reflective": """你是一位系统复盘师，分析长期模式并生成改进策略。

会话范围：{session_range}
Cognitive Tree 统计：{tree_stats}
检测到的偏见：{biases}

请输出 JSON：
{{
  "bias_analysis": {{"findings": [...], "severity": "low|medium|high"}},
  "blind_spot_analysis": {{"findings": [...], "recommendation": "..."}},
  "profile_update_strategy": {{"track_a_changes": {{...}}, "track_b_corrections": [...]}},
  "learning_strategies": [{{"type": "PARAMETER|RULE|SKILL|LLM|ARCHITECTURE", "description": "..."}}],
  "confidence": 0.0-1.0
}}""",

            "answer": """你是 DialogMesh 的回答生成器，综合所有认知层输出生成回复。

用户输入：{user_input}
用户画像：{user_profile}

系统认知状态：
- 算法结果：{algorithm_result}
- LLM 结果：{llm_result}
- 融合模式：{fusion_mode}
- 系统置信度：{system_confidence}

活跃推理链：{active_cognitive_branch}

约束：
- 回复风格：{style}
- 最大长度：{max_length}
- 如果系统置信度 < 0.7，必须在回复中声明不确定性。

请输出 JSON：
{{
  "response": "...",
  "confidence": 0.0-1.0,
  "honesty_declared": true|false,
  "cited_nodes": [...],
  "fallback_reason": "..."
}}""",
        }

    # ── 公共 API ───────────────────────────────────────────────────────────

    async def process_turn(
        self,
        session_id: str,
        user_input: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """处理单轮用户输入——编排器主入口。

        Args:
            session_id: 会话 ID
            user_input: 用户原始输入
            metadata: 可选的附加元数据

        Returns:
            OrchestratorResult：包含回复、意图、任务图、遥测数据
        """
        if self._closed:
            return OrchestratorResult(
                success=False,
                status="error",
                answer="Orchestrator is closed",
                errors=["Orchestrator is closed"],
            )

        self._turn_counter += 1
        turn_id = f"{session_id}-t{self._turn_counter}"
        start_time = time.time()

        turn_ctx = TurnContext(
            turn_id=turn_id,
            session_id=session_id,
            user_input=user_input,
        )
        turn_ctx.add_trace(f"Turn started: input={user_input[:50]}")

        # 记录用户消息到 ContextManager
        if self.context_manager:
            try:
                # 确保 session 已创建
                existing = await self.context_manager.get_session(session_id)
                if existing is None:
                    await self.context_manager.create_session(
                        user_id=session_id, session_id=session_id
                    )
                user_msg = UserMessage_v3(session_id=session_id, content=user_input)
                await self.context_manager.add_user_message(session_id, user_msg)
            except Exception as exc:
                logger.warning("Failed to add user message to context: %s", exc)

        # 启动遥测 trace
        trace = None
        if self.observability:
            trace = await self.observability.start_trace(session_id, self._turn_counter, user_input)

        try:
            # ── Phase 1: PCR Analysis ──
            await self._phase_pcr(turn_ctx)

            # ── Phase 2: Intent Parsing ──
            await self._phase_intent(turn_ctx)

            # ── Phase 3: Planning ──
            await self._phase_planning(turn_ctx)

            # ── Phase 4: Execution ──
            await self._phase_execution(turn_ctx)

            # ── Phase 5: Answer Generation ──
            await self._phase_answer(turn_ctx)

            # ── Phase 6: Meta-Cognitive (异步后台) ──
            asyncio.create_task(self._phase_meta_cognitive(turn_ctx))

            # ── Phase 7: Reflective (异步后台) ──
            asyncio.create_task(self._phase_reflective(turn_ctx))

            turn_ctx.finish()
            logger.info("Turn %s completed in %.1fms", turn_id, (time.time() - start_time) * 1000)

        except Exception as exc:
            logger.error("Turn %s failed: %s", turn_id, exc)
            turn_ctx.add_error(str(exc))
            turn_ctx.current_phase = TurnPhase.FAILED

        # 构建最终结果
        result = self._build_result(turn_ctx, start_time)

        # 记录 Agent 回复到 ContextManager
        if self.context_manager and result.answer:
            try:
                agent_msg = result.to_agent_message()
                await self.context_manager.add_agent_message(session_id, agent_msg)
            except Exception as exc:
                logger.warning("Failed to add agent message to context: %s", exc)

        # 结束遥测 trace
        if self.observability and trace:
            try:
                await self.observability.end_trace(
                    intent=result.intent.category.value if result.intent else "unknown",
                    confidence=result.answer_confidence,
                    execution_status=result.status,
                )
            except Exception as exc:
                logger.warning("Failed to end telemetry trace: %s", exc)

        return result

    # ── Phase 实现 ────────────────────────────────────────────────────────

    async def _phase_pcr(self, turn_ctx: TurnContext) -> None:
        """PCR 分析阶段——并行运行 PCR-LLM 和算法引擎。"""
        phase_start = time.time()
        turn_ctx.current_phase = TurnPhase.PCR_ANALYSIS
        turn_ctx.add_trace("Phase: PCR Analysis started")

        # 构建上下文
        context_data = {"user_input": turn_ctx.user_input, "context": "{}", "history": "[]"}

        # 使用 HybridEngine 并行执行
        if hasattr(self, "hybrid_engine"):
            llm_coro = lambda: self._run_llm("PCR-LLM", turn_ctx.session_id, context_data, timeout_ms=self.config.pcr_timeout_ms)
            fusion = await self.hybrid_engine.process_pcr(turn_ctx.user_input, llm_coro)
        else:
            # 回退：原有并行路径
            algo_future = asyncio.create_task(self._run_algorithm_pcr(turn_ctx.user_input))
            llm_future = asyncio.create_task(self._run_llm("PCR-LLM", turn_ctx.session_id, context_data, timeout_ms=self.config.pcr_timeout_ms))
            algo_result, llm_result = await asyncio.gather(algo_future, llm_future, return_exceptions=True)
            if isinstance(algo_result, Exception):
                algo_result = None
            if isinstance(llm_result, Exception):
                llm_result = None
            fusion = self.fusion_engine.fuse(algo_result, llm_result)
        turn_ctx.pcr_result = fusion.output or {}

        # 构建 IntentContext_v3
        snapshot = turn_ctx.pcr_result.get("cognitive_snapshot", {})
        expectation = turn_ctx.pcr_result.get("expectation_inference", {})
        noise = turn_ctx.pcr_result.get("noise_analysis", {})

        turn_ctx.intent_context = IntentContext_v3(
            expectation=expectation.get("primary", "unknown").lower(),
            noise_level=noise.get("semantic_noise", 0.0),
            complexity_level=noise.get("structural_noise", 0.0),
            cognitive_profile={
                "metacognition": snapshot.get("metacognition", 0.5),
                "divergence": snapshot.get("divergence", 0.5),
                "stability": snapshot.get("stability", 0.5),
                "confidence": expectation.get("confidence", 0.5),
            },
        )

        # 冷启动专业度探测：调整认知快照
        if hasattr(self, "cold_start_probe") and self.cold_start_probe:
            try:
                probe_result = self.cold_start_probe.probe(turn_ctx.user_input)
                if probe_result.get("overall_expertise", 0) > 0.5:
                    cs = probe_result.get("cognitive_snapshot", {})
                    if cs:
                        profile = turn_ctx.intent_context.cognitive_profile or {}
                        profile["metacognition"] = cs.get("metacognition", profile.get("metacognition", 0.5))
                        profile["divergence"] = cs.get("divergence", profile.get("divergence", 0.5))
                        profile["stability"] = cs.get("stability", profile.get("stability", 0.5))
                        profile["expertise_score"] = probe_result.get("expertise_score", 0.5)
                        profile["technical_level"] = probe_result.get("technical_level", "low")
                        turn_ctx.intent_context.cognitive_profile = profile
                        turn_ctx.add_trace("ColdStartProbe expertise=" + str(probe_result.get("overall_expertise", 0)))
            except Exception as exc:
                logger.warning("ColdStartProbe failed: %s", exc)

        latency_ms = (time.time() - phase_start) * 1000.0
        turn_ctx.mark_phase(TurnPhase.PCR_ANALYSIS, latency_ms)
        turn_ctx.add_trace(f"Phase: PCR Analysis completed (fusion={fusion.source.value}, conf={fusion.confidence:.2f})")

    async def _phase_intent(self, turn_ctx: TurnContext) -> None:
        """意图解析阶段——并行运行 Intent-LLM 和算法引擎。"""
        phase_start = time.time()
        turn_ctx.current_phase = TurnPhase.INTENT_PARSING
        turn_ctx.add_trace("Phase: Intent Parsing started")

        context_data = {
            "user_input": turn_ctx.user_input,
            "entities": "[]",
            "history": "[]",
            "pcr_result": str(turn_ctx.pcr_result) if turn_ctx.pcr_result else "{}",
        }

        # 使用 HybridEngine 并行执行
        if hasattr(self, "hybrid_engine"):
            llm_coro = lambda: self._run_llm("Intent-LLM", turn_ctx.session_id, context_data, timeout_ms=self.config.intent_timeout_ms)
            fusion = await self.hybrid_engine.process_intent(turn_ctx.user_input, llm_coro)
        else:
            # 回退：原有并行路径
            algo_future = asyncio.create_task(self._run_algorithm_intent(turn_ctx.user_input))
            llm_future = asyncio.create_task(self._run_llm("Intent-LLM", turn_ctx.session_id, context_data, timeout_ms=self.config.intent_timeout_ms))
            algo_result, llm_result = await asyncio.gather(algo_future, llm_future, return_exceptions=True)
            if isinstance(algo_result, Exception):
                algo_result = None
            if isinstance(llm_result, Exception):
                llm_result = None
            fusion = self.fusion_engine.fuse(algo_result, llm_result)

        # 从融合结果构建 Intent_v3
        intent_inference = fusion.output.get("intent_inference", {}) if fusion.output else {}
        primary_intent = intent_inference.get("primary_intent", "UNKNOWN")
        try:
            category = IntentCategory(primary_intent.lower())
        except ValueError:
            category = IntentCategory.UNKNOWN

        turn_ctx.intent_result = Intent_v3(
            category=category,
            raw_input=turn_ctx.user_input,
            confidence=fusion.confidence,
        )

        latency_ms = (time.time() - phase_start) * 1000.0
        turn_ctx.mark_phase(TurnPhase.INTENT_PARSING, latency_ms)
        turn_ctx.add_trace(f"Phase: Intent Parsing completed (intent={category.value}, conf={fusion.confidence:.2f})")

    async def _phase_planning(self, turn_ctx: TurnContext) -> None:
        """规划阶段——使用 PlanningSkill 生成任务图（算法侧使用 HybridEngine 加速）。"""
        phase_start = time.time()
        turn_ctx.current_phase = TurnPhase.PLANNING
        turn_ctx.add_trace("Phase: Planning started")

        if not turn_ctx.intent_result:
            turn_ctx.add_trace("Phase: Planning skipped (no intent)")
            turn_ctx.mark_phase(TurnPhase.PLANNING, (time.time() - phase_start) * 1000.0)
            return

        # 使用 HybridEngine 并行执行算法规划 + Planning-LLM（如果可用）
        if hasattr(self, "hybrid_engine") and self.hybrid_engine and self.planning_skill:
            try:
                # 算法侧：基于规则的快速规划
                intent_cat = turn_ctx.intent_result.category.value if turn_ctx.intent_result else "UNKNOWN"
                user_input = turn_ctx.user_input
                algo_plan = self.algorithm_engine.generate_plan(intent_cat, user_input) if hasattr(self, "algorithm_engine") else {}
                
                # LLM侧：完整的 PlanningSkill
                plan_result: PlanResult = await self.planning_skill.plan(
                    intent=turn_ctx.intent_result,
                    intent_context=turn_ctx.intent_context,
                )
                
                if plan_result.success and plan_result.task_graph:
                    turn_ctx.task_graph = plan_result.task_graph
                    turn_ctx.add_trace(f"Phase: Planning success (nodes={len(plan_result.task_graph.nodes)})")
                    step_count = len(algo_plan.get("steps", []))
                    step_count = len(algo_plan.get("steps", []))
                    turn_ctx.add_trace("Phase: Algorithm plan generated (" + str(step_count) + " steps)")
                else:
                    turn_ctx.add_trace(f"Phase: Planning failed, using algorithm fallback")
                    self._fallback_task_graph(turn_ctx)
            except Exception as exc:
                logger.error(f"Planning with HybridEngine failed: {exc}")
                turn_ctx.add_error(f"Planning failed: {exc}")
                self._fallback_task_graph(turn_ctx)
        elif self.planning_skill:
            try:
                plan_result: PlanResult = await self.planning_skill.plan(
                    intent=turn_ctx.intent_result,
                    intent_context=turn_ctx.intent_context,
                )
                if plan_result.success and plan_result.task_graph:
                    turn_ctx.task_graph = plan_result.task_graph
                    turn_ctx.add_trace(f"Phase: Planning success (nodes={len(plan_result.task_graph.nodes)})")
                else:
                    turn_ctx.add_trace(f"Phase: Planning failed ({plan_result.error})")
                    self._fallback_task_graph(turn_ctx)
            except Exception as exc:
                logger.error(f"Planning failed: {exc}")
                turn_ctx.add_error(f"Planning failed: {exc}")
                self._fallback_task_graph(turn_ctx)
        else:
            turn_ctx.add_trace("Phase: Planning skipped (no planning_skill)")
            self._fallback_task_graph(turn_ctx)

        latency_ms = (time.time() - phase_start) * 1000.0
        turn_ctx.mark_phase(TurnPhase.PLANNING, latency_ms)

    def _fallback_task_graph(self, turn_ctx: TurnContext) -> None:
        """规划失败的降级路径：生成单任务任务图。"""
        from core.agent.v3_0.data_models import TaskGraph_v3, TaskNode_v3
        intent_id = turn_ctx.intent_result.id if turn_ctx.intent_result else None
        tg = TaskGraph_v3(intent_id=intent_id)
        node = TaskNode_v3(name="fallback_execution", goal=f"Execute intent", layer=2)
        tg.add_node(node)
        turn_ctx.task_graph = tg
        turn_ctx.add_trace("Phase: Planning fallback to single task")
    async def _phase_execution(self, turn_ctx: TurnContext) -> None:
        """执行阶段——遍历任务图并调用工具。"""
        phase_start = time.time()
        turn_ctx.current_phase = TurnPhase.EXECUTION
        turn_ctx.add_trace("Phase: Execution started")

        if not turn_ctx.task_graph:
            turn_ctx.add_trace("Phase: Execution skipped (no task graph)")
            turn_ctx.mark_phase(TurnPhase.EXECUTION, (time.time() - phase_start) * 1000.0)
            return

        # 简化执行：拓扑排序后依次执行就绪节点
        try:
            ready_nodes = await turn_ctx.task_graph.async_get_ready_nodes()
            execution_results = []
            for node in ready_nodes:
                if node.tool_name and self.tool_registry:
                    tool_def = await self.tool_registry.get(node.tool_name)
                    if tool_def:
                        # 模拟工具执行（实际应调用 ToolExecutor）
                        result = {"tool": node.tool_name, "params": node.tool_params, "status": "simulated"}
                        execution_results.append(result)
                        node.mark_success(result)
                    else:
                        node.mark_success({"tool": node.tool_name, "status": "not_found"})
                else:
                    node.mark_success({"status": "no_tool"})

            turn_ctx.execution_result = {"results": execution_results, "count": len(execution_results)}
            turn_ctx.add_trace(f"Phase: Execution completed ({len(execution_results)} nodes)")
        except Exception as exc:
            logger.error("Execution failed: %s", exc)
            turn_ctx.add_error(f"Execution failed: {exc}")

        latency_ms = (time.time() - phase_start) * 1000.0
        turn_ctx.mark_phase(TurnPhase.EXECUTION, latency_ms)

    async def _phase_answer(self, turn_ctx: TurnContext) -> None:
        """回复生成阶段——Answer-LLM 综合所有输出生成回复。"""
        phase_start = time.time()
        turn_ctx.current_phase = TurnPhase.ANSWER_GENERATION
        turn_ctx.add_trace("Phase: Answer Generation started")

        # 构建活跃推理链（从 ContextManager 或 CognitiveTree）
        active_branch = []
        if self.context_manager:
            try:
                tree = await self.context_manager.get_cognitive_tree(turn_ctx.session_id)
                if tree:
                    active_branch = [n.content for n in tree.find_active_branch()]
            except Exception as exc:
                logger.warning("Failed to get cognitive tree for answer: %s", exc)

        system_confidence = turn_ctx.intent_result.confidence if turn_ctx.intent_result else 0.5
        if turn_ctx.pcr_result:
            system_confidence = (system_confidence + turn_ctx.pcr_result.get("confidence", 0.5)) / 2

        # 如果系统置信度低于阈值，直接生成诚实声明（不走 LLM）
        if system_confidence < self.config.clarification_threshold:
            turn_ctx.answer_text = (
                f"我不太确定你的意思。你的输入是：\"{turn_ctx.user_input}\"。"
                f"系统置信度较低（{system_confidence:.2f}），请提供更多细节。"
            )
            turn_ctx.answer_confidence = system_confidence
            turn_ctx.honesty_declared = True
            turn_ctx.status = "clarifying"
            latency_ms = (time.time() - phase_start) * 1000.0
            turn_ctx.mark_phase(TurnPhase.ANSWER_GENERATION, latency_ms)
            turn_ctx.add_trace("Phase: Answer generated (clarification, low confidence)")
            return

        # 调用 Answer-LLM
        llm_result = await self._run_llm(
            "Answer-LLM",
            turn_ctx.session_id,
            {
                "user_input": turn_ctx.user_input,
                "user_profile": json.dumps(self.profile_updater.get_profile(turn_ctx.session_id), ensure_ascii=False)[:500],
                "algorithm_result": str(turn_ctx.pcr_result)[:200],
                "llm_result": str(turn_ctx.intent_result)[:200],
                "fusion_mode": "hybrid",
                "system_confidence": f"{system_confidence:.2f}",
                "active_cognitive_branch": json.dumps(active_branch, ensure_ascii=False),
                "style": self.config.response_style,
                "max_length": str(self.config.max_response_length),
            },
            timeout_ms=self.config.answer_timeout_ms,
        )

        if llm_result and llm_result.success and llm_result.output:
            turn_ctx.answer_text = llm_result.output.get("response", "")
            turn_ctx.answer_confidence = llm_result.output.get("confidence", 0.5)
            turn_ctx.honesty_declared = llm_result.output.get("honesty_declared", False)
            turn_ctx.cited_nodes = llm_result.output.get("cited_nodes", [])
            if llm_result.node_id:
                turn_ctx.cited_nodes.append(llm_result.node_id)
        else:
            # LLM 失败时的 fallback 回复
            turn_ctx.answer_text = f"已收到你的请求：\"{turn_ctx.user_input}\"。正在处理中..."
            turn_ctx.answer_confidence = 0.5

        latency_ms = (time.time() - phase_start) * 1000.0
        turn_ctx.mark_phase(TurnPhase.ANSWER_GENERATION, latency_ms)
        turn_ctx.add_trace(f"Phase: Answer Generation completed (len={len(turn_ctx.answer_text)})")

    async def _phase_meta_cognitive(self, turn_ctx: TurnContext) -> None:
        """元认知验证阶段——异步后台运行。"""
        try:
            if self._turn_counter % 3 != 0:
                try:
                    if self.compiler:
                        tree = self.compiler._store.get_tree(turn_ctx.session_id)
                        if tree and len(tree.nodes) > 10:
                            turn_ctx.add_trace("Meta-Cognitive skipped (scheduling)")
                            return
                except Exception:
                    pass
            turn_ctx.add_trace("Phase: Meta-Cognitive (background) started")
            # 获取最近节点进行验证
            recent_node = None
            if self.compiler:
                tree = self.compiler._store.get_tree(turn_ctx.session_id)
                if tree and tree.nodes:
                    recent_node = max(tree.nodes.values(), key=lambda n: n.timestamp)

            if recent_node:
                    all_nodes = []
                    if self.compiler:
                        tree = self.compiler._store.get_tree(turn_ctx.session_id)
                        if tree and tree.nodes:
                            all_nodes = list(tree.nodes.values())
                    try:
                        ev_nodes = [n for n in all_nodes if n.node_id in getattr(recent_node, "evidence", [])]
                        hist_nodes = [n for n in all_nodes if n.node_id != recent_node.node_id]
                        rule_result = self.meta_validator.validate(recent_node, hist_nodes, ev_nodes)
                        turn_ctx.meta_cognitive_result = rule_result
                        turn_ctx.add_trace("Meta-Cog rule: " + str(rule_result.get("overall_validation", "unknown")))
                        if rule_result.get("hallucination_risk", 0) > 0.7:
                            if self.compiler:
                                t = self.compiler._store.get_tree(turn_ctx.session_id)
                                if t and recent_node.node_id in t.nodes:
                                    t.nodes[recent_node.node_id].status = CogNodeStatus.INVALIDATED
                                    turn_ctx.add_trace("Rule invalidated node risk=" + str(rule_result["hallucination_risk"]))
                    except Exception as exc:
                        turn_ctx.add_trace("Meta-Cog rule failed: " + str(exc))

            if not recent_node:
                turn_ctx.add_trace("Phase: Meta-Cognitive skipped (no recent node)")
                return

            llm_result = await self._run_llm(
                "Meta-Cognitive-LLM",
                turn_ctx.session_id,
                {
                    "node_content": recent_node.content[:500],
                    "node_type": recent_node.cog_type.value,
                    "source_llm": recent_node.source_llm,
                    "evidence_nodes": json.dumps(recent_node.evidence),
                },
                timeout_ms=self.config.meta_cognitive_timeout_ms,
            )

            if llm_result and llm_result.success:
                turn_ctx.meta_cognitive_result = llm_result.output
                turn_ctx.add_trace("Phase: Meta-Cognitive completed")

                # 如果检测到高风险幻觉，更新节点状态
                if llm_result.output:
                    risk = llm_result.output.get("hallucination_risk", 0.0)
                    if risk > 0.7 and self.compiler:
                        self.compiler._store.update_node(
                            turn_ctx.session_id,
                            recent_node.node_id,
                            {"status": CogNodeStatus.INVALIDATED},
                            requesting_llm="Meta-Cognitive-LLM",
                        )
                        turn_ctx.add_trace(f"Phase: Meta-Cognitive invalidated node {recent_node.node_id} (risk={risk:.2f})")
            else:
                turn_ctx.add_trace("Phase: Meta-Cognitive LLM call failed or skipped")
        except Exception as exc:
            logger.warning("Meta-Cognitive phase failed (background): %s", exc)
            turn_ctx.add_trace(f"Phase: Meta-Cognitive failed: {exc}")

    async def _phase_reflective(self, turn_ctx: TurnContext) -> None:
        """复盘阶段——异步后台运行，跨轮/跨会话。"""
        try:
            turn_ctx.add_trace("Phase: Reflective (background) started")

            # 获取 Cognitive Tree 统计
            tree_stats = {}
            if self.compiler:
                tree = self.compiler._store.get_tree(turn_ctx.session_id)
                if tree:
                    nodes = list(tree.nodes.values())
                    tree_stats = {
                        "total_nodes": len(nodes),
                        "by_type": {t.value: len(tree.find_by_type(t)) for t in set(n.cog_type for n in nodes)},
                        "invalidated": len([n for n in nodes if n.status == CogNodeStatus.INVALIDATED]),
                    }

            # 规则复盘分析引擎（ReflectiveAnalyzer）
            if hasattr(self, "reflective_analyzer"):
                try:
                    all_nodes = list(tree.nodes.values()) if self.compiler and tree else []
                    if all_nodes:
                        ref_result = self.reflective_analyzer.analyze(all_nodes)
                        turn_ctx.reflective_result = ref_result
                        turn_ctx.add_trace("Reflective rule: biases=" + str(len(ref_result.get("bias_analysis", {}).get("detected_biases", []))))
                except Exception as exc:
                    turn_ctx.add_trace("Reflective rule failed: " + str(exc))

            llm_result = await self._run_llm(
                "Reflective-LLM",
                turn_ctx.session_id,
                {
                    "session_range": f"{turn_ctx.session_id} (turn {turn_ctx.turn_id})",
                    "tree_stats": json.dumps(tree_stats, ensure_ascii=False),
                    "biases": "[]",
                },
                timeout_ms=self.config.reflective_timeout_ms,
            )

            if llm_result and llm_result.success:
                turn_ctx.reflective_result = llm_result.output
                turn_ctx.add_trace("Phase: Reflective completed")
            else:
                turn_ctx.add_trace("Phase: Reflective LLM call failed or skipped")
        except Exception as exc:
            logger.warning("Reflective phase failed (background): %s", exc)
            turn_ctx.add_trace(f"Phase: Reflective failed: {exc}")

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    async def _run_algorithm_pcr(self, user_input: str) -> Dict[str, Any]:
        """运行算法 PCR 引擎。"""
        await asyncio.sleep(0)  # 让出事件循环
        if hasattr(self, "algorithm_engine"):
            return self.algorithm_engine.analyze_pcr(user_input)
        return {"confidence": 0.0}

    async def _run_algorithm_intent(self, user_input: str) -> Dict[str, Any]:
        """运行算法 Intent 引擎。"""
        await asyncio.sleep(0)
        if hasattr(self, "algorithm_engine"):
            return self.algorithm_engine.parse_intent(user_input)
        return {"confidence": 0.0}

    async def _run_llm(
        self,
        llm_name: str,
        session_id: str,
        context_data: Dict[str, Any],
        parent_node_id: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> Optional[LLMInstanceResult]:
        """运行指定 LLM 实例。"""
        engine = self._llm_engines.get(llm_name)
        if engine:
            result = await engine.process(context_data, timeout_ms)
            if result:
                instance_result = LLMInstanceResult(llm_name=llm_name, success=result.success, output=result.output, confidence=result.confidence, latency_ms=result.latency_ms, error=result.error)
                return instance_result
        instance = self._llm_instances.get(llm_name)
        if not instance:
            logger.debug("LLM instance %s not found or disabled", llm_name)
            return None
        return await instance.process(session_id, context_data, parent_node_id, timeout_ms)

    def _build_result(self, turn_ctx: TurnContext, start_time: float) -> OrchestratorResult:
        """从 TurnContext 构建 OrchestratorResult。"""
        total_latency = (time.time() - start_time) * 1000.0

        status = "ok"
        if turn_ctx.errors:
            status = "error" if turn_ctx.current_phase == TurnPhase.FAILED else "fallback"
        elif not turn_ctx.answer_text:
            status = "clarifying"

        fallback_reason = None
        if status == "fallback":
            fallback_reason = "; ".join(turn_ctx.errors) if turn_ctx.errors else "unknown"

        # 构建澄清建议
        suggestions = []
        if status == "clarifying" or turn_ctx.intent_result and turn_ctx.intent_result.is_ambiguous():
            suggestions = [f"请 clarify: {a.description}" for a in (turn_ctx.intent_result.ambiguities if turn_ctx.intent_result else [])]

        return OrchestratorResult(
            turn_id=turn_ctx.turn_id,
            session_id=turn_ctx.session_id,
            success=status in ("ok", "fallback"),
            status=status,
            answer=turn_ctx.answer_text,
            answer_confidence=turn_ctx.answer_confidence,
            honesty_declared=turn_ctx.honesty_declared,
            intent=turn_ctx.intent_result,
            task_graph=turn_ctx.task_graph,
            suggestions=suggestions,
            cited_cognitive_nodes=turn_ctx.cited_nodes,
            total_latency_ms=total_latency,
            phase_latencies_ms=turn_ctx.phase_latencies_ms,
            trace_log=turn_ctx.trace_log,
            errors=turn_ctx.errors,
            fallback_reason=fallback_reason,
        )

    # ── 生命周期 ────────────────────────────────────────────────────────────

    def _init_llm_engines(self) -> None:
        provider = self.provider
        engine_map = {
            "PCR-LLM": PCRLLM(provider),
            "Intent-LLM": IntentLLM(provider),
            "Planning-LLM": PlanningLLM(provider),
            "Meta-Cognitive-LLM": MetaCognitiveLLM(provider),
            "Reflective-LLM": ReflectiveLLM(provider),
            "Answer-LLM": AnswerLLM(provider),
        }
        self._llm_engines = engine_map
        for name, engine in engine_map.items():
            attr = "enable_" + name.lower().replace("-", "_")
            toggle = getattr(self.config, attr, True)
            if not toggle:
                self._llm_instances.pop(name, None)

    async def health_check(self) -> Dict[str, Any]:
        """编排器健康检查。"""
        try:
            await asyncio.sleep(0)
            checks = {
                "orchestrator_status": "closed" if self._closed else "running",
                "llm_instances": len(self._llm_instances),
                "turn_counter": self._turn_counter,
                "provider_available": self.provider is not None,
                "compiler_available": self.compiler is not None,
                "planning_skill_available": self.planning_skill is not None,
                "tool_registry_available": self.tool_registry is not None,
            }
            healthy = not self._closed and self.provider is not None
            return {"healthy": healthy, "checks": checks}
        except Exception as exc:
            logger.error("Orchestrator health check failed: %s", exc)
            return {"healthy": False, "error": str(exc)}

    async def close(self) -> None:
        """关闭编排器，释放资源。"""
        try:
            self._closed = True
            if self.event_bus:
                self.event_bus.stop()
            logger.info("Orchestrator closed")
        except Exception as exc:
            logger.error("Orchestrator close failed: %s", exc)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取编排器统计。"""
        return {
            "turn_counter": self._turn_counter,
            "llm_instances": len(self._llm_instances),
            "closed": self._closed,
        }
