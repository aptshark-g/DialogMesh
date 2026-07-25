# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/tests/test_orchestrator.py
────────────────────────────────────────────────────────
DialogMesh Agent v3.0 Orchestrator 模块测试。

覆盖范围：
- 数据模型序列化/反序列化
- 融合引擎（4 种融合策略 + 冲突检测）
- 算法引擎（规则级 fallback）
- Orchestrator 单轮处理（mock provider）
- SystemBootstrap 6 阶段启动

运行方式：
    python -m pytest core/agent/v3_0/orchestrator/tests/test_orchestrator.py -v

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict

from core.agent.models import IntentCategory
from core.agent.v3_0.cognitive_tree.models import CogType, CogNodeStatus
from core.agent.v3_legacy.data_models import Intent_v3, TaskGraph_v3, TaskNode_v3

from core.agent.orchestrator.models import (
    BootstrapConfig,
    FusionResult,
    FusionSource,
    OrchestratorConfig,
    OrchestratorResult,
    SystemHealth,
    SystemPhase,
    TurnContext,
    TurnPhase,
)
from core.agent.orchestrator.orchestrator import (
    AlgorithmEngine,
    FusionEngine,
    LLMInstance,
    Orchestrator,
)
from core.agent.orchestrator.models import LLMInstanceResult
from core.agent.orchestrator.bootstrap import SystemBootstrap, SystemStartupError
from core.agent.planner.planner import PlanningSkill


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def orch_config() -> OrchestratorConfig:
    """标准编排器配置。"""
    return OrchestratorConfig(
        enable_pcr_llm=False,      # 测试时禁用真实 LLM
        enable_intent_llm=False,
        enable_planning_llm=False,
        enable_meta_cognitive_llm=False,
        enable_answer_llm=False,
        enable_reflective_llm=False,
        fallback_to_algorithm=True,
        fallback_to_single_task=True,
        clarification_threshold=0.3,
    )


