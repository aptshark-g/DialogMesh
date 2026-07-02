# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/bootstrap.py
─────────────────────────────────────────
DialogMesh Agent v3.0 — 系统引导器（SystemBootstrap）。

用途：
- 按 INTEGRATION.md §4 定义 6 阶段启动流程初始化 DialogMesh v3.0 系统。
- 管理组件依赖顺序、失败降级、配置加载与健康检查。
- 所有阶段均为异步，支持并发初始化和优雅降级。

6 阶段启动流程：
  Phase 1: 基础设施 — Observability（Metrics + Logger + Tracer + Alert）
  Phase 2: 数据层 — Persistence + DataModel（SQLite + 表创建）
  Phase 3: 认知层 — TopicTree + ContextManager + CognitiveCompiler
  Phase 4: 编排层 — LLM Providers + HybridRouter + PCR + Intent + Planning + ToolRegistry + Orchestrator
  Phase 5: 服务层 — Service Layer（WebSocket + HTTP）
  Phase 6: 健康检查 — 全系统诊断

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.agent.v3_0.cognitive_compiler.compiler import (
    CognitiveCompiler,
    CognitiveTreeStore,
)
from core.agent.v3_0.cognitive_compiler.event_bus import EventBus
from core.agent.v3_0.cognitive_tree.models import AccessControlMatrix
from core.agent.v3_0.context_manager.manager import ContextManager
from core.agent.v3_0.context_manager.store import InMemoryContextStore
from core.agent.v3_0.llm_providers.provider_manager import ProviderManager
from core.agent.v3_0.observability.telemetry import Telemetry
from core.agent.v3_0.planning.planner import PlanningSkill
from core.agent.v3_0.tool_registry.registry import ToolRegistry

from core.agent.v3_0.orchestrator.models import (
    BootstrapConfig,
    DialogMeshSystem,
    SystemHealth,
    SystemPhase,
    OrchestratorConfig,
)
from core.agent.v3_0.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class SystemStartupError(Exception):
    """系统启动失败异常。"""
    pass


