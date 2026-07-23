# -*- coding: utf-8 -*-
"""
tests/test_v3_orchestrator.py
────────────────────────────
Orchestrator v3.0 测试套件。

覆盖范围：
- 5 阶段处理流水线（感知→编译→规划→验证→生成）
- 流式处理（process_request_stream）
- 6 个 LLM 实例配置解析
- 降级回退（fallback answer）
- 并发安全（多会话 turn index 递增）
- 事件构建（WebSocketEvent 生成）

运行方式：
  pytest tests/test_v3_orchestrator.py -v

版本：3.0.0
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from core.agent.orchestrator import Orchestrator, OrchestratorResult, LLMInstanceConfig
from core.agent.v3_legacy.data_models import (
    EventType,
    Intent_v3,
    TaskGraph_v3,
    TaskNode_v3,
    UserMessage_v3,
    WebSocketEvent,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mock_llm_providers() -> MagicMock:
    """构造 mock LLM ProviderManager。"""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=MagicMock(success=True, text="mock answer"))
    mock.get = MagicMock(return_value=MagicMock())
    mock.get_all = MagicMock(return_value={"mock": MagicMock()})
    return mock


def _make_mock_pcr() -> MagicMock:
    """构造 mock PCR 引擎。"""
    mock = MagicMock()
    mock.evaluate = MagicMock(return_value=MagicMock(
        expectation="TOOL",
        noise_level=0.1,
        complexity_level=0.2,
        confidence=0.9,
    ))
    return mock


def _make_mock_intent_parser() -> MagicMock:
    """构造 mock Intent Parser。"""
    from core.agent.models import Entity, EntityType, Intent, IntentCategory, ParseResult

    mock = MagicMock()
    intent = Intent(
        category=IntentCategory.SCAN_MEMORY,
        raw_input="scan 100",
        normalized_input="scan 100",
        confidence=0.95,
        entities=[Entity(type=EntityType.NUMERIC_VALUE, value="100", raw_text="100", confidence=0.9)],
    )
    mock.parse = MagicMock(return_value=ParseResult(intent=intent, is_actionable=True))
    return mock


def _make_mock_planning_skill() -> MagicMock:
    """构造 mock Planning Skill。"""
    mock = MagicMock()
    plan_result = MagicMock()
    plan_result.success = True
    tg = TaskGraph_v3()
    n1 = TaskNode_v3(name="scan", goal="find address")
    tg.add_node(n1)
    plan_result.task_graph = tg
    mock.plan = AsyncMock(return_value=plan_result)
    return mock


def _make_mock_cognitive_compiler() -> MagicMock:
    """构造 mock Cognitive Compiler。"""
    mock = MagicMock()
    mock.compile = MagicMock(return_value=MagicMock())
    return mock


def _make_mock_context_manager() -> MagicMock:
    """构造 mock Context Manager。"""
    mock = MagicMock()
    mock.create_session = AsyncMock(return_value=MagicMock(session_id="test-sess-123"))
    mock.get_session = MagicMock(return_value=MagicMock())
    return mock


def _make_mock_topic_tree() -> MagicMock:
    """构造 mock Topic Tree。"""
    mock = MagicMock()
    return mock


def _make_mock_observability() -> MagicMock:
    """构造 mock Telemetry / Observability。"""
    mock = MagicMock()
    mock.record_turn = AsyncMock(return_value=(MagicMock(), []))
    return mock


@pytest.fixture
def orchestrator() -> Orchestrator:
    """使用全 mock 依赖构造的 Orchestrator 实例。"""
    orch = Orchestrator(
        pcr_engine=_make_mock_pcr(),
        intent_parser=_make_mock_intent_parser(),
        planning_skill=_make_mock_planning_skill(),
        cognitive_compiler=_make_mock_cognitive_compiler(),
        context_manager=_make_mock_context_manager(),
        topic_tree=_make_mock_topic_tree(),
        observability=_make_mock_observability(),
        llm_providers=_make_mock_llm_providers(),
        config={
            "pcr_llm": {"cognitive_mode": "fast", "provider": "mock", "model": "mock"},
            "intent_llm": {"cognitive_mode": "fast", "provider": "mock", "model": "mock"},
            "planning_llm": {"cognitive_mode": "deep", "provider": "mock", "model": "mock"},
            "meta_cognitive_llm": {"cognitive_mode": "deep", "provider": "mock", "model": "mock"},
            "reflective_llm": {"cognitive_mode": "reflective", "provider": "mock", "model": "mock"},
            "answer_llm": {"cognitive_mode": "deep", "provider": "mock", "model": "mock"},
        },
    )
    return orch


@pytest.fixture
def user_message() -> UserMessage_v3:
    """标准测试用户消息。"""
    return UserMessage_v3(session_id="test-sess-123", content="scan memory for 100")


# ═══════════════════════════════════════════════════════════════════════════════
# 基本处理测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessRequest:
    """process_request 主入口测试。"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试完整 5 阶段流水线成功执行。"""
        result = await orchestrator.process_request(user_message)
        assert isinstance(result, OrchestratorResult)
        assert result.session_id == "test-sess-123"
        assert result.turn_index == 0
        assert result.answer != ""
        assert result.latency_ms > 0
        assert result.task_graph is not None
        assert len(result.trace_log) > 0
        assert len(result.events) > 0

    @pytest.mark.asyncio
    async def test_turn_index_increments(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试多轮请求时 turn_index 递增。"""
        r1 = await orchestrator.process_request(user_message)
        r2 = await orchestrator.process_request(user_message)
        r3 = await orchestrator.process_request(user_message)
        assert r1.turn_index == 0
        assert r2.turn_index == 1
        assert r3.turn_index == 2

    @pytest.mark.asyncio
    async def test_concurrent_session_turns(self, orchestrator: Orchestrator):
        """测试多会话并发时 turn_index 独立递增。"""
        msg_a = UserMessage_v3(session_id="sess-a", content="hello")
        msg_b = UserMessage_v3(session_id="sess-b", content="world")

        tasks = [
            asyncio.create_task(orchestrator.process_request(msg_a)),
            asyncio.create_task(orchestrator.process_request(msg_b)),
            asyncio.create_task(orchestrator.process_request(msg_a)),
            asyncio.create_task(orchestrator.process_request(msg_b)),
        ]
        results = await asyncio.gather(*tasks)
        turns_a = [r.turn_index for r in results if r.session_id == "sess-a"]
        turns_b = [r.turn_index for r in results if r.session_id == "sess-b"]
        assert sorted(turns_a) == [0, 1]
        assert sorted(turns_b) == [0, 1]

    @pytest.mark.asyncio
    async def test_graceful_on_pcr_failure(self, user_message: UserMessage_v3):
        """测试 PCR 失败时流程仍继续（使用 stub）。"""
        bad_pcr = MagicMock()
        bad_pcr.evaluate = MagicMock(side_effect=RuntimeError("PCR crash"))

        orch = Orchestrator(
            pcr_engine=bad_pcr,
            intent_parser=_make_mock_intent_parser(),
            planning_skill=_make_mock_planning_skill(),
            cognitive_compiler=_make_mock_cognitive_compiler(),
            context_manager=_make_mock_context_manager(),
            topic_tree=_make_mock_topic_tree(),
            observability=_make_mock_observability(),
            llm_providers=_make_mock_llm_providers(),
            config={},
        )
        result = await orch.process_request(user_message)
        assert result.answer != ""
        assert not result.used_fallback

    @pytest.mark.asyncio
    async def test_graceful_on_intent_parser_failure(self, user_message: UserMessage_v3):
        """测试 Intent Parser 失败时流程仍继续。"""
        bad_parser = MagicMock()
        bad_parser.parse = MagicMock(side_effect=RuntimeError("Parser crash"))

        orch = Orchestrator(
            pcr_engine=_make_mock_pcr(),
            intent_parser=bad_parser,
            planning_skill=_make_mock_planning_skill(),
            cognitive_compiler=_make_mock_cognitive_compiler(),
            context_manager=_make_mock_context_manager(),
            topic_tree=_make_mock_topic_tree(),
            observability=_make_mock_observability(),
            llm_providers=_make_mock_llm_providers(),
            config={},
        )
        result = await orch.process_request(user_message)
        assert result.answer != ""

    @pytest.mark.asyncio
    async def test_graceful_on_planning_failure(self, user_message: UserMessage_v3):
        """测试 Planning Skill 失败时返回空 task_graph。"""
        bad_planning = MagicMock()
        bad_planning.plan = AsyncMock(side_effect=RuntimeError("Planning crash"))

        orch = Orchestrator(
            pcr_engine=_make_mock_pcr(),
            intent_parser=_make_mock_intent_parser(),
            planning_skill=bad_planning,
            cognitive_compiler=_make_mock_cognitive_compiler(),
            context_manager=_make_mock_context_manager(),
            topic_tree=_make_mock_topic_tree(),
            observability=_make_mock_observability(),
            llm_providers=_make_mock_llm_providers(),
            config={},
        )
        result = await orch.process_request(user_message)
        assert result.answer != ""
        assert result.task_graph is None

    @pytest.mark.asyncio
    async def test_fallback_answer_when_llm_unavailable(self, user_message: UserMessage_v3):
        """测试 LLM 不可用时回退到规则生成回复。"""
        bad_llm = MagicMock()
        bad_llm.generate = AsyncMock(side_effect=RuntimeError("LLM down"))
        bad_llm.get = MagicMock(return_value=None)
        bad_llm.get_all = MagicMock(return_value={})

        orch = Orchestrator(
            pcr_engine=_make_mock_pcr(),
            intent_parser=_make_mock_intent_parser(),
            planning_skill=_make_mock_planning_skill(),
            cognitive_compiler=_make_mock_cognitive_compiler(),
            context_manager=_make_mock_context_manager(),
            topic_tree=_make_mock_topic_tree(),
            observability=_make_mock_observability(),
            llm_providers=bad_llm,
            config={},
        )
        result = await orch.process_request(user_message)
        assert result.answer != ""
        assert "收到" in result.answer or "test" in result.answer.lower() or "recorded" in result.answer.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 流式处理测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStreamProcessing:
    """process_request_stream 流式处理测试。"""

    @pytest.mark.asyncio
    async def test_stream_yields_events(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试流式处理产生事件。"""
        events: List[WebSocketEvent] = []
        async for event in orchestrator.process_request_stream(user_message):
            events.append(event)
        assert len(events) > 0
        assert any(e.event_type == EventType.MESSAGE for e in events)

    @pytest.mark.asyncio
    async def test_stream_yields_task_graph_event(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试流式处理产生任务图事件。"""
        events: List[WebSocketEvent] = []
        async for event in orchestrator.process_request_stream(user_message):
            events.append(event)
        assert any(e.event_type == EventType.TASK_GRAPH for e in events)

    @pytest.mark.asyncio
    async def test_stream_error_handling(self, user_message: UserMessage_v3):
        """测试流式处理错误时产生 ERROR 事件。"""
        bad_parser = MagicMock()
        bad_parser.parse = MagicMock(side_effect=RuntimeError("Parser crash"))

        orch = Orchestrator(
            pcr_engine=_make_mock_pcr(),
            intent_parser=bad_parser,
            planning_skill=_make_mock_planning_skill(),
            cognitive_compiler=_make_mock_cognitive_compiler(),
            context_manager=_make_mock_context_manager(),
            topic_tree=_make_mock_topic_tree(),
            observability=_make_mock_observability(),
            llm_providers=_make_mock_llm_providers(),
            config={},
        )
        events: List[WebSocketEvent] = []
        async for event in orch.process_request_stream(user_message):
            events.append(event)
        assert any(e.event_type == EventType.ERROR for e in events)


# ═══════════════════════════════════════════════════════════════════════════════
# 内部阶段测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestInternalStages:
    """内部阶段实现测试。"""

    @pytest.mark.asyncio
    async def test_stage_1_parallel_execution(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试 Stage 1 PCR 与 Intent 并行执行。"""
        trace_log: List[str] = []
        pcr_output, intent_v3 = await orchestrator._stage_1_perception_and_intent(
            user_message, "test-sess", trace_log
        )
        assert pcr_output is not None
        assert intent_v3 is not None
        assert any("PCR" in t for t in trace_log)
        assert any("Intent" in t for t in trace_log)

    @pytest.mark.asyncio
    async def test_stage_4_validation_passes(self, orchestrator: Orchestrator):
        """测试 Stage 4 验证通过。"""
        from core.agent.models import IntentCategory

        intent = Intent_v3(category=IntentCategory.SCAN_MEMORY, confidence=0.8)
        tg = TaskGraph_v3()
        trace_log: List[str] = []
        passed = await orchestrator._stage_4_validate("sess", intent, tg, trace_log)
        assert passed is True

    @pytest.mark.asyncio
    async def test_stage_4_validation_fails_low_confidence(self, orchestrator: Orchestrator):
        """测试 Stage 4 低置信度导致验证失败。"""
        from core.agent.models import IntentCategory

        intent = Intent_v3(category=IntentCategory.SCAN_MEMORY, confidence=0.1)
        trace_log: List[str] = []
        passed = await orchestrator._stage_4_validate("sess", intent, None, trace_log)
        assert passed is False

    @pytest.mark.asyncio
    async def test_stage_5_parallel_generation(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试 Stage 5 Answer 与 Reflective 并行生成。"""
        from core.agent.models import IntentCategory

        intent = Intent_v3(category=IntentCategory.SCAN_MEMORY, confidence=0.8)
        trace_log: List[str] = []
        answer, reflection = await orchestrator._stage_5_generate(
            "sess", user_message, intent, None, True, trace_log
        )
        assert answer != ""
        assert reflection != ""
        assert any("Answer" in t for t in trace_log)
        assert any("Reflective" in t for t in trace_log)

    @pytest.mark.asyncio
    async def test_build_answer_prompt(self, orchestrator: Orchestrator, user_message: UserMessage_v3):
        """测试 Answer Prompt 构造。"""
        from core.agent.models import IntentCategory

        intent = Intent_v3(category=IntentCategory.SCAN_MEMORY, confidence=0.8)
        prompt = orchestrator._build_answer_prompt(user_message, intent, None, True)
        assert "User:" in prompt
        assert "scan memory for 100" in prompt
        assert "Intent: scan_memory" in prompt

    def test_fallback_answer_scan(self, orchestrator: Orchestrator):
        """测试扫描意图的回退回复。"""
        from core.agent.models import IntentCategory

        msg = UserMessage_v3(session_id="s", content="scan")
        intent = Intent_v3(category=IntentCategory.SCAN_MEMORY)
        answer = orchestrator._fallback_answer(msg, intent, None)
        assert "扫描" in answer

    def test_fallback_answer_analyze(self, orchestrator: Orchestrator):
        """测试分析意图的回退回复。"""
        from core.agent.models import IntentCategory

        msg = UserMessage_v3(session_id="s", content="analyze")
        intent = Intent_v3(category=IntentCategory.ANALYZE)
        answer = orchestrator._fallback_answer(msg, intent, None)
        assert "分析" in answer

    def test_fallback_answer_tutorial(self, orchestrator: Orchestrator):
        """测试教程意图的回退回复。"""
        from core.agent.models import IntentCategory

        msg = UserMessage_v3(session_id="s", content="tutorial")
        intent = Intent_v3(category=IntentCategory.TUTORIAL)
        answer = orchestrator._fallback_answer(msg, intent, None)
        assert "教程" in answer

    def test_fallback_answer_default(self, orchestrator: Orchestrator):
        """测试未知意图的回退回复。"""
        msg = UserMessage_v3(session_id="s", content="hello")
        answer = orchestrator._fallback_answer(msg, None, None)
        assert "收到" in answer or "message" in answer.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 事件构建测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventBuilding:
    """WebSocket 事件构建测试。"""

    def test_build_events_with_task_graph(self, orchestrator: Orchestrator):
        """测试有任务图时构建事件。"""
        tg = TaskGraph_v3()
        n1 = TaskNode_v3(name="scan")
        tg.add_node(n1)
        events = orchestrator._build_events("sess", 0, "answer", tg)
        assert len(events) >= 2
        assert events[0].event_type == EventType.MESSAGE
        assert any(e.event_type == EventType.TASK_GRAPH for e in events)

    def test_build_events_without_task_graph(self, orchestrator: Orchestrator):
        """测试无任务图时构建事件。"""
        events = orchestrator._build_events("sess", 0, "answer", None)
        assert len(events) == 1
        assert events[0].event_type == EventType.MESSAGE


# ═══════════════════════════════════════════════════════════════════════════════
# LLM 配置测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMConfig:
    """LLM 实例配置解析测试。"""

    def test_llm_instance_config_parsing(self):
        """测试 LLMInstanceConfig 解析。"""
        config = {
            "answer_llm": {"cognitive_mode": "deep", "provider": "openai", "model": "gpt-4o"},
            "pcr_llm": {"cognitive_mode": "fast", "provider": "ollama", "model": "llama3"},
        }
        orch = Orchestrator(
            pcr_engine=MagicMock(),
            intent_parser=MagicMock(),
            planning_skill=MagicMock(),
            cognitive_compiler=MagicMock(),
            context_manager=MagicMock(),
            topic_tree=MagicMock(),
            observability=MagicMock(),
            llm_providers=MagicMock(),
            config=config,
        )
        assert "answer_llm" in orch._llm_cfgs
        assert "pcr_llm" in orch._llm_cfgs
        assert orch._llm_cfgs["answer_llm"].cognitive_mode == "deep"
        assert orch._llm_cfgs["pcr_llm"].provider == "ollama"

    def test_empty_config(self):
        """测试空配置不报错。"""
        orch = Orchestrator(
            pcr_engine=MagicMock(),
            intent_parser=MagicMock(),
            planning_skill=MagicMock(),
            cognitive_compiler=MagicMock(),
            context_manager=MagicMock(),
            topic_tree=MagicMock(),
            observability=MagicMock(),
            llm_providers=MagicMock(),
            config={},
        )
        assert orch._llm_cfgs == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 关闭测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestShutdown:
    """Orchestrator 关闭测试。"""

    @pytest.mark.asyncio
    async def test_shutdown_clears_sessions(self, orchestrator: Orchestrator):
        """测试关闭后清除会话状态。"""
        # 先创建一些 turn index
        msg = UserMessage_v3(session_id="s1", content="test")
        await orchestrator.process_request(msg)
        assert len(orchestrator._session_turns) > 0

        await orchestrator.shutdown()
        assert len(orchestrator._session_turns) == 0

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, orchestrator: Orchestrator):
        """测试多次关闭不报错。"""
        await orchestrator.shutdown()
        await orchestrator.shutdown()
        assert True
