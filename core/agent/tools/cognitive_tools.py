# -*- coding: utf-8 -*-
"""
core/agent/tools/cognitive_tools.py
───────────────────────────────────
Tool Registry — 原子认知工具包装层（v2.4 新增）。

包装现有规则引擎（Layer 0+1）的已验证方法，暴露统一接口
供 Blueprint Executor 调用。不重新实现任何算法。

设计原则：
  - 每个工具只包装一个现有 Stage，不混合逻辑
  - 工具之间通过 state 字典显式共享状态，禁止隐式全局变量
  - 新增工具只需调用 CognitiveTools.register() 并在 Blueprint 中引用
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1
from core.agent.v3_common.models import (
    IntentContext, ParseContext, ParseResult, TaskGraph, Entity,
    Ambiguity, Intent,
)
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.llm_providers.base import GenerateRequest
from core.agent.config import get_config


@dataclass
class ExecutionContext:
    """
    跨工具共享的执行上下文。包含用户输入、会话状态、
    以及现有引擎实例的引用。

    所有工具函数签名统一为 (ExecutionContext, Dict) -> Any。
    """
    raw_input: str
    history: List[Any] = field(default_factory=list)
    profile: Optional[Any] = None
    parse_context: Optional[ParseContext] = None
    intent_context: Optional[IntentContext] = None
    pcr_instance: Optional[RuleBasedPCR] = None
    parser_instance: Optional[IntentParser] = None
    llm_provider: Optional[Any] = None
    router_decision: Optional[Any] = None
    tool_timeout_ms: int = 5000
    # 运行时计时器
    _start_ms: float = 0.0

    def __post_init__(self):
        if self._start_ms == 0.0:
            self._start_ms = time.time()

    def elapsed_ms(self) -> float:
        return (time.time() - self._start_ms) * 1000.0


# ═══════════════════════════════════════════════════════════════════════════════
# CognitiveTools
# ═══════════════════════════════════════════════════════════════════════════════

class CognitiveTools:
    """
    原子工具接口。底层直接调用 rule_based.py / intent_parser.py 的
    已验证逻辑，不重新实现任何算法。
    """

    _REGISTRY: Dict[str, Callable[[ExecutionContext, Dict], Any]] = {}

    @classmethod
    def register(cls, name: str, fn: Callable[[ExecutionContext, Dict], Any]):
        cls._REGISTRY[name] = fn

    @classmethod
    def run(cls, name: str, ctx: ExecutionContext, state: Dict) -> Any:
        fn = cls._REGISTRY.get(name)
        if fn is None:
            raise KeyError(f"Tool '{name}' not registered in CognitiveTools")
        return fn(ctx, state)

    @classmethod
    def list_registered(cls) -> List[str]:
        return list(cls._REGISTRY.keys())

    @classmethod
    def _ensure_pcr(cls, ctx: ExecutionContext) -> RuleBasedPCR:
        if ctx.pcr_instance is None:
            raise RuntimeError("ExecutionContext.pcr_instance is None")
        return ctx.pcr_instance

    @classmethod
    def _ensure_parser(cls, ctx: ExecutionContext) -> IntentParser:
        if ctx.parser_instance is None:
            raise RuntimeError("ExecutionContext.parser_instance is None")
        return ctx.parser_instance

    # ── 工具实现 ───────────────────────────────────────────────────────

    @classmethod
    def pcr_evaluate(cls, ctx: ExecutionContext, state: Dict) -> PCROutput_v1:
        """包装 RuleBasedPCR.evaluate()。"""
        pcr = cls._ensure_pcr(ctx)
        inp = PCRInput_v1(query=ctx.raw_input, session_history=ctx.history)
        return pcr.evaluate(inp)

    @classmethod
    def intent_parser_full_pipeline(cls, ctx: ExecutionContext, state: Dict) -> ParseResult:
        """包装 IntentParser.parse() 完整流水线。"""
        parser = cls._ensure_parser(ctx)
        if ctx.intent_context is None:
            pcr_out = state.get("pcr_evaluate")
            if pcr_out is not None:
                ctx.intent_context = IntentContext.from_pcr_output(pcr_out)
            else:
                raise RuntimeError("intent_parser_full_pipeline requires pcr_evaluate in state")
        if ctx.parse_context is None:
            ctx.parse_context = ParseContext()
        return parser.parse(ctx.raw_input, ctx.intent_context, ctx.parse_context)

    @classmethod
    def extract_entities(cls, ctx: ExecutionContext, state: Dict) -> List[Entity]:
        """包装 IntentParser._extract_entities()。"""
        parser = cls._ensure_parser(ctx)
        pcr_out = state.get("pcr_evaluate")
        if ctx.intent_context is None and pcr_out is not None:
            ctx.intent_context = IntentContext.from_pcr_output(pcr_out)
        if ctx.intent_context is None:
            raise RuntimeError("extract_entities requires IntentContext")
        config = parser._build_parser_config(ctx.intent_context)
        return parser._extract_entities(ctx.raw_input, config, ctx.intent_context)

    @classmethod
    def detect_ambiguities(cls, ctx: ExecutionContext, state: Dict) -> List[Ambiguity]:
        """包装 IntentParser._detect_ambiguities()。"""
        parser = cls._ensure_parser(ctx)
        intent = state.get("parsed_intent")
        if intent is None:
            parse_result = state.get("intent_parser_full_pipeline")
            if isinstance(parse_result, ParseResult) and parse_result.intent is not None:
                intent = parse_result.intent
        if intent is None:
            raise RuntimeError("detect_ambiguities requires parsed_intent in state")
        entities = state.get("extract_entities", [])
        if ctx.intent_context is None:
            pcr_out = state.get("pcr_evaluate")
            if pcr_out is not None:
                ctx.intent_context = IntentContext.from_pcr_output(pcr_out)
        if ctx.intent_context is None:
            raise RuntimeError("detect_ambiguities requires IntentContext")
        return parser._detect_ambiguities(intent, entities, ctx.intent_context)

    @classmethod
    def build_task_graph(cls, ctx: ExecutionContext, state: Dict) -> TaskGraph:
        """包装 IntentParser._build_task_graph()。"""
        parser = cls._ensure_parser(ctx)
        intent = state.get("parsed_intent")
        if intent is None:
            parse_result = state.get("intent_parser_full_pipeline")
            if isinstance(parse_result, ParseResult) and parse_result.intent is not None:
                intent = parse_result.intent
        if intent is None:
            raise RuntimeError("build_task_graph requires parsed_intent in state")
        if ctx.intent_context is None:
            pcr_out = state.get("pcr_evaluate")
            if pcr_out is not None:
                ctx.intent_context = IntentContext.from_pcr_output(pcr_out)
        if ctx.intent_context is None:
            raise RuntimeError("build_task_graph requires IntentContext")
        return parser._build_task_graph(intent, ctx.intent_context)

    @classmethod
    def llm_generate_explanation(cls, ctx: ExecutionContext, state: Dict) -> str:
        """使用 LLM 生成针对当前输入的解释文本。"""
        if ctx.llm_provider is None:
            return f"[系统未配置 LLM，无法生成解释：{ctx.raw_input}]"

        pcr_out = state.get("pcr_evaluate")
        system_prompt = "你是一名技术助手，请根据用户输入生成简洁的中文操作说明。"
        user_prompt = f"用户输入：{ctx.raw_input}\n\n请生成一段简短的中文解释说明。"

        from core.agent.llm_providers import GenerateRequest
        req = GenerateRequest(
            system_prompt=system_prompt,
            prompt=user_prompt,
            max_tokens=256,
            temperature=0.3,
        )
        res = ctx.llm_provider.generate(req)
        if res.metrics.success:
            return res.text.strip()
        return f"[生成解释失败：{res.metrics.error_message or 'unknown'}]"

    @classmethod
    def ask_user(cls, ctx: ExecutionContext, state: Dict) -> Dict[str, Any]:
        """包装歧义消解 → 生成 ClarificationPayload。"""
        ambiguities = state.get("detect_ambiguities", [])
        return {
            "type": "clarification",
            "ambiguities_count": len(ambiguities),
            "ambiguities_summary": [str(a) for a in ambiguities],
            "message": "检测到歧义，请澄清以下信息。",
        }

    @classmethod
    def conversation_handler(cls, ctx: ExecutionContext, state: Dict) -> Dict[str, Any]:
        """
        对话处理器：当系统无法识别用户意图时，让 LLM 作为核心决策层处理。

        与 strategy_completer 不同：
        - 给 LLM 完整的系统上下文（包括用户原文、历史、系统状态、蓝图、编排）
        - LLM 是核心，不是辅助
        - 输出自然语言回复，不是 JSON 策略选择
        """
        if ctx.llm_provider is None:
            return {
                "action": "direct_reply",
                "text": "[系统未配置 LLM，无法处理自然语言对话]",
            }

        pcr_out = state.get("pcr_evaluate")
        parse_result = state.get("intent_parser_full_pipeline")
        query = ctx.raw_input

        # 构建历史摘要
        history_summary = []
        for h in (ctx.history or [])[-5:]:
            if isinstance(h, dict):
                role = h.get("role", "user")
                content = h.get("content", "")
                history_summary.append(f"{role}: {content}")

        # 构建系统状态（包含蓝图、编排等）
        system_state = {
            "expectation": getattr(pcr_out, "expectation", "UNKNOWN"),
            "noise": round(getattr(pcr_out, "noise_level", 0.0), 2),
            "complexity": round(getattr(pcr_out, "complexity_level", 0.0), 2),
            "cognitive": {
                "metacognition": round(getattr(pcr_out.cognitive_profile, "metacognition", 0.0), 2) if pcr_out else 0.0,
            },
            "intent_category": getattr(parse_result.intent.category, "value", "UNKNOWN") if parse_result else "UNKNOWN",
            "intent_confidence": round(getattr(parse_result.intent, "confidence", 0.0), 2) if parse_result else 0.0,
            "entity_count": len(getattr(parse_result.intent, "entities", [])) if parse_result else 0,
            "ambiguity_count": len(getattr(parse_result.intent, "ambiguities", [])) if parse_result else 0,
            "available_blueprints": list(state.get("available_blueprints", ["RULE_FAST_PATH", "RULE_TUTORIAL", "RULE_INTERACTIVE"])),
            "router_decision": state.get("router_decision", "N/A"),
        }

        provider = ctx.llm_provider

        # 从配置加载系统提示词和参数（通过 ConfigManager 单例访问）
        from core.agent.config import config as cfg_mgr
        sp_cfg = cfg_mgr.get_system_prompt("conversation_handler")
        profile_cfg = cfg_mgr.get_llm_profile("local_thinking" if (provider and getattr(provider, "name", "").lower() in ("lmstudio", "local")) else "default")

        system_prompt = sp_cfg.index_card
        glossary = sp_cfg.parameter_glossary or {}

        # 构建历史文本
        history_text = "\n".join(history_summary) if history_summary else "（无）"
        system_state_json = json.dumps(system_state, ensure_ascii=False, indent=2)

        # 动态构建参数速查（从配置读取，而非硬编码）
        glossary_lines = []
        for key, desc in glossary.items():
            if key in system_state:
                glossary_lines.append(f"- {key}: {desc}")
        glossary_text = "\n".join(glossary_lines) if glossary_lines else "（无）"

        # 用户提示：动态数据 + 参数速查字典
        user_prompt = f"""用户输入："{query}"

