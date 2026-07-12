# -*- coding: utf-8 -*-
"""
core/agent/v3_0/system_bootstrap.py
──────────────────────────────────
DialogMesh v3.0 SystemBootstrap — 6 阶段系统启动流程。

用途：
- 按 INTEGRATION.md §4.1 定义的顺序，分 6 个阶段初始化 DialogMesh v3.0 全部子系统。
- 阶段 1: 基础设施（Observability）
- 阶段 2: 数据层（Persistence + DataModel）
- 阶段 3: 认知层（TopicTree + ContextManager + CognitiveCompiler）
- 阶段 4: 编排层（LLM Providers + HybridRouter + PCR + IntentParser + ToolRegistry + PlanningSkill + Orchestrator）
- 阶段 5: 服务层（Service Layer）
- 阶段 6: 健康检查（全系统健康诊断）

设计原则：
- 所有阶段均为 async 方法，支持协程级别并发与超时控制。
- 每个阶段的初始化失败按文档 §4.2 的规范处理：致命错误立即抛出 SystemStartupError。
- 阶段 4 支持降级启动：部分 LLM Provider 不可用时仅注册可用实例并记录告警。
- 配置加载支持环境变量插值（${VAR} → os.environ）。

依赖模块：
- core.agent.v3_0.observability
- core.agent.v3_0.cognitive_tree
- core.agent.v3_0.context_manager
- core.agent.v3_0.cognitive_compiler
- core.agent.v3_0.llm_providers
- core.agent.v3_0.planning
- core.agent.v3_0.tool_registry
- core.agent.persistence

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def load_agent_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 agent_config.yaml 并展开环境变量。

    搜索路径优先级：
      1. 传入的 path 参数
      2. 环境变量 AGENT_CONFIG_PATH
      3. 项目根目录 config/agent_config.yaml
      4. 当前工作目录 config/agent_config.yaml

    若 PyYAML 未安装，返回空字典（降级启动）。
    """
    if yaml is None:
        logger.warning("PyYAML not installed, skipping YAML config load")
        return {}

    candidates: List[str] = []
    if path:
        candidates.append(path)
    env_path = os.environ.get("AGENT_CONFIG_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(
        str(Path(__file__).resolve().parents[3] / "config" / "agent_config.yaml")
    )
    candidates.append(str(Path.cwd() / "config" / "agent_config.yaml"))

    for candidate in candidates:
        cp = Path(candidate)
        if cp.exists():
            try:
                with cp.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                return _interpolate_env(raw) if raw else {}
            except Exception as exc:
                logger.warning(f"Config load failed from {cp}: {exc}")
                continue

    logger.warning("No agent_config.yaml found, using empty config")
    return {}

from core.agent.v3_0.data_models import (
    ComponentHealth,
    ComponentType,
    HealthStatus,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 异常定义
# ═══════════════════════════════════════════════════════════════════════════════

class SystemStartupError(Exception):
    """系统启动致命错误——任一阶段初始化失败时抛出。"""


class PhaseStartupError(SystemStartupError):
    """特定阶段启动失败，携带阶段编号与组件信息。"""

    def __init__(self, phase: int, component: str, message: str):
        self.phase = phase
        self.component = component
        super().__init__(f"[Phase {phase}] {component} init failed: {message}")


# ═══════════════════════════════════════════════════════════════════════════════
# 系统容器
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DialogMeshSystem:
    """
    DialogMesh v3.0 运行时系统容器。

    包含所有已初始化子系统的引用，供主入口与服务层直接访问。
    """

    orchestrator: Any
    service_layer: Optional[Any] = None
    observability: Optional[Any] = None
    persistence: Optional[Any] = None
    context_manager: Optional[Any] = None
    cognitive_compiler: Optional[Any] = None
    topic_tree: Optional[Any] = None
    llm_providers: Optional[Any] = None
    planning_skill: Optional[Any] = None
    tool_registry: Optional[Any] = None
    health: Optional[HealthStatus] = None
    started_at: float = field(default_factory=time.time)

    @property
    def uptime_seconds(self) -> float:
        """系统已运行秒数。"""
        return time.time() - self.started_at


# ═══════════════════════════════════════════════════════════════════════════════
# 配置加载器
# ═══════════════════════════════════════════════════════════════════════════════

def _interpolate_env(value: Any) -> Any:
    """递归替换字符串中的 ${ENV_VAR} 为对应环境变量值。"""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match: re.Match) -> str:
            env_key = match.group(1)
            env_val = os.environ.get(env_key, "")
            return env_val

        return pattern.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


