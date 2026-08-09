"""DialogMesh v6 Bootstrap — wire all modules into AgentOrchestrator.

10-chain pipeline: Compass → PCR → DualTrack → L4 → Behavior → Context → Engineering → LLM
Cold path: EventLog → MetaSubscriber → FeedbackBridge → Cold→Hot feedback

Usage:
    orch = bootstrap()
    result = orch.process("user input")
"""

from __future__ import annotations
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)


def bootstrap(pcr_router=None, intent_pipeline=None, l4_engine=None,
              behavior_collab=None, engineering_chain=None,
              llm=None, discourse_tree=None, event_log_db=None) -> "AgentOrchestrator":
    """Create and wire a complete AgentOrchestrator.

    All parameters optional — missing modules gracefully degrade.
    LLM auto-detects DeepSeek key if available.

    Usage:
        orch = bootstrap()                  # auto-detect everything
        orch = bootstrap(llm=my_provider)    # custom LLM
        result = orch.process("user input")
    """
    from core.agent.orchestrator.agent_native import AgentOrchestrator

    # ═══ LLM auto-detect ═══
    llm = llm or _auto_detect_llm()

    # ═══ EventLog (cold path) ═══
    event_log = None
    if event_log_db is None:
        event_log_db = os.path.join("data", "event_log.db")
    try:
        from core.agent.api.api_event_log import EventLog
        os.makedirs(os.path.dirname(event_log_db) or "data", exist_ok=True)
        event_log = EventLog(event_log_db)
        event_log.open()
        logger.info("EventLog ready: %s", event_log_db)
    except Exception as e:
        logger.warning("EventLog unavailable: %s", e)

    # ═══ Context (unified) ═══
    context_assembly = _load_unified_context()

    # ═══ Cognition Hub ═══
    cognition_hub = _load_cognition_hub()

    # ═══ Feedback Bridge (cold→hot) ═══
    feedback_bridge = _load_feedback_bridge()

    # ═══ Compass (multi-lens) ═══
    compass = _load_compass()

    # ═══ Cognitive Bridge (v4) ═══
    cognitive_bridge = _load_cognitive_bridge()

    # ═══ Execution & Safety ═══
    exec_pipeline = _load_execution_pipeline()
    file_sandbox = _load_file_sandbox()
    perm_guard = _load_permission_guard()
    sem_diff = _load_semantic_diff()
    evt_bus = _load_event_bus()
    reactor = _load_reactor()
    plan_gate = _load_plan_gate()

    # ═══ Wire everything ═══
    orch = AgentOrchestrator(
        pcr_router=pcr_router,
        intent_splitter=intent_pipeline,
        l4_engine=l4_engine,
        behavior_collab=behavior_collab,
        engineering_chain=engineering_chain,
        llm=llm,
        discourse_tree=discourse_tree,
        cognitive_bridge=cognitive_bridge,
        event_log=event_log,
        context_assembly=context_assembly,
        cognition_hub=cognition_hub,
        feedback_bridge=feedback_bridge,
        compass_selector=compass,
        plan_gate=plan_gate,
        execution_pipeline=exec_pipeline,
        file_sandbox=file_sandbox,
        permission_guard=perm_guard,
        semantic_diff=sem_diff,
        event_bus=evt_bus,
        reactor=reactor,
    )

    # Unified async prewarm: BGE model loads in background so the first API
    # request does not pay cold-load latency (DESIGN_DEEP_AUDIT §7.7).
    try:
        from core.infrastructure.model_service import prewarm_models
        prewarm_models(blocking=False)
    except Exception:
        pass

    logger.info("DialogMesh v6 bootstrap complete")
    _log_module_status(orch)
    return orch


def _load_unified_context():
    try:
        from core.agent.assembly.unified_context import UnifiedContext
        return UnifiedContext()
    except Exception as e:
        logger.debug("UnifiedContext: %s", e)
        return None


def _load_cognition_hub():
    try:
        from core.agent.cognition.hub import CognitionHub
        return CognitionHub()
    except Exception as e:
        logger.debug("CognitionHub: %s", e)
        return None


def _load_feedback_bridge():
    try:
        from core.agent.meta.feedback_bridge import FeedbackBridge
        return FeedbackBridge()
    except Exception as e:
        logger.debug("FeedbackBridge: %s", e)
        return None


def _load_compass():
    try:
        from core.agent.perception.compass import create_default_compass
        return create_default_compass()
    except Exception as e:
        logger.debug("Compass: %s", e)
        return None