历史（最近5轮）：
{history_text}

参数速查：
{glossary_text}

当前状态：
{system_state_json}

请按格式回复：分析 → Final Output"""

        req = GenerateRequest(
            system_prompt=system_prompt,
            prompt=user_prompt,
            max_tokens=profile_cfg.max_tokens,
            temperature=profile_cfg.temperature,
            timeout_ms=profile_cfg.timeout_ms,
        )

        res = provider.generate(req)
        if res.metrics.success:
            text = res.text.strip()
            # 如果 LLM 仍然输出了 JSON，尝试解析
            if text.startswith("{") and text.endswith("}"):
                try:
                    action = json.loads(text)
                    if isinstance(action, dict) and "text" in action:
                        return {"action": "direct_reply", "text": action["text"]}
                except json.JSONDecodeError:
                    pass
            return {
                "action": "direct_reply",
                "text": text,
            }

        return {
            "action": "direct_reply",
            "text": f"[LLM 调用失败: {res.metrics.error_type}]",
        }

    @classmethod
    def strategy_completer(cls, ctx: ExecutionContext, state: Dict) -> Dict[str, Any]:
        """
        策略补全器：当规则引擎无法确定意图时，直接让 LLM 生成交互策略。

        不尝试修正分类，而是直接返回行动策略：
        - ask_user: 向用户追问
        - direct_reply: 直接给出解释/教程
        - execute: 执行某个蓝图

        返回 {"action": "...", ...} 结构，下游直接执行。
        """
        if ctx.llm_provider is None:
            return {
                "action": "direct_reply",
                "text": "[规则引擎无法解析，且未配置 LLM Provider]",
            }

        pcr_out = state.get("pcr_evaluate")
        parse_result = state.get("intent_parser_full_pipeline")

        # 构建结构化上下文（不含用户原文，只传枚举值和摘要）
        context = {
            "expectation": getattr(pcr_out, "expectation", "UNKNOWN"),
            "noise": getattr(pcr_out, "noise_level", 0.0),
            "complexity": getattr(pcr_out, "complexity_level", 0.0),
            "cognitive": {
                "metacognition": getattr(pcr_out.cognitive_profile, "metacognition", 0.0) if pcr_out else 0.0,
            },
            "intent_category": getattr(parse_result.intent.category, "value", "UNKNOWN") if parse_result else "UNKNOWN",
            "intent_confidence": getattr(parse_result.intent, "confidence", 0.0) if parse_result else 0.0,
            "entity_count": len(getattr(parse_result.intent, "entities", [])) if parse_result else 0,
            "ambiguity_count": len(getattr(parse_result.intent, "ambiguities", [])) if parse_result else 0,
        }

        provider = ctx.llm_provider

        # 从配置加载系统提示词和 LLM 参数（通过 ConfigManager 单例访问）
        from core.agent.config import config as cfg_mgr
        sp_cfg = cfg_mgr.get_system_prompt("strategy_completer")
        profile_cfg = cfg_mgr.get_llm_profile("fast")

        req = GenerateRequest(
            prompt=f"""用户输入已被规则引擎处理，但无法确定意图。请根据以下上下文选择最合适的交互策略。

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