@pytest.fixture
def algorithm_engine() -> AlgorithmEngine:
    """算法引擎实例。"""
    return AlgorithmEngine()


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestModels:
    """测试 Orchestrator 数据模型。"""

    def test_turn_context_lifecycle(self) -> None:
        """测试 TurnContext 的完整生命周期。"""
        ctx = TurnContext(session_id="sess-123", user_input="scan 100")
        assert ctx.current_phase == TurnPhase.IDLE
        assert ctx.turn_id.startswith("turn-")

        ctx.mark_phase(TurnPhase.PCR_ANALYSIS, 50.0)
        assert ctx.current_phase == TurnPhase.PCR_ANALYSIS
        assert ctx.phase_latencies_ms["pcr_analysis"] == 50.0

        ctx.add_trace("test message")
        assert len(ctx.trace_log) == 1
        assert "test message" in ctx.trace_log[0]

        ctx.add_error("test error")
        assert len(ctx.errors) == 1

        ctx.finish()
        assert ctx.current_phase == TurnPhase.COMPLETED
        assert ctx.finished_at is not None

    def test_orchestrator_result_to_agent_message(self) -> None:
        """测试 OrchestratorResult 转换为 AgentMessage_v3。"""
        result = OrchestratorResult(
            turn_id="t-001",
            session_id="sess-123",
            success=True,
            status="ok",
            answer="Found 3 addresses",
            answer_confidence=0.85,
            cited_cognitive_nodes=["C-abc123"],
        )
        msg = result.to_agent_message()
        assert msg.session_id == "sess-123"
        assert msg.content == "Found 3 addresses"
        assert msg.metadata["turn_id"] == "t-001"
        assert msg.metadata["cited_nodes"] == ["C-abc123"]

    def test_system_health(self) -> None:
        """测试 SystemHealth 模型。"""
        health = SystemHealth(
            healthy=True,
            status="healthy",
            phase=SystemPhase.COMPLETED,
            components={"observability": {"status": "ok"}},
        )
        assert health.healthy is True
        assert health.components["observability"]["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════
# 融合引擎测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFusionEngine:
    """测试认知双工融合引擎。"""

    def test_algorithm_high_confidence(self, orch_config: OrchestratorConfig) -> None:
        """测试算法高置信度路径。"""
        engine = FusionEngine(orch_config)
        algo = {"intent_category": "SCAN_MEMORY", "confidence": 0.95}
        llm = None  # LLM 失败

        result = engine.fuse(algo, llm)
        assert result.source == FusionSource.ALGORITHM
        assert result.confidence == 0.95
        assert result.clarification_required is False

    def test_llm_high_confidence(self, orch_config: OrchestratorConfig) -> None:
        """测试 LLM 高置信度路径。"""
        engine = FusionEngine(orch_config)
        algo = {"confidence": 0.3}  # 算法低置信
        llm = LLMInstanceResult(
            llm_name="Intent-LLM",
            success=True,
            output={"intent_category": "READ_MEMORY"},
            confidence=0.9,
        )

        result = engine.fuse(algo, llm)
        assert result.source == FusionSource.LLM
        assert result.confidence == 0.9

    def test_both_low_confidence_fallback(self, orch_config: OrchestratorConfig) -> None:
        """测试两者都低置信时的降级。"""
        engine = FusionEngine(orch_config)
        algo = {"confidence": 0.3}
        llm = LLMInstanceResult(
            llm_name="Intent-LLM",
            success=True,
            output={},
            confidence=0.3,
        )

        result = engine.fuse(algo, llm)
        assert result.source == FusionSource.FALLBACK
        assert result.clarification_required is True

    def test_conflict_detection(self, orch_config: OrchestratorConfig) -> None:
        """测试冲突检测与消解。"""
        engine = FusionEngine(orch_config)
        algo = {"intent_category": "SCAN_MEMORY", "confidence": 0.9}
        llm = LLMInstanceResult(
            llm_name="Intent-LLM",
            success=True,
            output={"intent_category": "READ_MEMORY"},  # 与算法冲突
            confidence=0.85,
        )

        result = engine.fuse(algo, llm)
        assert result.conflict_detected is True
        # 算法置信度更高，应选择算法但降低置信度
        assert result.confidence < 0.9
        assert result.confidence > 0.0

    def test_weighted_fusion(self, orch_config: OrchestratorConfig) -> None:
        """测试加权融合。"""
        engine = FusionEngine(orch_config)
        algo = {"intent_category": "SCAN_MEMORY", "confidence": 0.8}
        llm = LLMInstanceResult(
            llm_name="Intent-LLM",
            success=True,
            output={"intent_category": "SCAN_MEMORY"},  # 无冲突
            confidence=0.85,
        )

        result = engine.fuse(algo, llm)
        assert result.source == FusionSource.FUSED
        # 融合置信度应在两者之间
        assert 0.8 <= result.confidence <= 0.85


# ═══════════════════════════════════════════════════════════════════════════
# 算法引擎测试
# ═══════════════════════════════════════════════════════════════════════════

class TestAlgorithmEngine:
    """测试规则级 fallback 算法引擎。"""

    def test_pcr_analysis(self, algorithm_engine: AlgorithmEngine) -> None:
        """测试 PCR 规则分析。"""
        result = algorithm_engine.analyze_pcr("scan 100")
        assert "noise_analysis" in result
        assert "expectation_inference" in result
        assert "cognitive_snapshot" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_intent_parsing_scan(self, algorithm_engine: AlgorithmEngine) -> None:
        """测试 Intent 规则解析（scan 关键词）。"""
        result = algorithm_engine.parse_intent("scan memory for 100")
        assert result["intent_inference"]["primary_intent"] == "SCAN_MEMORY"
        assert result["confidence"] > 0.5

    def test_intent_parsing_read(self, algorithm_engine: AlgorithmEngine) -> None:
        """测试 Intent 规则解析（read 关键词）。"""
        result = algorithm_engine.parse_intent("read 0x1000")
        assert result["intent_inference"]["primary_intent"] == "READ_MEMORY"

    def test_intent_parsing_unknown(self, algorithm_engine: AlgorithmEngine) -> None:
        """测试未知意图。"""
        result = algorithm_engine.parse_intent("hello world")
        assert result["intent_inference"]["primary_intent"] == "UNKNOWN"
        assert result["confidence"] < 0.5


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestOrchestrator:
    """测试 Orchestrator 核心编排逻辑。"""

    @pytest.mark.asyncio
    async def test_process_turn_simple(self, orch_config: OrchestratorConfig) -> None:
        """测试简单输入的单轮处理。"""
        orchestrator = Orchestrator(config=orch_config)
        result = await orchestrator.process_turn(
            session_id="test-sess",
            user_input="scan 100",
        )
        assert result is not None
        assert result.status == "ok"
        assert "scan" in result.answer.lower() or "处理" in result.answer
        assert result.intent.category == IntentCategory.SCAN_MEMORY

    @pytest.mark.asyncio
    async def test_process_turn_clarification(self, orch_config: OrchestratorConfig) -> None:
        """测试低置信度输入触发澄清。"""
        orchestrator = Orchestrator(config=orch_config)
        result = await orchestrator.process_turn(
            session_id="test-sess",
            user_input="?",  # 极短输入，置信度低
        )
        # 由于规则引擎会返回 UNKNOWN 且置信度低，意图应为 UNKNOWN
        assert result is not None
        assert result.intent.category == IntentCategory.UNKNOWN
        assert result.answer is not None

    @pytest.mark.asyncio
    async def test_process_turn_task_graph(self, orch_config: OrchestratorConfig) -> None:
        """测试任务图生成。"""
        orchestrator = Orchestrator(
            config=orch_config,
            planning_skill=PlanningSkill(),
        )
        result = await orchestrator.process_turn(
            session_id="test-sess",
            user_input="hack health to 999",
        )
        assert result.task_graph is not None
        assert len(result.task_graph.nodes) >= 1
        # nodes 是 dict，取第一个值验证
        first_node = list(result.task_graph.nodes.values())[0]
        assert first_node.name in ("fallback_execution", "first_scan", "scan")

    @pytest.mark.asyncio
    async def test_orchestrator_health(self, orch_config: OrchestratorConfig) -> None:
        """测试编排器健康检查。"""
        orchestrator = Orchestrator(config=orch_config)
        health = await orchestrator.health_check()
        assert isinstance(health, dict)
        # provider 为 None 时 healthy 为 False，但 checks 结构应完整
        assert "checks" in health
        assert health["checks"]["orchestrator_status"] == "running"

    @pytest.mark.asyncio
    async def test_orchestrator_stats(self, orch_config: OrchestratorConfig) -> None:
        """测试编排器统计。"""
        orchestrator = Orchestrator(config=orch_config)
        stats = orchestrator.get_stats()
        assert stats["turn_counter"] == 0
        assert stats["closed"] is False

        # 处理一轮后计数应增加
        await orchestrator.process_turn("test-sess", "scan 100")
        stats = orchestrator.get_stats()
        assert stats["turn_counter"] == 1

    @pytest.mark.asyncio
    async def test_orchestrator_close(self, orch_config: OrchestratorConfig) -> None:
        """测试编排器关闭。"""
        orchestrator = Orchestrator(config=orch_config)
        await orchestrator.close()

        result = await orchestrator.process_turn("test-sess", "scan 100")
        assert result.success is False
        assert result.status == "error"
        assert "closed" in result.answer.lower()


# ═══════════════════════════════════════════════════════════════════════════
# SystemBootstrap 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSystemBootstrap:
    """测试 6 阶段系统启动流程。"""

    @pytest.mark.asyncio
    async def test_full_startup(self) -> None:
        """测试完整 6 阶段启动。"""
        config = BootstrapConfig(
            enable_cognitive_tree=True,
            enable_health_monitor=True,
        )
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        assert system is not None
        assert system.orchestrator is not None
        assert system.health is not None
        assert system.health.phase == SystemPhase.COMPLETED

        await bootstrap.shutdown(system)

    @pytest.mark.asyncio
    async def test_phase_results(self) -> None:
        """测试阶段结果追踪。"""
        config = BootstrapConfig()
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        results = bootstrap.get_phase_results()
        assert "phase_1_infrastructure" in results
        assert "phase_2_data" in results
        assert "phase_3_cognitive" in results
        assert "phase_4_orchestration" in results
        assert "phase_5_service" in results
        assert "phase_6_health" in results

        await bootstrap.shutdown(system)

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self) -> None:
        """测试关闭的幂等性。"""
        config = BootstrapConfig()
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        # 多次关闭不应报错
        await bootstrap.shutdown(system)
        await bootstrap.shutdown(system)  # 应安全处理
        assert system.health.phase == SystemPhase.COMPLETED

    @pytest.mark.asyncio
    async def test_orchestrator_after_startup(self) -> None:
        """测试启动后 Orchestrator 可用性。"""
        config = BootstrapConfig()
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        # 验证 Orchestrator 可以处理请求
        result = await system.orchestrator.process_turn(
            session_id="test-sess-2",
            user_input="read 0x1000",
        )
        assert result is not None
        assert result.status == "ok"
        assert result.intent.category == IntentCategory.READ_MEMORY
        assert "0x1000" in result.answer or "read" in result.answer.lower()

        await bootstrap.shutdown(system)


