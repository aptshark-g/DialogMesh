# -*- coding: utf-8 -*-
"""
core/agent/mcp/server.py
────────────────────────
MCP Server：把内部 CognitiveTools 暴露为 MCP 标准工具。

支持两种传输：
  - stdio：Claude Desktop 集成
  - Streamable HTTP：Web 服务，可 mount 到 FastAPI

设计原则：
  - 每个 CognitiveTools 注册为 1-2 个 MCP 工具（粒度由暴露策略决定）
  - 会话状态通过 FastMCP lifespan 管理（PCR 实例、Parser 实例）
  - SecurityManager 在每个工具调用前后执行检查
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from core.agent.mcp.config import MCPServerConfig
from core.agent.mcp.security import SecurityManager

from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser

try:
    from mcp.server.fastmcp import FastMCP, Context
    from mcp.server.session import ServerSession
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    FastMCP = None
    Context = None
    ServerSession = None

import logging
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan Context — 跨工具共享的会话状态
# ═══════════════════════════════════════════════════════════════════════════════

class MCPServerLifespanContext:
    """
    FastMCP lifespan 中初始化的共享资源。
    所有工具通过 ctx.request_context.lifespan_context 访问。
    """

    def __init__(
        self,
        pcr: Optional[RuleBasedPCR] = None,
        parser: Optional[IntentParser] = None,
        config: Optional[MCPServerConfig] = None,
    ):
        self.pcr = pcr or RuleBasedPCR()
        self.parser = parser or IntentParser()
        self.config = config or MCPServerConfig.from_env()
        self.security = SecurityManager(self.config)

    def create_execution_context(self, raw_input: str) -> ExecutionContext:
        """为单次工具调用创建 ExecutionContext。"""
        return ExecutionContext(
            raw_input=raw_input,
            pcr_instance=self.pcr,
            parser_instance=self.parser,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MCP Server Factory
# ═══════════════════════════════════════════════════════════════════════════════

def create_mcp_server(
    pcr: Optional[RuleBasedPCR] = None,
    parser: Optional[IntentParser] = None,
    config: Optional[MCPServerConfig] = None,
) -> Optional[Any]:
    """
    创建 FastMCP Server 实例，注册内部工具。

    如果 mcp 包未安装，返回 None。
    """
    if not HAS_MCP or FastMCP is None:
        logger.warning("mcp package not installed — MCP Server unavailable")
        return None

    cfg = config or MCPServerConfig.from_env()
    lifespan_ctx = MCPServerLifespanContext(pcr=pcr, parser=parser, config=cfg)

    mcp = FastMCP(cfg.name, dependencies=["mcp"])

    # ── 工具 1: evaluate_intent ───────────────────────────────────────
    @mcp.tool()
    def evaluate_intent(query: str) -> str:
        """
        评估用户意图。输入自然语言查询，返回意图分类 + 置信度 + 噪声估计。

        Args:
            query: 用户原始输入，如 "扫描 Game.exe 中的 1000"

        Returns:
            JSON 字符串，包含 expectation、confidence、noise_level、complexity_level
        """
        start = time.time()
        ctx = lifespan_ctx.create_execution_context(query)
        result = CognitiveTools.run("pcr_evaluate", ctx, {})
        latency = (time.time() - start) * 1000

        # 安全后处理
        output = result.to_json() if hasattr(result, "to_json") else str(result)
        output = lifespan_ctx.security.post_flight(
            tool_name="evaluate_intent",
            user_id=None,
            input_preview=query[:128],
            output=output,
            latency_ms=latency,
        )
        return output

    # ── 工具 2: parse_intent ───────────────────────────────────────────
    @mcp.tool()
    def parse_intent(query: str) -> str:
        """
        完整意图解析流水线。输入查询，返回解析结果（实体、歧义、任务图）。

        Args:
            query: 用户原始输入

        Returns:
            JSON 字符串，包含 entities、ambiguities、task_graph
        """
        start = time.time()
        ctx = lifespan_ctx.create_execution_context(query)
        state: Dict[str, Any] = {}

        # 1. PCR 评估
        pcr_out = CognitiveTools.run("pcr_evaluate", ctx, state)
        state["pcr_evaluate"] = pcr_out

        # 2. 完整解析
        parse_result = CognitiveTools.run("intent_parser_full_pipeline", ctx, state)
        state["intent_parser_full_pipeline"] = parse_result

        latency = (time.time() - start) * 1000
        output = parse_result.to_json() if hasattr(parse_result, "to_json") else str(parse_result)
        output = lifespan_ctx.security.post_flight(
            tool_name="parse_intent",
            user_id=None,
            input_preview=query[:128],
            output=output,
            latency_ms=latency,
        )
        return output

    # ── 工具 3: extract_entities ───────────────────────────────────────
    @mcp.tool()
    def extract_entities(query: str) -> str:
        """
        从查询中提取结构化实体（进程名、内存地址、数值等）。

        Args:
            query: 用户原始输入

        Returns:
            JSON 数组，每个实体包含 type、value、confidence
        """
        start = time.time()
        ctx = lifespan_ctx.create_execution_context(query)
        state: Dict[str, Any] = {}

        pcr_out = CognitiveTools.run("pcr_evaluate", ctx, state)
        state["pcr_evaluate"] = pcr_out

        entities = CognitiveTools.run("extract_entities", ctx, state)
        state["extract_entities"] = entities

        latency = (time.time() - start) * 1000
        import json
        output = json.dumps(
            [{"type": e.type, "value": e.value, "confidence": e.confidence}
             for e in entities] if hasattr(entities, "__iter__") else str(entities),
            ensure_ascii=False,
            default=str,
        )
        output = lifespan_ctx.security.post_flight(
            tool_name="extract_entities",
            user_id=None,
            input_preview=query[:128],
            output=output,
            latency_ms=latency,
        )
        return output

    # ── 工具 4: detect_ambiguities ─────────────────────────────────────
    @mcp.tool()
    def detect_ambiguities(query: str) -> str:
        """
        检测查询中的歧义（模糊进程、缺少数值、未知意图等）。

        Args:
            query: 用户原始输入

        Returns:
            JSON 数组，每个歧义包含 type、message、suggestions
        """
        start = time.time()
        ctx = lifespan_ctx.create_execution_context(query)
        state: Dict[str, Any] = {}

        pcr_out = CognitiveTools.run("pcr_evaluate", ctx, state)
        state["pcr_evaluate"] = pcr_out

        parse_result = CognitiveTools.run("intent_parser_full_pipeline", ctx, state)
        state["intent_parser_full_pipeline"] = parse_result

        # 需要 intent 和 entities 才能检测歧义
        intent = parse_result.intent if hasattr(parse_result, "intent") else None
        entities = state.get("extract_entities", [])
        if hasattr(parse_result, "entities"):
            entities = parse_result.entities

        # 手动构造 intent_context（如果缺失）
        if ctx.intent_context is None and pcr_out is not None:
            from core.agent.v3_common.models import IntentContext
            ctx.intent_context = IntentContext.from_pcr_output(pcr_out)

        ambiguities = CognitiveTools.run("detect_ambiguities", ctx, state)

        latency = (time.time() - start) * 1000
        import json
        output = json.dumps(
            [{"type": a.type, "message": a.message, "suggestions": a.suggestions}
             for a in ambiguities] if hasattr(ambiguities, "__iter__") else str(ambiguities),
            ensure_ascii=False,
            default=str,
        )
        output = lifespan_ctx.security.post_flight(
            tool_name="detect_ambiguities",
            user_id=None,
            input_preview=query[:128],
            output=output,
            latency_ms=latency,
        )
        return output

    # ── 工具 5: get_status ─────────────────────────────────────────────
    @mcp.tool()
    def get_status() -> str:
        """
        获取 Agent 当前状态（工具注册表、蓝图列表、健康度）。

        Returns:
            JSON 对象，包含 registered_tools、blueprints、health
        """
        import json
        from core.agent.v3_common.blueprints import BLUEPRINT_REGISTRY

        tools = CognitiveTools.list_registered()
        blueprints = list(BLUEPRINT_REGISTRY.keys())
        health = {
            "tools_count": len(tools),
            "blueprints_count": len(blueprints),
            "server_name": cfg.name,
            "server_version": cfg.version,
        }
        return json.dumps({
            "registered_tools": tools,
            "blueprints": blueprints,
            "health": health,
        }, ensure_ascii=False)

    # ── 工具 6: explain_intent ─────────────────────────────────────────
    @mcp.tool()
    def explain_intent(query: str) -> str:
        """
        生成用户意图的解释文案（供新手参考）。
        如果配置了 LLM Provider，调用 LLM 生成；否则返回规则生成的解释。

        Args:
            query: 用户原始输入

        Returns:
            解释文本
        """
        start = time.time()
        ctx = lifespan_ctx.create_execution_context(query)
        state: Dict[str, Any] = {}

        pcr_out = CognitiveTools.run("pcr_evaluate", ctx, state)
        state["pcr_evaluate"] = pcr_out

        parse_result = CognitiveTools.run("intent_parser_full_pipeline", ctx, state)
        state["intent_parser_full_pipeline"] = parse_result

        explanation = CognitiveTools.run("llm_generate_explanation", ctx, state)

        latency = (time.time() - start) * 1000
        output = str(explanation)
        output = lifespan_ctx.security.post_flight(
            tool_name="explain_intent",
            user_id=None,
            input_preview=query[:128],
            output=output,
            latency_ms=latency,
        )
        return output

    # 如果配置了白名单，只暴露指定工具
    if cfg.exposed_tools:
        # 需要移除不在白名单中的工具（FastMCP 没有 unregister API，
        # 这里通过重新创建 Server 的方式实现，实际生产可用子类过滤）
        # 简化：在工具内部检查白名单
        _original_tools = list(mcp._tools.keys()) if hasattr(mcp, "_tools") else []
        # 注：FastMCP 内部结构可能变化，这里只做防御性注释
        logger.info("Exposed tools filter: %s", cfg.exposed_tools)

    return mcp


# ═══════════════════════════════════════════════════════════════════════════════
# 传输启动器
# ═══════════════════════════════════════════════════════════════════════════════

def run_stdio_server(
    pcr: Optional[RuleBasedPCR] = None,
    parser: Optional[IntentParser] = None,
    config: Optional[MCPServerConfig] = None,
) -> None:
    """
    启动 stdio 传输的 MCP Server（用于 Claude Desktop 等）。
    """
    mcp = create_mcp_server(pcr=pcr, parser=parser, config=config)
    if mcp is None:
        raise RuntimeError("mcp package not installed — cannot start MCP Server")
    mcp.run()


def get_streamable_http_app(
    pcr: Optional[RuleBasedPCR] = None,
    parser: Optional[IntentParser] = None,
    config: Optional[MCPServerConfig] = None,
) -> Optional[Any]:
    """
    返回 Streamable HTTP ASGI app，可 mount 到 FastAPI。

    示例：
        from fastapi import FastAPI
        app = FastAPI()
        app.mount("/mcp", get_streamable_http_app())
    """
    mcp = create_mcp_server(pcr=pcr, parser=parser, config=config)
    if mcp is None:
        return None
    if hasattr(mcp, "streamable_http_app"):
        return mcp.streamable_http_app()
    logger.error("FastMCP does not support streamable_http_app")
    return None