可用策略：
1. ask_user - 向用户追问以获取更多信息
2. direct_reply - 直接给出解释、教程或建议
3. execute - 执行某个蓝图（默认 RULE_FAST_PATH）

输出要求：
必须且只能是合法的 JSON 对象，禁止任何解释、思考过程、Markdown 代码块。
""",
            system_prompt=sp_cfg.index_card,
            max_tokens=profile_cfg.max_tokens,
            temperature=profile_cfg.temperature,
            timeout_ms=profile_cfg.timeout_ms,
        )

        res = provider.generate(req)
        if res.metrics.success:
            # 尝试解析 JSON
            text = res.text.strip()
            # 移除可能的 markdown 代码块
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                action = json.loads(text)
                if isinstance(action, dict) and "action" in action:
                    return action
            except json.JSONDecodeError:
                pass

            # 解析失败，返回直接回复
            return {
                "action": "direct_reply",
                "text": res.text[:500],
            }

        return {
            "action": "direct_reply",
            "text": f"[策略补全器失败: {res.metrics.error_type}]",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _summarize_for_llm(state: Dict) -> str:
    """为 LLM 生成结构化摘要（不含用户原文，只传枚举值 + 实体统计）。"""
    pcr_out = state.get("pcr_evaluate")
    summary = {
        "expectation": getattr(pcr_out, "expectation", "UNKNOWN"),
        "noise_level": getattr(pcr_out, "noise_level", 0.0),
        "complexity_level": getattr(pcr_out, "complexity_level", 0.0),
        "entity_count": len(state.get("extract_entities", [])),
        "ambiguity_count": len(state.get("detect_ambiguities", [])),
    }
    return json.dumps(summary, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 启动注册
# ═══════════════════════════════════════════════════════════════════════════════

def _register_all():
    ct = CognitiveTools
    ct.register("pcr_evaluate", ct.pcr_evaluate)
    ct.register("intent_parser_full_pipeline", ct.intent_parser_full_pipeline)
    ct.register("extract_entities", ct.extract_entities)
    ct.register("detect_ambiguities", ct.detect_ambiguities)
    ct.register("build_task_graph", ct.build_task_graph)
    ct.register("ask_user", ct.ask_user)
    ct.register("strategy_completer", ct.strategy_completer)
    ct.register("conversation_handler", ct.conversation_handler)
    # 兼容旧蓝图 LLM_TUTORIAL（保留别名）
    ct.register("llm_generate_explanation", ct.strategy_completer)


_register_all()