# ═══════════════════════════════════════════════════════════════════════════
# 端到端测试
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """端到端场景测试。"""

    @pytest.mark.asyncio
    async def test_memory_scan_workflow(self) -> None:
        """测试内存扫描完整工作流。"""
        config = BootstrapConfig()
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        try:
            # 第一轮：扫描
            result1 = await system.orchestrator.process_turn(
                session_id="e2e-sess",
                user_input="scan memory for 100",
            )
            assert result1.status == "ok"
            assert result1.intent.category == IntentCategory.SCAN_MEMORY
            assert result1.task_graph is not None
            assert len(result1.task_graph.nodes) >= 1
            assert "scan" in result1.answer.lower()
            assert result1.answer_confidence > 0

            # 第二轮：读取
            result2 = await system.orchestrator.process_turn(
                session_id="e2e-sess",
                user_input="read 0x1234",
            )
            assert result2.status == "ok"
            assert result2.intent.category == IntentCategory.READ_MEMORY
            assert "read" in result2.answer.lower()

            # 验证统计
            stats = system.orchestrator.get_stats()
            assert stats["turn_counter"] == 2

        finally:
            await bootstrap.shutdown(system)

    @pytest.mark.asyncio
    async def test_multi_session_isolation(self) -> None:
        """测试多会话隔离。"""
        config = BootstrapConfig()
        bootstrap = SystemBootstrap(config=config)
        system = await bootstrap.start()

        try:
            result_a = await system.orchestrator.process_turn(
                session_id="sess-a",
                user_input="scan 100",
            )
            result_b = await system.orchestrator.process_turn(
                session_id="sess-b",
                user_input="read 0x2000",
            )

            assert result_a.intent.category == IntentCategory.SCAN_MEMORY
            assert result_b.intent.category == IntentCategory.READ_MEMORY
            assert result_a.session_id == "sess-a"
            assert result_b.session_id == "sess-b"
            # 不同会话应独立处理
            assert result_a.turn_id != result_b.turn_id

        finally:
            await bootstrap.shutdown(system)


