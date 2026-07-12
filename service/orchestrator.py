# -*- coding: utf-8 -*-
"""
service/orchestrator.py
───────────────────────
DialogMesh 请求编排器。

将用户请求通过 PCR → Intent Parser → [编译器] → 响应构建的完整流程编排起来。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.pcr.datacontract import PCRInput_v1, HistoryEntry, Modality
from core.agent.v3_common.models import (
    IntentContext, ParseContext, ParseResult,
    Intent, IntentCategory, TaskGraph,
)
from core.agent.pcr.interface import IPCRRouter

from service.models import Session, CognitiveProfile
from service.protocol.schemas import SendMessageRequest

logger = logging.getLogger(__name__)


class DialogMeshOrchestrator:
    """
    DialogMesh 请求编排器。

    流程：
        1. 构建 PCRInput_v1
        2. 调用 PCR.evaluate()
        3. 转换为 IntentContext
        4. 调用 IntentParser.parse()
        5. 如有编译器，调用编译器
        6. 更新 Session 的 cognitive_profile
        7. 构建响应字典
    """

    def __init__(
        self,
        pcr: IPCRRouter,
        intent_parser,
        compiler=None,
    ):
        self._pcr = pcr
        self._intent_parser = intent_parser
        self._compiler = compiler
        self._logger = logging.getLogger(self.__class__.__name__)

    # ── 核心流程 ───────────────────────────────────────────────────────

    async def process(
        self,
        request: SendMessageRequest,
        session: Session,
    ) -> Dict[str, Any]:
        """
        处理用户请求，执行完整编排流程。

        Returns:
            字典，包含 parse_result（原始对象）、前端响应字段、trace_log、latency
        """
        trace_log: List[str] = []
        start_time = time.time()

        try:
            # 1. 构建 PCRInput
            self._logger.info("Building PCRInput for session=%s", session.session_id)
            trace_log.append(f"[Orchestrator] Building PCRInput session={session.session_id}")
            pcr_input = self.build_pcr_input(session, request)

            # 2. 调用 PCR.evaluate（同步阻塞调用用 run_in_executor 包裹）
            self._logger.info("Calling PCR.evaluate")
            trace_log.append("[Orchestrator] Calling PCR.evaluate")
            pcr_start = time.time()
            try:
                pcr_output = await self._run_in_executor(self._pcr.evaluate, pcr_input)
            except Exception as exc:
                self._logger.error("PCR evaluation failed: %s", exc)
                trace_log.append(f"[Orchestrator] PCR evaluation failed: {exc}")
                from core.agent.pcr.datacontract import PCROutput_v1
                pcr_output = PCROutput_v1.default_fallback(str(exc))
            pcr_latency = (time.time() - pcr_start) * 1000
            trace_log.append(f"[Orchestrator] PCR latency={pcr_latency:.1f}ms")

            # 3. 转换为 IntentContext
            self._logger.info("Converting PCROutput to IntentContext")
            intent_context = IntentContext.from_pcr_output(pcr_output)
            trace_log.append(
                f"[Orchestrator] IntentContext: expectation={intent_context.expectation.value} "
                f"noise={intent_context.noise_level:.2f} complexity={intent_context.complexity_level:.2f}"
            )

            # 4. 构建 ParseContext
            parse_context = self._build_parse_context(session)

            # 5. 调用 IntentParser.parse（同步阻塞调用用 run_in_executor 包裹）
            self._logger.info("Calling IntentParser.parse")
            trace_log.append("[Orchestrator] Calling IntentParser.parse")
            parser_start = time.time()
            query = request.content or ""
            try:
                parse_result = await self._run_in_executor(
                    self._intent_parser.parse,
                    query,
                    intent_context,
                    parse_context,
                )
            except Exception as exc:
                self._logger.error("IntentParser.parse failed: %s", exc)
                trace_log.append(f"[Orchestrator] IntentParser failed: {exc}")
                fallback_intent = Intent(
                    category=IntentCategory.UNKNOWN,
                    raw_input=query,
                    confidence=0.0,
                )
                parse_result = ParseResult(
                    intent=fallback_intent,
                    task_graph=None,
                    is_actionable=False,
                    clarification_message="解析引擎暂时不可用，请稍后重试",
                    suggestions=["重试"],
                    trace_log=[f"Error: {exc}"],
                )
            parser_latency = (time.time() - parser_start) * 1000
            trace_log.append(f"[Orchestrator] Parser latency={parser_latency:.1f}ms")

            # 6. 如有编译器，调用编译器
            if self._compiler is not None:
                self._logger.info("Calling compiler")
                trace_log.append("[Orchestrator] Calling compiler")
                try:
                    compiler_result = self._call_compiler(query, session, parse_result)
                    if compiler_result:
                        trace_log.append(f"[Orchestrator] Compiler result: {compiler_result}")
                except Exception as exc:
                    self._logger.warning("Compiler failed (skipped): %s", exc)
                    trace_log.append(f"[Orchestrator] Compiler skipped: {exc}")

            # 7. 更新 Session 的 cognitive_profile
            self._logger.info("Updating cognitive profile")
            self.update_cognitive_profile(session, parse_result)

            # 8. 合并 trace_log
            parse_result.trace_log.extend(trace_log)
            total_latency = (time.time() - start_time) * 1000
            parse_result.trace_log.append(f"[Orchestrator] Total latency={total_latency:.1f}ms")

            # 构建响应
            response = self.build_response(parse_result, session)
            response["parse_result"] = parse_result
            response["pcr_output"] = pcr_output
            response["pcr_latency_ms"] = pcr_latency
            response["parser_latency_ms"] = parser_latency
            return response

        except Exception as exc:
            self._logger.exception("Unhandled error in orchestrator.process")
            fallback_intent = Intent(
                category=IntentCategory.UNKNOWN,
                raw_input=request.content or "",
                confidence=0.0,
            )
            fallback_result = ParseResult(
                intent=fallback_intent,
                task_graph=None,
                is_actionable=False,
                clarification_message="服务暂时不可用，请稍后重试",
                suggestions=["重试"],
                trace_log=[f"[Orchestrator] Unhandled error: {exc}"],
            )
            return {
                "parse_result": fallback_result,
                "intent_result": fallback_intent.to_dict(),
                "task_graph": None,
                "ambiguities": [],
                "suggestions": ["重试"],
                "cognitive_profile": None,
                "trace_log": fallback_result.trace_log,
                "is_actionable": False,
                "clarification_message": fallback_result.clarification_message,
                "pcr_output": None,
                "pcr_latency_ms": 0.0,
                "parser_latency_ms": 0.0,
            }

    # ── 辅助方法 ───────────────────────────────────────────────────────

    def build_pcr_input(
        self,
        session: Session,
        request: SendMessageRequest,
    ) -> PCRInput_v1:
        """
        从 Session 和 Request 构建 PCRInput_v1。
        包含最近 10 轮的 session_history 和认知画像。
        """
        history_entries: List[HistoryEntry] = []
        for turn in session.history[-10:]:
            entry = HistoryEntry(
                role=turn.role,
                content=turn.content,
                expectation="",
                timestamp=turn.timestamp,
                metadata=turn.intent_result or {},
            )
            history_entries.append(entry)

        user_preferences: Dict[str, Any] = {}
        if session.adaptive_thresholds:
            user_preferences["adaptive_thresholds"] = session.adaptive_thresholds.to_dict()

        if session.cognitive_profile:
            from core.agent.pcr.datacontract import CognitiveProfile_v1
            pcr_cog = CognitiveProfile_v1(
                metacognition=session.cognitive_profile.metacognition,
                divergence=session.cognitive_profile.divergence,
                tracking_depth=session.cognitive_profile.tracking_depth,
                stability=session.cognitive_profile.stability,
                confidence=session.cognitive_profile.confidence,
            )
            user_preferences["cognitive_profile"] = pcr_cog.to_dict()

        modality_map = {
            "text": Modality.TEXT,
            "structured": Modality.STRUCTURED,
            "image": Modality.IMAGE,
            "audio": Modality.AUDIO,
            "multimodal": Modality.MULTIMODAL,
        }
        modality = modality_map.get(request.modality, Modality.TEXT)

        return PCRInput_v1(
            query=request.content or "",
            modality=modality,
            session_id=session.session_id,
            turn_index=session.turn_count,
            session_history=history_entries,
            user_preferences=user_preferences,
            timestamp=request.timestamp or time.time(),
            metadata={
                "message_id": request.message_id,
                "client_sequence": request.client_sequence,
            },
        )

    def build_response(
        self,
        parse_result: ParseResult,
        session: Session,
    ) -> Dict[str, Any]:
        """
        构建前端响应字典。

        包含：intent_result, task_graph, ambiguities, suggestions,
              cognitive_profile, trace_log, is_actionable, clarification_message
        """
        cog_dict = None
        if session.cognitive_profile:
            cog_dict = session.cognitive_profile.to_dict()

        return {
            "intent_result": parse_result.intent.to_dict(),
            "task_graph": parse_result.task_graph.to_dict() if parse_result.task_graph else None,
            "ambiguities": [a.to_dict() for a in parse_result.intent.ambiguities],
            "suggestions": parse_result.suggestions,
            "cognitive_profile": cog_dict,
            "trace_log": parse_result.trace_log,
            "is_actionable": parse_result.is_actionable,
            "clarification_message": parse_result.clarification_message,
        }

    def update_cognitive_profile(
        self,
        session: Session,
        parse_result: ParseResult,
    ) -> None:
        """
        基于 ParseResult 更新 Session 的 cognitive_profile。
        """
        if session.cognitive_profile is None:
            session.cognitive_profile = CognitiveProfile()

        cog = session.cognitive_profile
        intent = parse_result.intent

        # confidence：取最高值
        cog.confidence = max(cog.confidence, intent.confidence)

        # divergence：有歧义则上升，无歧义则下降
        if intent.ambiguities:
            cog.divergence = min(1.0, cog.divergence + 0.1)
        else:
            cog.divergence = max(0.0, cog.divergence - 0.05)

        # tracking_depth：基于子意图数量
        sub_count = len(intent.sub_intents)
        if sub_count > 1:
            cog.tracking_depth = min(1.0, cog.tracking_depth + 0.1 * sub_count)
        else:
            cog.tracking_depth = max(0.0, cog.tracking_depth - 0.05)

        # metacognition：可执行则上升
        if parse_result.is_actionable:
            cog.metacognition = min(1.0, cog.metacognition + 0.05)
        else:
            cog.metacognition = max(0.0, cog.metacognition - 0.02)

        # stability：基于置信度
        if intent.confidence >= 0.7:
            cog.stability = min(1.0, cog.stability + 0.05)
        elif intent.confidence < 0.4:
            cog.stability = max(0.0, cog.stability - 0.05)

        session.touch()

    # ── 内部方法 ───────────────────────────────────────────────────────

    def _build_parse_context(self, session: Session) -> ParseContext:
        """从 Session 构建 ParseContext（新建，不恢复历史以简化）。"""
        return ParseContext(session_id=session.session_id)

    def _run_in_executor(self, func, *args):
        """将同步阻塞调用放入线程池执行。"""
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, lambda: func(*args))

    def _call_compiler(
        self,
        query: str,
        session: Session,
        parse_result: ParseResult,
    ) -> Optional[str]:
        """
        调用编译器。

        支持两种模式：
        1. 统一对象：调用 .process() 或 .compile()
        2. 分阶段字典：包含 header_injector / syntactic_decomposer / macro_micro_quantizer
        """
        if self._compiler is None:
            return None

        # 模式1：统一对象
        if hasattr(self._compiler, "process") and callable(self._compiler.process):
            try:
                result = self._compiler.process(query, session, parse_result)
                return str(result) if result is not None else None
            except Exception as exc:
                return f"Compiler process error: {exc}"

        if hasattr(self._compiler, "compile") and callable(self._compiler.compile):
            try:
                result = self._compiler.compile(query, session, parse_result)
                return str(result) if result is not None else None
            except Exception as exc:
                return f"Compiler compile error: {exc}"

        # 模式2：分阶段字典
        if isinstance(self._compiler, dict):
            return self._call_compiler_stages(query, session, parse_result)

        return None

    def _call_compiler_stages(
        self,
        query: str,
        session: Session,
        parse_result: ParseResult,
    ) -> str:
        """手动调用编译器三阶段（向后兼容）。"""
        result_parts: List[str] = []
        session_history = [
            {"role": t.role, "content": t.content}
            for t in session.history[-5:]
        ]

        # Stage 1: HeaderInjector
        header_injector = self._compiler.get("header_injector")
        if header_injector and hasattr(header_injector, "inject"):
            try:
                injection = header_injector.inject(
                    raw_text=query,
                    session_id=session.session_id,
                    session_history=session_history,
                    turn_index=session.turn_count,
                )
                result_parts.append(f"HeaderInjector: {len(injection.replacements)} replacements")
            except Exception as exc:
                result_parts.append(f"HeaderInjector failed: {exc}")

        # Stage 2: SyntacticDecomposer
        syntactic_decomposer = self._compiler.get("syntactic_decomposer")
        if syntactic_decomposer and hasattr(syntactic_decomposer, "decompose"):
            try:
                clauses = syntactic_decomposer.decompose(query)
                result_parts.append(f"SyntacticDecomposer: {len(clauses)} clauses")
            except Exception as exc:
                result_parts.append(f"SyntacticDecomposer failed: {exc}")

        # Stage 3: MacroMicroQuantizer
        macro_micro_quantizer = self._compiler.get("macro_micro_quantizer")
        if macro_micro_quantizer and hasattr(macro_micro_quantizer, "quantize"):
            try:
                try:
                    from core.agent.discourse_block_tree.models import EDU
                    edus = [EDU(raw_text=query)]
                    quantized = macro_micro_quantizer.quantize(edus)
                    result_parts.append(f"MacroMicroQuantizer: {len(quantized)} EDUs")
                except ImportError:
                    result_parts.append("MacroMicroQuantizer: EDU model not available")
            except Exception as exc:
                result_parts.append(f"MacroMicroQuantizer failed: {exc}")

        return "; ".join(result_parts) if result_parts else "Compiler: no stages executed"