class SystemBootstrap:
    """DialogMesh v3.0 系统引导器——6 阶段启动流程。

    使用示例::

        bootstrap = SystemBootstrap(config=BootstrapConfig())
        system = await bootstrap.start()
        # 使用 system.orchestrator.process_turn(...)
        await bootstrap.shutdown(system)
    """

    def __init__(self, config: Optional[BootstrapConfig] = None) -> None:
        self.config = config or BootstrapConfig()
        self._phase: SystemPhase = SystemPhase.PHASE_1_INFRASTRUCTURE
        self._phase_results: Dict[SystemPhase, Dict[str, Any]] = {}
        self._start_time = 0.0

    # ── 主入口 ────────────────────────────────────────────────────────────

    async def start(self) -> DialogMeshSystem:
        """启动 DialogMesh 系统。

        Returns:
            DialogMeshSystem：包含所有初始化组件的系统容器。

        Raises:
            SystemStartupError: 任何致命阶段失败时抛出。
        """
        self._start_time = time.time()
        system = DialogMeshSystem(config=self.config)
        health = SystemHealth(phase=SystemPhase.PHASE_1_INFRASTRUCTURE)

        try:
            # ── Phase 1: 基础设施 ──
            await self._phase_1_infrastructure(system, health)

            # ── Phase 2: 数据层 ──
            await self._phase_2_data(system, health)

            # ── Phase 3: 认知层 ──
            await self._phase_3_cognitive(system, health)

            # ── Phase 4: 编排层 ──
            await self._phase_4_orchestration(system, health)

            # ── Phase 5: 服务层 ──
            await self._phase_5_service(system, health)

            # ── Phase 6: 健康检查 ──
            await self._phase_6_health(system, health)

            system.health = health
            total_time = time.time() - self._start_time
            logger.info("DialogMesh v3.0 startup complete in %.2fs", total_time)
            return system

        except Exception as exc:
            health.healthy = False
            health.status = "unhealthy"
            health.phase = self._phase
            health.errors.append(str(exc))
            system.health = health
            logger.error("DialogMesh v3.0 startup failed at %s: %s", self._phase.value, exc)
            raise SystemStartupError(f"Startup failed at {self._phase.value}: {exc}") from exc

    async def shutdown(self, system: DialogMeshSystem) -> None:
        """优雅关闭系统。

        按启动的逆序关闭各组件。
        """
        logger.info("Shutting down DialogMesh v3.0...")
        try:
            # 1. 关闭 Orchestrator
            if system.orchestrator and hasattr(system.orchestrator, "close"):
                await system.orchestrator.close()
                logger.info("Orchestrator closed")

            # 2. 关闭 Observability
            if system.observability and hasattr(system.observability, "shutdown"):
                await system.observability.shutdown()
                logger.info("Observability shutdown")

            # 3. 关闭 ContextManager
            # (ContextManager 是 Orchestrator 内部依赖，已在 Orchestrator 中关闭)

            logger.info("DialogMesh v3.0 shutdown complete")
        except Exception as exc:
            logger.error("Shutdown error: %s", exc)
            raise

    # ── Phase 1: 基础设施 ─────────────────────────────────────────────────

    async def _phase_1_infrastructure(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """初始化可观测性系统（Telemetry）。"""
        self._phase = SystemPhase.PHASE_1_INFRASTRUCTURE
        phase_start = time.time()
        logger.info("[Phase 1/6] Initializing infrastructure...")

        try:
            await asyncio.sleep(0)
            telemetry = await Telemetry.from_config(
                store_db_path=self.config.observability_db_path
            )
            system.observability = telemetry

            # 记录启动事件
            await telemetry.logger.log_turn(
                session_id="system",
                turn_index=0,
                query="system_startup",
                latency_ms=0.0,
                intent_result="startup",
                confidence=1.0,
                execution_status="phase_1",
                trace=["Infrastructure initialization started"],
            )

            health.components["observability"] = {
                "status": "ok",
                "latency_ms": (time.time() - phase_start) * 1000.0,
            }
            self._phase_results[self._phase] = {"observability": "ok"}
            logger.info("[Phase 1/6] Infrastructure initialized")

        except Exception as exc:
            health.components["observability"] = {
                "status": "error",
                "error": str(exc),
            }
            logger.error("[Phase 1/6] Infrastructure failed: %s", exc)
            raise  # Phase 1 失败为致命错误

    # ── Phase 2: 数据层 ─────────────────────────────────────────────────

    async def _phase_2_data(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """初始化持久化与数据模型。"""
        self._phase = SystemPhase.PHASE_2_DATA
        phase_start = time.time()
        logger.info("[Phase 2/6] Initializing data layer...")

        try:
            await asyncio.sleep(0)
            # 目前使用 InMemoryContextStore（Phase 1）
            # 后续可接入 SQLite / PostgreSQL
            store = InMemoryContextStore()
            await store._ensure_connection() if hasattr(store, "_ensure_connection") else None

            health.components["persistence"] = {
                "status": "ok",
                "latency_ms": (time.time() - phase_start) * 1000.0,
            }
            self._phase_results[self._phase] = {"persistence": "in_memory"}
            logger.info("[Phase 2/6] Data layer initialized (in-memory)")

        except Exception as exc:
            health.components["persistence"] = {
                "status": "error",
                "error": str(exc),
            }
            logger.error("[Phase 2/6] Data layer failed: %s", exc)
            raise  # Phase 2 失败为致命错误

    # ── Phase 3: 认知层 ─────────────────────────────────────────────────

    async def _phase_3_cognitive(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """初始化认知层：TopicTree、ContextManager、CognitiveCompiler。"""
        self._phase = SystemPhase.PHASE_3_COGNITIVE
        phase_start = time.time()
        logger.info("[Phase 3/6] Initializing cognitive layer...")

        try:
            await asyncio.sleep(0)

            # 1. 事件总线
            event_bus = EventBus()
            event_bus.start()

            # 2. 认知树存储
            ct_store = CognitiveTreeStore()

            # 3. 访问控制矩阵
            access_control = AccessControlMatrix()
            # 使用 AccessControlMatrix 直接作为权限管理器
            ac_manager = access_control

            # 4. 节点生命周期管理器
            try:
                from core.agent.v3_0.cognitive_compiler.lifecycle import NodeLifecycleManager
                lifecycle = NodeLifecycleManager(ct_store)
            except Exception:
                lifecycle = None  # type: ignore

            # 5. 边管理器
            try:
                from core.agent.v3_0.cognitive_compiler.edge_manager import EdgeManager
                edge_manager = EdgeManager(ct_store)
            except Exception:
                edge_manager = None  # type: ignore

            # 6. 认知编译器
            cognitive_compiler = CognitiveCompiler(
                cognitive_tree_store=ct_store,
                access_control=ac_manager,
                event_bus=event_bus,
                lifecycle_manager=lifecycle,
                edge_manager=edge_manager,
            )

            # 7. 上下文管理器
            context_manager = ContextManager(
                store=InMemoryContextStore(),
                enable_cognitive_tree=self.config.enable_cognitive_tree,
            )

            # 暂存到系统对象
            system._cognitive_compiler = cognitive_compiler  # type: ignore
            system._context_manager = context_manager  # type: ignore
            system._event_bus = event_bus  # type: ignore

            health.components["cognitive_compiler"] = {
                "status": "ok",
                "latency_ms": (time.time() - phase_start) * 1000.0,
            }
            health.components["context_manager"] = {"status": "ok"}
            self._phase_results[self._phase] = {
                "cognitive_compiler": "ok",
                "context_manager": "ok",
            }
            logger.info("[Phase 3/6] Cognitive layer initialized")

        except Exception as exc:
            health.components["cognitive_compiler"] = {
                "status": "error",
                "error": str(exc),
            }
            logger.error("[Phase 3/6] Cognitive layer failed: %s", exc)
            raise  # Phase 3 失败为致命错误

    # ── Phase 4: 编排层 ─────────────────────────────────────────────────

    async def _phase_4_orchestration(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """初始化编排层：LLM Providers、Planning、ToolRegistry、Orchestrator。"""
        self._phase = SystemPhase.PHASE_4_ORCHESTRATION
        phase_start = time.time()
        logger.info("[Phase 4/6] Initializing orchestration layer...")

        try:
            await asyncio.sleep(0)

            # 1. LLM Provider Manager
            provider_manager = None
            try:
                provider_manager = ProviderManager()
                # 如果配置了 provider，尝试注册 mock provider（开发阶段）
                from core.agent.v3_0.llm_providers.models import ProviderConfig, ProviderBackend
                mock_config = ProviderConfig(
                    name="mock",
                    backend=ProviderBackend.MOCK,
                    metadata={"default_response": '{"response": "Mock response", "confidence": 0.8}'},
                )
                provider_manager.register(mock_config)
                logger.info("Mock provider registered for development")
            except Exception as exc:
                logger.warning("ProviderManager initialization warning: %s", exc)

            # 2. 规划技能
            planning_skill = PlanningSkill(llm_provider=provider_manager)

            # 3. 工具注册中心
            tool_registry = ToolRegistry()
            # 注册一些基础工具（开发阶段）
            from core.agent.v3_0.tool_registry.models import ToolDefinition, ToolSource
            tool_registry.register_sync(
                ToolDefinition(name="memory_read", description="Read memory at address", tags=["memory"], source=ToolSource.BUILTIN)
            )
            tool_registry.register_sync(
                ToolDefinition(name="memory_write", description="Write memory at address", tags=["memory"], source=ToolSource.BUILTIN, dangerous=True)
            )
            tool_registry.register_sync(
                ToolDefinition(name="first_scan", description="First scan for value", tags=["scan"], source=ToolSource.BUILTIN)
            )

            # 4. Orchestrator 配置
            orch_config = OrchestratorConfig()

            # 5. Orchestrator
            cognitive_compiler = getattr(system, "_cognitive_compiler", None)
            context_manager = getattr(system, "_context_manager", None)
            event_bus = getattr(system, "_event_bus", None)

            orchestrator = Orchestrator(
                config=orch_config,
                llm_provider=provider_manager,
                cognitive_compiler=cognitive_compiler,
                context_manager=context_manager,
                planning_skill=planning_skill,
                tool_registry=tool_registry,
                observability=system.observability,
                event_bus=event_bus,
            )

            system.orchestrator = orchestrator

            health.components["llm_providers"] = {
                "status": "ok" if provider_manager else "degraded",
            }
            health.components["planning_skill"] = {"status": "ok"}
            health.components["tool_registry"] = {"status": "ok"}
            health.components["orchestrator"] = {
                "status": "ok",
                "latency_ms": (time.time() - phase_start) * 1000.0,
            }
            self._phase_results[self._phase] = {
                "llm_providers": "ok",
                "planning_skill": "ok",
                "tool_registry": "ok",
                "orchestrator": "ok",
            }
            logger.info("[Phase 4/6] Orchestration layer initialized")

        except Exception as exc:
            health.components["orchestrator"] = {
                "status": "error",
                "error": str(exc),
            }
            logger.error("[Phase 4/6] Orchestration layer failed: %s", exc)
            # Phase 4 允许降级启动（只使用可用 Provider）
            if not health.components.get("llm_providers"):
                raise  # 如果完全不可用，则致命

    # ── Phase 5: 服务层 ─────────────────────────────────────────────────

    async def _phase_5_service(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """初始化服务层（WebSocket + HTTP）。"""
        self._phase = SystemPhase.PHASE_5_SERVICE
        phase_start = time.time()
        logger.info("[Phase 5/6] Initializing service layer...")

        try:
            await asyncio.sleep(0)
            # Phase 1 暂不实现完整 Service Layer
            # 仅记录占位，实际 FastAPI/WebSocket 服务在 core/service/v3_0 中实现
            health.components["service_layer"] = {
                "status": "degraded",
                "message": "Phase 1: service layer placeholder",
                "latency_ms": (time.time() - phase_start) * 1000.0,
            }
            self._phase_results[self._phase] = {"service_layer": "placeholder"}
            logger.info("[Phase 5/6] Service layer initialized (placeholder)")

        except Exception as exc:
            health.components["service_layer"] = {
                "status": "error",
                "error": str(exc),
            }
            logger.error("[Phase 5/6] Service layer failed: %s", exc)
            raise  # Phase 5 失败为致命错误

    # ── Phase 6: 健康检查 ─────────────────────────────────────────────────

    async def _phase_6_health(
        self, system: DialogMeshSystem, health: SystemHealth
    ) -> None:
        """执行全系统健康检查。"""
        self._phase = SystemPhase.PHASE_6_HEALTH
        phase_start = time.time()
        logger.info("[Phase 6/6] Running health check...")

        try:
            await asyncio.sleep(0)
            errors = []
            degraded = False

            # 检查 Orchestrator
            if system.orchestrator:
                orch_health = await system.orchestrator.health_check()
                if not orch_health.get("healthy"):
                    errors.append(f"Orchestrator: {orch_health}")
                    degraded = True
            else:
                errors.append("Orchestrator not initialized")
                degraded = True

            # 检查 Observability
            if system.observability:
                try:
                    global_health = await system.observability.get_global_health()
                    if global_health.get("error_rate", 0) > 0.5:
                        degraded = True
                except Exception as exc:
                    logger.warning("Observability health check failed: %s", exc)
            else:
                errors.append("Observability not initialized")

            health.healthy = len(errors) == 0 and not degraded
            health.status = "healthy" if health.healthy else ("degraded" if degraded else "unhealthy")
            health.phase = SystemPhase.COMPLETED
            health.uptime_seconds = time.time() - self._start_time
            health.errors.extend(errors)
            health.timestamp = time.time()

            self._phase_results[self._phase] = {
                "healthy": health.healthy,
                "status": health.status,
                "errors": errors,
            }
            logger.info(
                "[Phase 6/6] Health check complete: status=%s, errors=%d",
                health.status, len(errors)
            )

            if not health.healthy and errors:
                logger.warning("Health check found errors: %s", errors)

        except Exception as exc:
            health.healthy = False
            health.status = "unhealthy"
            health.errors.append(str(exc))
            logger.error("[Phase 6/6] Health check failed: %s", exc)
            # Phase 6 非致命，记录告警

    # ── 辅助方法 ────────────────────────────────────────────────────────────

    def get_phase_results(self) -> Dict[str, Any]:
        """获取所有阶段的启动结果（只读副本）。"""
        return {
            phase.value: result
            for phase, result in self._phase_results.items()
        }

    def get_current_phase(self) -> SystemPhase:
        """获取当前启动阶段。"""
        return self._phase

    # ── 自检 ────────────────────────────────────────────────────────────

    if __name__ == "__main__":
        import asyncio

        async def _self_test() -> None:
            logger.info("=== SystemBootstrap self-test ===")
            bootstrap = SystemBootstrap(config=BootstrapConfig())
            try:
                system = await bootstrap.start()
                assert system.orchestrator is not None
                assert system.health.healthy or system.health.status == "degraded"
                print(f"[PASS] System started: health={system.health.status}")

                # 测试单轮处理
                result = await system.orchestrator.process_turn(
                    session_id="test-session",
                    user_input="scan memory for 100",
                )
                assert result.answer is not None
                print(f"[PASS] Process turn: status={result.status}, answer_len={len(result.answer)}")

                await bootstrap.shutdown(system)
                print(f"[PASS] System shutdown")
                logger.info("=== SystemBootstrap self-test passed ===")
            except Exception as exc:
                logger.error("Self-test failed: %s", exc)
                raise

        asyncio.run(_self_test())