def _load_cognitive_bridge():
    try:
        from core.agent.v4.cognitive_bridge import V4CognitiveBridge
        return V4CognitiveBridge()
    except Exception as e:
        logger.debug("V4CognitiveBridge: %s", e)
        return None


def _auto_detect_llm():
    """Auto-detect available LLM: switch gateway first (B8-4 主路径),
    then direct DeepSeek key, then None (structural mode)."""
    import os

    # B8-4: 主路径 = switch 网关（唯一内核）
    try:
        from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
        switch_url = os.environ.get("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080")
        gw = GatewayLLMProvider(base_url=switch_url)
        if gw.health_check():
            logger.info("LLM: switch gateway (%s)", switch_url)
            return gw
        logger.info("LLM: switch gateway unreachable (%s)", switch_url)
    except Exception as e:
        logger.debug("Switch gateway: %s", e)

    # 降级: DeepSeek 直连（switch 离线时 fallback）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.info("LLM: none (set DEEPSEEK_API_KEY for DeepSeek)")
        return None
    try:
        from core.agent.llm_providers.deepseek_direct import DeepSeekProvider
        llm = DeepSeekProvider(api_key=api_key)
        logger.info("LLM: DeepSeek (%s)", llm.model)
        return llm
    except Exception as e:
        logger.debug("DeepSeek: %s", e)
    return None


def _log_module_status(orch):
    statuses = []
    if orch._compass: statuses.append("Compass")
    if orch.pcr: statuses.append("PCR")
    if orch.intent: statuses.append("Intent")
    if orch.l4: statuses.append("L4")
    if orch._context_assembly: statuses.append("Context")
    if orch.llm: statuses.append("LLM")
    if orch._event_log: statuses.append("EventLog")
    if orch._cognition_hub: statuses.append("Cognition")
    if orch._feedback_bridge: statuses.append("Feedback")
    if orch._execution_pipeline: statuses.append("Execution")
    if orch._file_sandbox: statuses.append("Sandbox")
    if orch._permission_guard: statuses.append("Permission")
    if orch._event_bus: statuses.append("EventBus")
    if orch._reactor: statuses.append("ReActor")
    logger.info("Loaded: %s", ", ".join(statuses))
    if not orch.llm:
        logger.info("(LLM not connected — pipeline runs in structural mode)")


def _load_execution_pipeline():
    try:
        from core.agent.execution.tree_manager import AgentTreeManager
        from core.agent.execution.engine import ExecutionEngine
        from core.agent.execution.pipeline import ExecutionPipeline
        return ExecutionPipeline(tree_manager=AgentTreeManager(),
                                engine=ExecutionEngine())
    except Exception as e:
        logger.debug("ExecutionPipeline: %s", e)
        return None

def _load_file_sandbox():
    try:
        from core.agent.execution.sandbox import FileSandbox
        try:
            from core.agent.execution.semantic_diff import (
                SemanticConstraint,
                SemanticDiffer,
            )
            return FileSandbox(
                os.getcwd(),
                semantic_differ=SemanticDiffer(),
                semantic_constraint=SemanticConstraint(),
            )
        except Exception:
            return FileSandbox(os.getcwd())
    except Exception as e:
        logger.debug("FileSandbox: %s", e)
        return None

def _load_permission_guard():
    try:
        from core.agent.execution.permissions import PermissionEnforcer
        return PermissionEnforcer()
    except Exception as e:
        logger.debug("PermissionGuard: %s", e)
        return None

def _load_semantic_diff():
    try:
        from core.agent.execution.semantic_diff import SemanticDiffer
        return SemanticDiffer()
    except Exception as e:
        logger.debug("SemanticDiff: %s", e)
        return None

def _load_event_bus():
    try:
        from core.agent.event.event_bus import EventBus
        return EventBus()
    except Exception as e:
        logger.debug("EventBus: %s", e)
        return None

def _load_reactor():
    try:
        from core.agent.execution.closure import ReActor
        return ReActor()
    except Exception as e:
        logger.debug("ReActor: %s", e)
        return None

def _load_plan_gate():
    try:
        from core.agent.planning.checkpoint import PlanGate
        return PlanGate()
    except Exception as e:
        logger.debug("PlanGate: %s", e)
        return None


# ═══ Quick test ═══

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orch = bootstrap()
    r = orch.process("先定位延迟，然后修复它")
    print(f"\nPipeline OK — latency: {r.get('latency_ms')}ms")
    print(f"Keys: {list(r.keys())}")
