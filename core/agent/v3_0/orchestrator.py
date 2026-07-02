# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator.py
────────────────────────────────
DialogMesh v3.0 Orchestrator — 6 LLM 实例整合编排器。

用途：
- 协调 6 个专用 LLM 实例（PCR / Intent / Planning / Meta-Cognitive / Answer / Reflective）
  完成用户请求的完整处理生命周期。
- 提供 ``process_request()`` 作为上层 Service Layer 的统一入口。
- 通过 CognitiveCompiler 将各 LLM 的推理结果写入共享的 Cognitive Tree。
- 支持异步并发：PCR 与 Intent 并行执行；Answer 与 Reflective 并行执行。

处理流程（5 阶段）：
  1. 输入分发：PCR-LLM + Intent-LLM 并行执行
  2. 认知编译：CognitiveCompiler 将感知与意图结果编译为 CT 节点
  3. 规划执行：PlanningSkill 将意图转化为 TaskGraph
  4. 验证监督：Meta-Cognitive-LLM 跨轮验证结果一致性
  5. 输出生成：Answer-LLM 生成回复 + Reflective-LLM 异步复盘

对应工程文档：
- ENGINEERING_MULTILAYER_LLM.md §5
- ENGINEERING_INTEGRATION.md §6.1

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    CognitiveProfile_v3,
    EventType,
    IntentContext_v3,
    Intent_v3,
    ParseResult_v3,
    TaskGraph_v3,
    UserMessage_v3,
    WebSocketEvent,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OrchestratorResult:
    """Orchestrator 处理结果 — 包含回复、任务图、认知树更新与遥测数据。"""

    session_id: str
    turn_index: int
    answer: str = ""
    task_graph: Optional[TaskGraph_v3] = None
    cognitive_profile: Optional[CognitiveProfile_v3] = None
    trace_log: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    used_fallback: bool = False
    events: List[WebSocketEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMInstanceConfig:
    """单个 LLM 实例配置。"""

    cognitive_mode: str = "fast"
    provider: str = "openai"
    model: str = "gpt-3.5-turbo"


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class Orchestrator:
    """
    DialogMesh v3.0 核心编排器。

    整合 6 个 LLM 实例的异步处理流水线：
      - PCR-LLM：实时感知（fast）
      - Intent-LLM：意图理解（fast）
      - Planning-LLM：任务规划（deep）
      - Meta-Cognitive-LLM：验证监督（deep）
      - Reflective-LLM：长期复盘（reflective）
      - Answer-LLM：回复生成（deep）

    Args:
        pcr_engine: PCR 引擎实例（如 RuleBasedPCR）。
        intent_parser: 意图解析器实例。
        planning_skill: PlanningSkill 实例。
        cognitive_compiler: CognitiveCompiler 实例。
        context_manager: ContextManager 实例。
        topic_tree: CognitiveTree 实例。
        observability: Telemetry 实例。
        llm_providers: ProviderManager 实例。
        config: LLM 实例配置字典（来自 agent_config.yaml 的 llm_instances 段）。
    """

    def __init__(
        self,
        pcr_engine: Any,
        intent_parser: Any,
        planning_skill: Any,
        cognitive_compiler: Any,
        context_manager: Any,
        topic_tree: Any,
        observability: Any,
        llm_providers: Any,
        config: Dict[str, Any],
    ) -> None:
        self._pcr = pcr_engine
        self._intent_parser = intent_parser
        self._planning = planning_skill
        self._compiler = cognitive_compiler
        self._ctx_mgr = context_manager
        self._topic_tree = topic_tree
        self._obs = observability
        self._llm_providers = llm_providers
        self._config = config

        # 会话状态追踪
        self._session_turns: Dict[str, int] = {}
        self._lock = asyncio.Lock()

        # 从 config 解析 6 个 LLM 实例的专用配置
        self._llm_cfgs: Dict[str, LLMInstanceConfig] = {}
        for key, val in config.items():
            if isinstance(val, dict):
                self._llm_cfgs[key] = LLMInstanceConfig(
                    cognitive_mode=val.get("cognitive_mode", "fast"),
                    provider=val.get("provider", "openai"),
                    model=val.get("model", "gpt-3.5-turbo"),
                )

        logger.info(
            f"[Orchestrator] Initialized with {len(self._llm_cfgs)} LLM instances"
        )

    # ── 公共 API ────────────────────────────────────────────────────────────

    async def process_request(
        self,
        user_message: UserMessage_v3,
        session_id: Optional[str] = None,
    ) -> OrchestratorResult:
        """
        处理用户请求的主入口。

        执行完整的 5 阶段异步流水线，并返回包含回答、任务图与遥测的结果。
        """
        start_time = time.time()
        sid = session_id or user_message.session_id
        result = OrchestratorResult(session_id=sid, turn_index=await self._next_turn_index(sid))
        trace_log: List[str] = []

        try:
            await asyncio.sleep(0)  # 让出事件循环

            # ── Stage 1: 输入分发（PCR + Intent 并行）─────────────────────
            trace_log.append(f"[Stage 1] PCR + Intent parallel (turn={result.turn_index})")
            pcr_output, intent_v3 = await self._stage_1_perception_and_intent(
                user_message, sid, trace_log
            )

            # ── Stage 2: 认知编译 ──────────────────────────────────────────
            trace_log.append("[Stage 2] Cognitive compilation")
            await self._stage_2_compile(sid, pcr_output, intent_v3, trace_log)

            # ── Stage 3: 规划执行 ──────────────────────────────────────────
            trace_log.append("[Stage 3] Planning & execution")
            task_graph = await self._stage_3_planning(sid, intent_v3, pcr_output, trace_log)
            result.task_graph = task_graph

            # ── Stage 4: 验证监督（Meta-Cognitive）───────────────────────────
            trace_log.append("[Stage 4] Meta-cognitive validation")
            validation_passed = await self._stage_4_validate(sid, intent_v3, task_graph, trace_log)

            # ── Stage 5: 输出生成（Answer + Reflective 并行）──────────────────
            trace_log.append("[Stage 5] Answer generation + Reflective")
            answer, reflection = await self._stage_5_generate(
                sid, user_message, intent_v3, task_graph, validation_passed, trace_log
            )
            result.answer = answer

            # 构建 WebSocket 事件
            result.events = self._build_events(sid, result.turn_index, answer, task_graph)
            trace_log.append("[Stage 5] Events built")

            # 记录遥测
            if self._obs and hasattr(self._obs, "record_turn"):
                try:
                    await self._obs.record_turn(
                        session_id=sid,
                        turn_index=result.turn_index,
                        query=user_message.content,
                        latency_ms=(time.time() - start_time) * 1000.0,
                        intent=intent_v3.category.value if intent_v3 else "unknown",
                        confidence=getattr(intent_v3, "confidence", 0.0),
                        execution_status="success" if validation_passed else "degraded",
                        trace_steps=trace_log,
                    )
                except Exception as exc:
                    logger.warning(f"[Orchestrator] Telemetry record_turn failed: {exc}")

        except Exception as exc:
            logger.error(f"[Orchestrator] process_request failed: {exc}", exc_info=True)
            result.answer = f"[系统错误] 请求处理失败: {exc}"
            result.used_fallback = True
            trace_log.append(f"[ERROR] {exc}")

        result.latency_ms = (time.time() - start_time) * 1000.0
        result.trace_log = trace_log
        return result

    async def process_request_stream(
        self,
        user_message: UserMessage_v3,
        session_id: Optional[str] = None,
    ):
        """
        流式处理用户请求。

        每完成一个阶段即 yield 一个 WebSocketEvent，供前端实时渲染。
        """
        sid = session_id or user_message.session_id
        turn_index = await self._next_turn_index(sid)
        trace_log: List[str] = []

        try:
            # Stage 1
            yield WebSocketEvent.builder(EventType.SYSTEM_STATUS, sid).with_payload(
                "stage", "perception"
            ).with_payload("turn_index", turn_index).build()
            pcr_output, intent_v3 = await self._stage_1_perception_and_intent(
                user_message, sid, trace_log
            )

            # Stage 2
            yield WebSocketEvent.builder(EventType.SYSTEM_STATUS, sid).with_payload(
                "stage", "compilation"
            ).build()
            await self._stage_2_compile(sid, pcr_output, intent_v3, trace_log)

            # Stage 3
            yield WebSocketEvent.builder(EventType.SYSTEM_STATUS, sid).with_payload(
                "stage", "planning"
            ).build()
            task_graph = await self._stage_3_planning(sid, intent_v3, pcr_output, trace_log)
            if task_graph:
                yield WebSocketEvent.builder(EventType.TASK_GRAPH, sid).with_payload(
                    "task_graph", task_graph.to_summary() if hasattr(task_graph, "to_summary") else {}
                ).build()

            # Stage 4
            yield WebSocketEvent.builder(EventType.SYSTEM_STATUS, sid).with_payload(
                "stage", "validation"
            ).build()
            validation_passed = await self._stage_4_validate(sid, intent_v3, task_graph, trace_log)

            # Stage 5
            yield WebSocketEvent.builder(EventType.SYSTEM_STATUS, sid).with_payload(
                "stage", "generation"
            ).build()
            answer, _ = await self._stage_5_generate(
                sid, user_message, intent_v3, task_graph, validation_passed, trace_log
            )

            yield WebSocketEvent.builder(EventType.MESSAGE, sid).with_payload(
                "content", answer
            ).with_payload("turn_index", turn_index).build()

        except Exception as exc:
            logger.error(f"[Orchestrator] stream failed: {exc}")
            yield WebSocketEvent.builder(EventType.ERROR, sid).with_payload(
                "message", str(exc)
            ).with_payload("turn_index", turn_index).build()

    async def shutdown(self) -> None:
        """优雅关闭 Orchestrator，释放会话状态。"""
        async with self._lock:
            self._session_turns.clear()
        logger.info("[Orchestrator] Shutdown complete")

    # ── 内部阶段实现 ────────────────────────────────────────────────────────

    async def _stage_1_perception_and_intent(
        self,
        user_message: UserMessage_v3,
        session_id: str,
        trace_log: List[str],
    ) -> Tuple[Any, Optional[Intent_v3]]:
        """
        Stage 1: PCR-LLM 感知 + Intent-LLM 意图理解（并行执行）。

        Returns:
            (pcr_output, intent_v3)
        """
        pcr_task = asyncio.create_task(self._run_pcr(user_message, session_id))
        intent_task = asyncio.create_task(self._run_intent(user_message, session_id))

        pcr_output, intent_v3 = await asyncio.gather(pcr_task, intent_task)

        trace_log.append(f"  PCR: {getattr(pcr_output, 'expectation', 'unknown')}")
        trace_log.append(f"  Intent: {intent_v3.category.value if intent_v3 else 'none'}")
        return pcr_output, intent_v3

    async def _run_pcr(self, user_message: UserMessage_v3, session_id: str) -> Any:
        """执行 PCR 感知。"""
        try:
            from core.agent.pcr.datacontract import PCRInput_v1

            pcr_input = PCRInput_v1(query=user_message.content)
            pcr_output = self._pcr.evaluate(pcr_input)
            return pcr_output
        except Exception as exc:
            logger.warning(f"[PCR] Run failed: {exc}")
            return None

    async def _run_intent(self, user_message: UserMessage_v3, session_id: str) -> Optional[Intent_v3]:
        """执行意图解析。"""
        try:
            # 使用 v2.x IntentParser 接口，然后将结果转换为 v3 Intent_v3
            raw_result = self._intent_parser.parse(
                user_input=user_message.content,
                intent_context=None,
                parse_context=None,
            )

            # 转换为 v3 模型
            if hasattr(raw_result, "intent"):
                intent = self._convert_to_intent_v3(raw_result.intent)
                return intent
            return None
        except Exception as exc:
            logger.warning(f"[Intent] Run failed: {exc}")
            return None

    async def _stage_2_compile(
        self,
        session_id: str,
        pcr_output: Any,
        intent_v3: Optional[Intent_v3],
        trace_log: List[str],
    ) -> None:
        """
        Stage 2: 认知编译 — 将 PCR 与 Intent 结果写入 Cognitive Tree。
        """
        if not self._compiler:
            trace_log.append("  Compiler skipped (not available)")
            return

        try:
            # 编译 PCR 感知节点
            if pcr_output:
                from core.agent.v3_0.cognitive_tree.models import CogType

                self._compiler.compile(
                    session_id=session_id,
                    llm_name="PCR-LLM",
                    cog_type=CogType.PERCEPTION,
                    content=str(getattr(pcr_output, "expectation", "unknown")),
                    confidence=getattr(pcr_output, "confidence", 0.5),
                )
                trace_log.append("  Compiled PCR node")

            # 编译意图节点
            if intent_v3:
                from core.agent.v3_0.cognitive_tree.models import CogType

                self._compiler.compile(
                    session_id=session_id,
                    llm_name="Intent-LLM",
                    cog_type=CogType.HYPOTHESIS,
                    content=f"{intent_v3.category.value}: {intent_v3.raw_input}",
                    confidence=intent_v3.confidence,
                )
                trace_log.append("  Compiled Intent node")
        except Exception as exc:
            logger.warning(f"[Compiler] Stage 2 failed: {exc}")
            trace_log.append(f"  Compiler error: {exc}")

    async def _stage_3_planning(
        self,
        session_id: str,
        intent_v3: Optional[Intent_v3],
        pcr_output: Any,
        trace_log: List[str],
    ) -> Optional[TaskGraph_v3]:
        """
        Stage 3: 规划执行 — 将意图转化为 TaskGraph。
        """
        if not intent_v3 or not self._planning:
            trace_log.append("  Planning skipped (no intent or planner)")
            return None

        try:
            # 构建 IntentContext
            intent_ctx = IntentContext_v3()
            if pcr_output:
                intent_ctx.noise_level = getattr(pcr_output, "noise_level", 0.0)
                intent_ctx.complexity_level = getattr(pcr_output, "complexity_level", 0.0)
                intent_ctx.expectation = getattr(pcr_output, "expectation", intent_ctx.expectation)

            # 调用 PlanningSkill
            plan_result = await self._planning.plan(intent=intent_v3, intent_context=intent_ctx)

            if plan_result and getattr(plan_result, "success", False):
                task_graph = getattr(plan_result, "task_graph", None)
                if task_graph:
                    trace_log.append(f"  Planning success: {len(task_graph.nodes)} nodes")
                    return task_graph

            trace_log.append("  Planning returned empty task graph")
            return None
        except Exception as exc:
            logger.warning(f"[Planning] Stage 3 failed: {exc}")
            trace_log.append(f"  Planning error: {exc}")
            return None

    async def _stage_4_validate(
        self,
        session_id: str,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
        trace_log: List[str],
    ) -> bool:
        """
        Stage 4: 验证监督 — Meta-Cognitive-LLM 跨轮验证。

        目前使用规则验证作为轻量级实现，未来可接入 LLM 进行深度验证。
        """
        try:
            validations: List[bool] = []

            # V1: 意图置信度校验
            if intent_v3:
                validations.append(intent_v3.confidence >= 0.3)

            # V2: 任务图无环校验
            if task_graph and hasattr(task_graph, "topological_order"):
                try:
                    order = task_graph.topological_order()
                    validations.append(len(order) > 0 or len(task_graph.nodes) == 0)
                except Exception:
                    validations.append(False)

            # V3: 上下文一致性（检查是否存在明显矛盾）
            if self._ctx_mgr and session_id:
                try:
                    session = self._ctx_mgr.get_session(session_id)
                    validations.append(session is not None)
                except Exception:
                    validations.append(True)  # 无会话时不阻塞

            passed = all(validations) if validations else True
            trace_log.append(f"  Validation: {'passed' if passed else 'failed'} ({len(validations)} checks)")
            return passed
        except Exception as exc:
            logger.warning(f"[Validation] Stage 4 failed: {exc}")
            trace_log.append(f"  Validation error: {exc}")
            return False

    async def _stage_5_generate(
        self,
        session_id: str,
        user_message: UserMessage_v3,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
        validation_passed: bool,
        trace_log: List[str],
    ) -> Tuple[str, str]:
        """
        Stage 5: 输出生成 — Answer-LLM + Reflective-LLM 并行执行。

        Returns:
            (answer, reflection)
        """
        answer_task = asyncio.create_task(
            self._generate_answer(session_id, user_message, intent_v3, task_graph, validation_passed)
        )
        reflective_task = asyncio.create_task(
            self._run_reflective(session_id, user_message, intent_v3, task_graph)
        )

        answer, reflection = await asyncio.gather(answer_task, reflective_task)
        trace_log.append(f"  Answer generated ({len(answer)} chars)")
        trace_log.append(f"  Reflective: {reflection}")
        return answer, reflection

    async def _generate_answer(
        self,
        session_id: str,
        user_message: UserMessage_v3,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
        validation_passed: bool,
    ) -> str:
        """生成最终回复。"""
        try:
            # 优先使用 Answer-LLM 配置
            answer_cfg = self._llm_cfgs.get("answer_llm")
            provider_name = answer_cfg.provider if answer_cfg else "openai"

            # 构造 prompt
            prompt = self._build_answer_prompt(user_message, intent_v3, task_graph, validation_passed)

            # 调用 LLM
            if self._llm_providers and hasattr(self._llm_providers, "generate"):
                from core.agent.v3_0.llm_providers.base import GenerateRequest_v3

                request = GenerateRequest_v3(prompt=prompt, max_tokens=1024, temperature=0.5)
                result = await self._llm_providers.generate(request, provider_name=provider_name)
                if result and getattr(result, "success", False):
                    return getattr(result, "text", "")

            # 回退：基于规则生成简单回复
            return self._fallback_answer(user_message, intent_v3, task_graph)
        except Exception as exc:
            logger.warning(f"[Answer] Generation failed: {exc}")
            return self._fallback_answer(user_message, intent_v3, task_graph)

    async def _run_reflective(
        self,
        session_id: str,
        user_message: UserMessage_v3,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
    ) -> str:
        """
        Reflective-LLM 长期复盘 — 异步执行，不阻塞 Answer 返回。
        目前为轻量级实现，记录本轮关键信息到 Cognitive Tree。
        """
        try:
            if self._compiler and intent_v3:
                from core.agent.v3_0.cognitive_tree.models import CogType

                self._compiler.compile(
                    session_id=session_id,
                    llm_name="Reflective-LLM",
                    cog_type=CogType.REFLECTION,
                    content=f"Turn reflection: intent={intent_v3.category.value}, "
                    f"confidence={intent_v3.confidence}, "
                    f"nodes={len(task_graph.nodes) if task_graph else 0}",
                    confidence=0.7,
                )
            return "reflection_logged"
        except Exception as exc:
            logger.warning(f"[Reflective] Run failed: {exc}")
            return f"reflection_error: {exc}"

    # ── 辅助方法 ────────────────────────────────────────────────────────────

    async def _next_turn_index(self, session_id: str) -> int:
        """获取并递增会话的轮次索引。"""
        async with self._lock:
            idx = self._session_turns.get(session_id, 0)
            self._session_turns[session_id] = idx + 1
            return idx

    def _convert_to_intent_v3(self, raw_intent: Any) -> Optional[Intent_v3]:
        """将 v2.x Intent 转换为 v3 Intent_v3。"""
        try:
            from core.agent.models import IntentCategory

            intent = Intent_v3(
                category=getattr(raw_intent, "category", IntentCategory.UNKNOWN),
                raw_input=getattr(raw_intent, "raw_input", ""),
                normalized_input=getattr(raw_intent, "normalized_input", ""),
                confidence=getattr(raw_intent, "confidence", 0.0),
                requires_process=getattr(raw_intent, "requires_process", True),
                is_destructive=getattr(raw_intent, "is_destructive", False),
                is_reversible=getattr(raw_intent, "is_reversible", False),
                session_id=getattr(raw_intent, "session_id", None),
            )
            # 转换实体
            raw_entities = getattr(raw_intent, "entities", [])
            if raw_entities:
                from core.agent.v3_0.data_models import Entity_v3

                intent.entities = [
                    Entity_v3(
                        type=getattr(e, "type", None),
                        value=getattr(e, "value", None),
                        raw_text=getattr(e, "raw_text", ""),
                        confidence=getattr(e, "confidence", 1.0),
                    )
                    for e in raw_entities
                ]
            return intent
        except Exception as exc:
            logger.warning(f"Intent conversion failed: {exc}")
            return None

    def _build_answer_prompt(
        self,
        user_message: UserMessage_v3,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
        validation_passed: bool,
    ) -> str:
        """构造 Answer-LLM 的 prompt。"""
        lines: List[str] = []
        lines.append("You are DialogMesh, a helpful assistant.")
        lines.append("")
        lines.append(f"User: {user_message.content}")
        if intent_v3:
            lines.append(f"Intent: {intent_v3.category.value}")
            lines.append(f"Confidence: {intent_v3.confidence:.2f}")
        if task_graph and hasattr(task_graph, "nodes"):
            lines.append(f"Task count: {len(task_graph.nodes)}")
        if not validation_passed:
            lines.append("Warning: validation issues detected, be cautious.")
        lines.append("")
        lines.append("Please provide a helpful, concise response.")
        return "\n".join(lines)

    def _fallback_answer(
        self,
        user_message: UserMessage_v3,
        intent_v3: Optional[Intent_v3],
        task_graph: Optional[TaskGraph_v3],
    ) -> str:
        """当 LLM 不可用时回退到规则生成的简单回复。"""
        category = intent_v3.category.value if intent_v3 else "unknown"
        if category == "scan_memory":
            return "收到扫描请求。请确认目标地址范围，我将为您执行内存扫描。"
        if category == "analyze":
            return "收到分析请求。正在准备分析环境..."
        if category == "tutorial":
            return "好的，我可以为您提供相关教程。请告诉我具体想了解哪方面内容？"
        return f"收到您的消息：{user_message.content[:50]}... 我已记录，正在处理中。"

    def _build_events(
        self,
        session_id: str,
        turn_index: int,
        answer: str,
        task_graph: Optional[TaskGraph_v3],
    ) -> List[WebSocketEvent]:
        """构造需要推送给前端的 WebSocketEvent 列表。"""
        events: List[WebSocketEvent] = []

        # 主消息事件
        events.append(
            WebSocketEvent.builder(EventType.MESSAGE, session_id)
            .with_payload("content", answer)
            .with_payload("turn_index", turn_index)
            .build()
        )

        # 任务图事件（如果有）
        if task_graph:
            events.append(
                WebSocketEvent.builder(EventType.TASK_GRAPH, session_id)
                .with_payload("task_graph", task_graph.to_summary() if hasattr(task_graph, "to_summary") else {})
                .build()
            )

        return events