# ═══════════════════════════════════════════════════════════════════════════
# 负面测试
# ═══════════════════════════════════════════════════════════════════════════

class TestNegativeCases:
    """负面测试——边界条件、异常输入、错误路径。"""

    @pytest.mark.asyncio
    async def test_empty_input(self, orch_config: OrchestratorConfig) -> None:
        """测试空字符串输入应返回澄清或未知意图。"""
        orchestrator = Orchestrator(config=orch_config)
        result = await orchestrator.process_turn("test-sess", "")
        assert result.intent.category == IntentCategory.UNKNOWN
        assert result.status in ("ok", "clarifying")
        await orchestrator.close()

    @pytest.mark.asyncio
    async def test_whitespace_only_input(self, orch_config: OrchestratorConfig) -> None:
        """测试纯空格输入应返回未知意图。"""
        orchestrator = Orchestrator(config=orch_config)
        result = await orchestrator.process_turn("test-sess", "   ")
        assert result.intent.category == IntentCategory.UNKNOWN
        await orchestrator.close()

    @pytest.mark.asyncio
    async def test_very_long_input(self, orch_config: OrchestratorConfig) -> None:
        """测试超长输入（> 1000 字符）不应崩溃。"""
        orchestrator = Orchestrator(config=orch_config)
        long_input = "scan " + "x" * 2000
        result = await orchestrator.process_turn("test-sess", long_input)
        assert result is not None
        assert result.status in ("ok", "fallback", "clarifying")
        await orchestrator.close()

    @pytest.mark.asyncio
    async def test_closed_orchestrator(self, orch_config: OrchestratorConfig) -> None:
        """测试关闭后调用 process_turn 应返回错误。"""
        orchestrator = Orchestrator(config=orch_config)
        await orchestrator.close()
        result = await orchestrator.process_turn("test-sess", "scan 100")
        assert result.success is False
        assert result.status == "error"
        assert "closed" in result.answer.lower()

    @pytest.mark.asyncio
    async def test_unknown_intent_input(self, orch_config: OrchestratorConfig) -> None:
        """测试完全无关的输入应返回 UNKNOWN 意图。"""
        orchestrator = Orchestrator(config=orch_config)
        result = await orchestrator.process_turn("test-sess", "hello world how are you today")
        assert result.intent.category == IntentCategory.UNKNOWN
        assert result.intent.confidence < 0.5
        await orchestrator.close()

    @pytest.mark.asyncio
    async def test_fusion_llm_failure_fallback(self, orch_config: OrchestratorConfig) -> None:
        """测试 LLM 失败时融合引擎正确降级到算法。"""
        engine = FusionEngine(orch_config)
        algo = {"intent_category": "SCAN_MEMORY", "confidence": 0.8}
        llm = LLMInstanceResult(
            llm_name="Intent-LLM",
            success=False,  # LLM 失败
            output={},
            confidence=0.0,
        )
        result = engine.fuse(algo, llm)
        assert result.source == FusionSource.ALGORITHM
        assert result.confidence == 0.8
        assert result.clarification_required is False


# ═══════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