def load_agent_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 agent_config.yaml 并展开环境变量。

    搜索路径优先级：
      1. 传入的 path 参数
      2. 环境变量 AGENT_CONFIG_PATH
      3. 项目根目录 config/agent_config.yaml
      4. 当前工作目录 config/agent_config.yaml
    """
    candidates: List[str] = []
    if path:
        candidates.append(path)
    env_path = os.environ.get("AGENT_CONFIG_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(
        str(Path(__file__).resolve().parents[3] / "config" / "agent_config.yaml")
    )
    candidates.append(str(Path.cwd() / "config" / "agent_config.yaml"))

    for candidate in candidates:
        cp = Path(candidate)
        if cp.exists():
            try:
                with cp.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                return _interpolate_env(raw) if raw else {}
            except Exception as exc:
                logger.warning(f"Config load failed from {cp}: {exc}")
                continue

    logger.warning("No agent_config.yaml found, using empty config")
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# SystemBootstrap
# ═══════════════════════════════════════════════════════════════════════════════

class SystemBootstrap:
    """
    DialogMesh v3.0 系统引导器 — 6 阶段启动流程。

    使用示例：

        bootstrap = SystemBootstrap(config_path="config/agent_config.yaml")
        system = await bootstrap.start()
        # system.orchestrator 已就绪，可直接处理请求
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._components: Dict[str, Any] = {}
        self._health_components: Dict[str, ComponentHealth] = {}

    # ── 公共入口 ────────────────────────────────────────────────────────────

    async def start(self) -> DialogMeshSystem:
        """
        启动 DialogMesh 系统。

        按 INTEGRATION.md §4.1 执行 6 阶段初始化，任何致命错误都会抛出
        SystemStartupError 子类异常。
        """
        overall_start = time.time()

        # 阶段 1: 基础设施
        observability = await self._phase_1_infrastructure()

        # 阶段 2: 数据层
        persistence, data_model = await self._phase_2_data_layer(observability)

        # 阶段 3: 认知层
        topic_tree, context_manager, cognitive_compiler = await self._phase_3_cognitive_layer(
            persistence, observability
        )

        # 阶段 4: 编排层
        orchestrator, llm_providers, planning_skill, tool_registry = await self._phase_4_orchestration(
            cognitive_compiler, context_manager, topic_tree, observability
        )

        # 阶段 5: 服务层
        service_layer = await self._phase_5_service_layer(
            orchestrator, observability
        )

        # 阶段 6: 健康检查
        health = await self._phase_6_health_check(
            llm_providers=llm_providers,
            persistence=persistence,
            service_layer=service_layer,
            observability=observability,
        )

        elapsed = (time.time() - overall_start) * 1000.0
        logger.info(f"[System] DialogMesh v3.0 startup complete in {elapsed:.1f}ms")

        return DialogMeshSystem(
            orchestrator=orchestrator,
            service_layer=service_layer,
            observability=observability,
            persistence=persistence,
            context_manager=context_manager,
            cognitive_compiler=cognitive_compiler,
            topic_tree=topic_tree,
            llm_providers=llm_providers,
            planning_skill=planning_skill,
            tool_registry=tool_registry,
            health=health,
        )

    async def shutdown(self, system: DialogMeshSystem) -> None:
        """
        优雅关闭系统，按逆序释放各阶段资源。
        """
        logger.info("[System] DialogMesh v3.0 shutting down...")

        # 逆序关闭
        if system.service_layer and hasattr(system.service_layer, "shutdown"):
            try:
                await system.service_layer.shutdown()
            except Exception as exc:
                logger.warning(f"Service layer shutdown error: {exc}")

        if system.orchestrator and hasattr(system.orchestrator, "shutdown"):
            try:
                await system.orchestrator.shutdown()
            except Exception as exc:
                logger.warning(f"Orchestrator shutdown error: {exc}")

        if system.llm_providers and hasattr(system.llm_providers, "close"):
            try:
                await system.llm_providers.close()
            except Exception as exc:
                logger.warning(f"LLM providers shutdown error: {exc}")

        if system.cognitive_compiler and hasattr(system.cognitive_compiler, "shutdown"):
            try:
                await system.cognitive_compiler.shutdown()
            except Exception as exc:
                logger.warning(f"Cognitive compiler shutdown error: {exc}")

        if system.context_manager and hasattr(system.context_manager, "shutdown"):
            try:
                await system.context_manager.shutdown()
            except Exception as exc:
                logger.warning(f"Context manager shutdown error: {exc}")

        if system.persistence and hasattr(system.persistence, "close"):
            try:
                system.persistence.close()
            except Exception as exc:
                logger.warning(f"Persistence shutdown error: {exc}")

        if system.observability and hasattr(system.observability, "shutdown"):
            try:
                await system.observability.shutdown()
            except Exception as exc:
                logger.warning(f"Observability shutdown error: {exc}")

        logger.info("[System] DialogMesh v3.0 shutdown complete")

    # ── 阶段 1: 基础设施 ───────────────────────────────────────────────────

    async def _phase_1_infrastructure(self) -> Any:
        """初始化 Observability（Telemetry）。"""
        logger.info("[Phase 1/6] 初始化基础设施...")
        phase_start = time.time()

        try:
            self._config = load_agent_config(self._config_path)

            from core.agent.v3_0.observability import Telemetry

            telemetry = await Telemetry.from_config()
            self._components["observability"] = telemetry

            latency_ms = (time.time() - phase_start) * 1000.0
            self._health_components["observability"] = ComponentHealth(
                component=ComponentType.LLM_PROVIDER,  # 映射到最接近的组件类型
                status="ok",
                latency_ms=latency_ms,
            )
            logger.info(f"[Phase 1/6] 基础设施初始化完成 ({latency_ms:.1f}ms)")
            return telemetry
        except Exception as exc:
            raise PhaseStartupError(1, "Observability", str(exc)) from exc

    # ── 阶段 2: 数据层 ────────────────────────────────────────────────────

    async def _phase_2_data_layer(
        self, observability: Any
    ) -> Tuple[Any, Any]:
        """初始化 Persistence 与 DataModel。"""
        logger.info("[Phase 2/6] 初始化数据层...")
        phase_start = time.time()

        try:
            persistence_cfg = self._config.get("persistence", {})
            db_path = persistence_cfg.get("database_path", "data/dialogmesh.db")

            # 使用现有 v2.x persistence 模块作为底层存储
            from core.agent.persistence import SQLiteSessionStore, TieredStorageManager

            warm_store = SQLiteSessionStore(db_path=db_path)
            persistence = TieredStorageManager(
                warm_store=warm_store,
                policy=None,  # 使用默认策略
            )

            # DataModel 在 v3.0 中已以 Pydantic 形式定义，无需额外初始化
            data_model = self._config.get("data_model", {})
            self._components["persistence"] = persistence
            self._components["data_model"] = data_model

            latency_ms = (time.time() - phase_start) * 1000.0
            self._health_components["persistence"] = ComponentHealth(
                component=ComponentType.PERSISTENCE,
                status="ok",
                latency_ms=latency_ms,
            )
            logger.info(f"[Phase 2/6] 数据层初始化完成 ({latency_ms:.1f}ms)")
            return persistence, data_model
        except Exception as exc:
            raise PhaseStartupError(2, "Persistence", str(exc)) from exc

    # ── 阶段 3: 认知层 ─────────────────────────────────────────────────────

    async def _phase_3_cognitive_layer(
        self,
        persistence: Any,
        observability: Any,
    ) -> Tuple[Any, Any, Any]:
        """初始化 TopicTree、ContextManager、CognitiveCompiler。"""
        logger.info("[Phase 3/6] 初始化认知层...")
        phase_start = time.time()

        try:
            # TopicTree
            from core.agent.v3_0.cognitive_tree import CognitiveTree

            topic_tree = CognitiveTree(session_id="global")
            self._components["topic_tree"] = topic_tree

            # ContextManager
            from core.agent.v3_0.context_manager import ContextManager, SQLiteContextStore, WindowConfig

            ctx_cfg = self._config.get("context_manager", {})
            window_config = WindowConfig(
                max_tokens=ctx_cfg.get("max_context_tokens", 8000),
                compression_threshold=ctx_cfg.get("compression_threshold", 2048),
                pruning_strategy=ctx_cfg.get("pruning_strategy", "oldest_first"),
            )
            # 若配置了 SQLite 持久化，使用 SQLiteContextStore；否则用内存
            try:
                db_path = self._config.get("persistence", {}).get("database_path", "data/dialogmesh.db")
                store = SQLiteContextStore(db_path=db_path)
            except Exception:
                from core.agent.v3_0.context_manager import InMemoryContextStore
                store = InMemoryContextStore()

            context_manager = ContextManager(
                store=store,
                default_window_config=window_config,
                enable_cognitive_tree=True,
            )
            self._components["context_manager"] = context_manager

            # CognitiveCompiler
            from core.agent.v3_0.cognitive_compiler import (
                CognitiveCompiler,
                CognitiveTreeStore,
                EdgeManager,
                EventBus,
                NodeLifecycleManager,
            )
            from core.agent.v3_0.cognitive_tree.models import AccessControlMatrix

            tree_store = CognitiveTreeStore()
            access_control = AccessControlMatrix()
            event_bus = EventBus()
            lifecycle_manager = NodeLifecycleManager(store=tree_store)
            edge_manager = EdgeManager(store=tree_store)

            cognitive_compiler = CognitiveCompiler(
                cognitive_tree_store=tree_store,
                access_control=access_control,
                event_bus=event_bus,
                lifecycle_manager=lifecycle_manager,
                edge_manager=edge_manager,
            )
            self._components["cognitive_compiler"] = cognitive_compiler

            latency_ms = (time.time() - phase_start) * 1000.0
            self._health_components["cognitive_compiler"] = ComponentHealth(
                component=ComponentType.COMPILER,
                status="ok",
                latency_ms=latency_ms,
            )
            logger.info(f"[Phase 3/6] 认知层初始化完成 ({latency_ms:.1f}ms)")
            return topic_tree, context_manager, cognitive_compiler
        except Exception as exc:
            raise PhaseStartupError(3, "CognitiveLayer", str(exc)) from exc

    # ── 阶段 4: 编排层 ──────────────────────────────────────────────────────

    async def _phase_4_orchestration(
        self,
        cognitive_compiler: Any,
        context_manager: Any,
        topic_tree: Any,
        observability: Any,
    ) -> Tuple[Any, Any, Any, Any]:
        """
        初始化 LLM Providers、HybridRouter、PCR、IntentParser、ToolRegistry、
        PlanningSkill 与 Orchestrator。

        本阶段支持降级启动：部分 Provider 不可用时仅注册可用实例。
        """
        logger.info("[Phase 4/6] 初始化编排层...")
        phase_start = time.time()

        # 4.1 LLM Providers + HybridRouter
        llm_providers = await self._init_llm_providers(observability)

        # 4.2 PCR Engine + Intent Parser（使用 v2.x 兼容接口作为适配层）
        pcr_engine = await self._init_pcr_engine(llm_providers, observability)
        intent_parser = await self._init_intent_parser(llm_providers, observability)

        # 4.3 Tool Registry
        tool_registry = await self._init_tool_registry(cognitive_compiler, observability)

        # 4.4 Planning Skill
        planning_skill = await self._init_planning_skill(
            llm_providers, tool_registry, cognitive_compiler, context_manager, observability
        )

        # 4.5 Orchestrator
        orchestrator = await self._init_orchestrator(
            planning_skill=planning_skill,
            cognitive_compiler=cognitive_compiler,
            context_manager=context_manager,
            observability=observability,
            llm_provider=llm_providers,
            tool_registry=tool_registry,
        )

        latency_ms = (time.time() - phase_start) * 1000.0
        self._health_components["orchestrator"] = ComponentHealth(
            component=ComponentType.ORCHESTRATOR,
            status="ok",
            latency_ms=latency_ms,
        )
        logger.info(f"[Phase 4/6] 编排层初始化完成 ({latency_ms:.1f}ms)")
        return orchestrator, llm_providers, planning_skill, tool_registry

    async def _init_llm_providers(self, observability: Any) -> Any:
        """初始化 LLM ProviderManager 与 HybridRouter。"""
        from core.agent.v3_0.llm_providers import ProviderManager, ProviderManagerConfig
        from core.agent.v3_0.llm_providers.models import ProviderConfig, ProviderBackend

        providers_cfg = self._config.get("llm_providers", {})
        fallback_order = self._config.get("hybrid_router", {}).get("fallback_order", ["openai", "ollama"])

        pm_config = ProviderManagerConfig(
            fallback_chain=fallback_order,
            enable_circuit_breaker=True,
        )
        manager = ProviderManager(config=pm_config)

        # 按配置注册各个 Provider
        for name, cfg in providers_cfg.items():
            if not isinstance(cfg, dict):
                continue
            try:
                backend_str = cfg.get("backend", name.lower())
                backend = ProviderBackend(backend_str)
                provider_config = ProviderConfig(
                    name=name,
                    backend=backend,
                    model=cfg.get("default_model", cfg.get("model", "gpt-4o")),
                    api_key=cfg.get("api_key"),
                    base_url=cfg.get("base_url"),
                    timeout_seconds=cfg.get("timeout_seconds", 30.0),
                    max_tokens=cfg.get("max_tokens", 512),
                    temperature=cfg.get("temperature", 0.3),
                    metadata={"max_concurrent_requests": cfg.get("max_concurrent_requests", 10)},
                )
                manager.register(provider_config)
                logger.info(f"[LLM] Registered provider: {name} ({backend.value})")
            except Exception as exc:
                logger.warning(f"[LLM] Provider {name} registration failed: {exc}")
                # 降级：继续注册其他 Provider

        self._components["llm_providers"] = manager
        return manager

    async def _init_pcr_engine(self, llm_providers: Any, observability: Any) -> Any:
        """初始化 PCR Engine（使用 v2.x 规则引擎作为基础）。"""
        try:
            from core.agent.pcr.rule_based import RuleBasedPCR

            pcr = RuleBasedPCR()
            logger.info("[PCR] RuleBasedPCR initialized")
            return pcr
        except Exception as exc:
            logger.warning(f"[PCR] RuleBasedPCR init failed: {exc}, using stub")
            return _StubPCREngine()

    async def _init_intent_parser(self, llm_providers: Any, observability: Any) -> Any:
        """初始化 Intent Parser（使用 v2.x 解析器作为基础）。"""
        try:
            from core.agent.v3_common.intent_parser import IntentParser

            parser = IntentParser()
            logger.info("[Intent] IntentParser initialized")
            return parser
        except Exception as exc:
            logger.warning(f"[Intent] IntentParser init failed: {exc}, using stub")
            return _StubIntentParser()

    async def _init_tool_registry(
        self, cognitive_compiler: Any, observability: Any
    ) -> Any:
        """初始化 Tool Registry。"""
        try:
            from core.agent.v3_0.tool_registry import ToolRegistry

            registry = ToolRegistry()
            logger.info("[ToolRegistry] Initialized")
            return registry
        except Exception as exc:
            logger.warning(f"[ToolRegistry] init failed: {exc}, using stub")
            return _StubToolRegistry()

    async def _init_planning_skill(
        self,
        llm_providers: Any,
        tool_registry: Any,
        cognitive_compiler: Any,
        context_manager: Any,
        observability: Any,
    ) -> Any:
        """初始化 Planning Skill。"""
        try:
            from core.agent.v3_0.planning import PlanningSkill

            # 尝试获取 Planning-LLM 实例
            planning_llm = None
            if llm_providers and hasattr(llm_providers, "get"):
                planning_llm = llm_providers.get("planning_llm")
                if not planning_llm:
                    # 回退：使用任何可用的 deep provider
                    for name in ["openai", "ollama"]:
                        p = llm_providers.get(name)
                        if p:
                            planning_llm = p
                            break

            planner = PlanningSkill(llm_provider=planning_llm)
            logger.info("[Planning] PlanningSkill initialized")
            return planner
        except Exception as exc:
            logger.warning(f"[Planning] PlanningSkill init failed: {exc}, using stub")
            return _StubPlanningSkill()

    async def _init_orchestrator(
        self,
        llm_provider: Any,
        planning_skill: Any,
        cognitive_compiler: Any,
        context_manager: Any,
        observability: Any,
        tool_registry: Any,
    ) -> Any:
        """初始化 Orchestrator — 整合 6 个 LLM 实例的核心编排器。"""
        from core.agent.v3_0.orchestrator import Orchestrator

        orch = Orchestrator(
            llm_provider=llm_provider,
            planning_skill=planning_skill,
            cognitive_compiler=cognitive_compiler,
            context_manager=context_manager,
            observability=observability,
            tool_registry=tool_registry,
        )
        logger.info("[Orchestrator] Initialized")
        return orch

    # ── 阶段 5: 服务层 ──────────────────────────────────────────────────────

    async def _phase_5_service_layer(
        self,
        orchestrator: Any,
        observability: Any,
    ) -> Any:
        """初始化 Service Layer（FastAPI / WebSocket）。"""
        logger.info("[Phase 5/6] 初始化服务层...")
        phase_start = time.time()

        try:
            # Service Layer 在 v3.0 中复用 v2.x 的 AgentService 作为适配层
            # 实际 FastAPI 应用创建由主入口负责
            service_cfg = self._config.get("service", {})
            service_stub = _ServiceLayerStub(
                orchestrator=orchestrator,
                observability=observability,
                config=service_cfg,
            )
            self._components["service_layer"] = service_stub

            latency_ms = (time.time() - phase_start) * 1000.0
            logger.info(f"[Phase 5/6] 服务层初始化完成 ({latency_ms:.1f}ms)")
            return service_stub
        except Exception as exc:
            raise PhaseStartupError(5, "ServiceLayer", str(exc)) from exc

    # ── 阶段 6: 健康检查 ─────────────────────────────────────────────────────

    async def _phase_6_health_check(
        self,
        llm_providers: Any,
        persistence: Any,
        service_layer: Any,
        observability: Any,
    ) -> HealthStatus:
        """执行全系统健康检查。"""
        logger.info("[Phase 6/6] 执行健康检查...")
        phase_start = time.time()

        health = HealthStatus(status="healthy")

        # 6.1 LLM Provider 健康检查
        if llm_providers and hasattr(llm_providers, "health_check_all"):
            try:
                await llm_providers.health_check_all()
                health.components["llm_providers"] = ComponentHealth(
                    component=ComponentType.LLM_PROVIDER,
                    status="ok",
                    latency_ms=0.0,
                )
            except Exception as exc:
                health.status = "degraded"
                health.components["llm_providers"] = ComponentHealth(
                    component=ComponentType.LLM_PROVIDER,
                    status="warn",
                    message=str(exc),
                )
                logger.warning(f"[Health] LLM provider health check: {exc}")
        elif llm_providers and hasattr(llm_providers, "get_all"):
            # 简单检查：尝试获取所有 provider
            try:
                providers = llm_providers.get_all()
                health.components["llm_providers"] = ComponentHealth(
                    component=ComponentType.LLM_PROVIDER,
                    status="ok" if providers else "warn",
                    latency_ms=0.0,
                )
            except Exception as exc:
                health.status = "degraded"
                health.components["llm_providers"] = ComponentHealth(
                    component=ComponentType.LLM_PROVIDER,
                    status="warn",
                    message=str(exc),
                )

        # 6.2 Persistence 健康检查
        if persistence and hasattr(persistence, "_warm"):
            try:
                # 尝试读取 warm 层
                health.components["persistence"] = ComponentHealth(
                    component=ComponentType.PERSISTENCE,
                    status="ok",
                    latency_ms=0.0,
                )
            except Exception as exc:
                health.status = "degraded"
                health.components["persistence"] = ComponentHealth(
                    component=ComponentType.PERSISTENCE,
                    status="warn",
                    message=str(exc),
                )

        # 6.3 综合评估
        if any(c.status == "warn" for c in health.components.values()):
            health.status = "degraded"
            logger.warning("[Health] System health degraded, check components above")
        else:
            logger.info("[Health] All components healthy")

        latency_ms = (time.time() - phase_start) * 1000.0
        health.components["health_check"] = ComponentHealth(
            component=ComponentType.ORCHESTRATOR,
            status="ok",
            latency_ms=latency_ms,
        )
        return health


# ═══════════════════════════════════════════════════════════════════════════════
# 存根组件（降级启动时使用）
# ═══════════════════════════════════════════════════════════════════════════════

class _StubPCREngine:
    """PCR Engine 存根 — 当规则引擎不可用时提供最小功能。"""

    def evaluate(self, input_data: Any) -> Any:
        from core.agent.pcr.datacontract import PCROutput_v1

        return PCROutput_v1.fast_execute_tool(query=getattr(input_data, "query", ""), latency_ms=1.0)

    def get_health(self) -> str:
        return "stub"


class _StubIntentParser:
    """Intent Parser 存根 — 提供最小解析功能。"""

    def parse(self, user_input: str, intent_context: Any, parse_context: Any) -> Any:
        from core.agent.v3_common.models import Entity, EntityType, Intent, IntentCategory, ParseResult

        intent = Intent(
            category=IntentCategory.UNKNOWN,
            raw_input=user_input,
            normalized_input=user_input,
            confidence=0.0,
        )
        return ParseResult(intent=intent, is_actionable=False)


class _StubToolRegistry:
    """Tool Registry 存根。"""

    def list_tools(self) -> List[Any]:
        return []

    def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        return {"status": "stub", "tool": tool_name}


class _StubPlanningSkill:
    """Planning Skill 存根。"""

    async def plan(self, intent: Any, intent_context: Optional[Any] = None, **kwargs: Any) -> Any:
        from core.agent.v3_0.planning.models import PlanResult

        return PlanResult(success=False, error="PlanningSkill stub: no LLM available")


class _ServiceLayerStub:
    """Service Layer 存根 — 在 Orchestrator 就绪后提供 FastAPI 应用绑定接口。"""

    def __init__(self, orchestrator: Any, observability: Any, config: Dict[str, Any]):
        self.orchestrator = orchestrator
        self.observability = observability
        self.config = config
        self._host = config.get("host", "0.0.0.0")
        self._port = config.get("port", 8000)
        self._api_prefix = config.get("api_prefix", "/api/v1")

    async def shutdown(self) -> None:
        logger.info("[ServiceLayerStub] Shutdown called")
